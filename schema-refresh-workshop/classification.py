"""Combine schema hints, nested-data analysis, and Presidio sample evidence."""

from collections import Counter
import json
import re

from catalog import full_domain_is_safe, samples

SENSITIVE_NAME = re.compile(r"email|phone|mobile|address|national|passport|birth|salary|profit|contact|asmens|telefon|atlygin", re.I)
COLOR_DOMAIN = {"red", "green", "blue", "black", "white", "yellow"}
ENTITIES = ["EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON", "LOCATION", "LT_PERSON_CODE"]
_analyzer = None


def analyzer():
    global _analyzer
    if _analyzer is None:
        from shared_detector import build_analyzer
        _analyzer = build_analyzer("lithuanian")
    return _analyzer


def leaves(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield from leaves(child)
    elif isinstance(value, list):
        for child in value:
            yield from leaves(child)
    elif isinstance(value, str):
        yield value


def classify(connection, table_name, column):
    values = samples(connection, table_name, column)
    findings = {"column": f"{table_name}.{column['column_name']}", "type": column["type"],
                "sample_count": len(values), "entity_counts": {}, "reasons": []}
    if column["type"] == "text" and column["column_name"] == "favorite_color" and values:
        if full_domain_is_safe(connection, table_name, column, COLOR_DOMAIN):
            return {**findings, "decision": "keep", "rule": {"action": "keep", "domain": sorted(COLOR_DOMAIN)},
                    "reasons": ["recognized benign field; full-column enum check passed"]}
    if SENSITIVE_NAME.search(column["column_name"]):
        findings["reasons"].append("sensitive column-name signal")
    counts = Counter()
    if column["type"] in {"text", "jsonb"}:
        for value in values:
            texts = leaves(json.loads(value)) if column["type"] == "jsonb" else [value]
            for text in texts:
                for result in analyzer().analyze(text=text, language="en", entities=ENTITIES, score_threshold=0.5):
                    counts[result.entity_type] += 1
    findings["entity_counts"] = dict(counts)
    if counts:
        findings["reasons"].append("sampled data contains detected PII")
    if findings["reasons"] and column["nullable"]:
        return {**findings, "decision": "anonymize", "rule": {"action": "null"}}
    reasons = findings["reasons"] + ["absence of sample detections is not evidence of safety" if not counts
                                    else "NOT NULL field requires a compatible reviewed transform"]
    return {**findings, "decision": "review", "rule": None, "reasons": reasons}
