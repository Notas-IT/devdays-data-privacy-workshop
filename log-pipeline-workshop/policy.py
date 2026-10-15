"""Validate policy and construct a new outbound record from safe fields only."""

import hashlib
import json
from pathlib import Path
import re

SOURCES = {"hr": "/raw/hr/app.jsonl", "billing": "/raw/billing/app.jsonl"}
EVENTS = {"salary_export", "invoice_created"}
FIELDS = {"employee_name", "national_id", "email", "phone", "address",
          "salary_eur", "company_profit_eur"}
ENTITIES = ["PERSON", "LOCATION", "EMAIL_ADDRESS", "PHONE_NUMBER", "LT_PERSON_CODE", "LT_SALARY"]


def validate_policy(policy: dict) -> dict:
    if not isinstance(policy, dict):
        raise ValueError("Policy must be an object")
    if set(policy) - {"version", "message_action", "message_replacement", "field_actions"}:
        raise ValueError("Unknown policy option")
    if not isinstance(policy.get("version"), str) or not re.fullmatch(r"[a-z0-9_-]{1,32}", policy["version"]):
        raise ValueError("Invalid version")
    if policy.get("message_action") not in {"replace", "drop", "presidio"}:
        raise ValueError("Unsupported message action")
    replacement = policy.get("message_replacement", "<REDACTED_MESSAGE>")
    if replacement not in {"<REDACTED_MESSAGE>", "<MESSAGE_REMOVED>"}:
        raise ValueError("Unsupported message replacement")
    actions = policy.get("field_actions")
    if not isinstance(actions, dict) or set(actions) - FIELDS:
        raise ValueError("Invalid field actions")
    if any(action not in {"replace", "drop"} for action in actions.values()):
        raise ValueError("Unsupported field action")
    return policy


class PolicyStore:
    def __init__(self, path: Path):
        self.path = path
        self.policy = None
        self.revision = None
        self.valid = False
        self.last_bytes = None

    def refresh(self) -> bool:
        try:
            content = self.path.read_bytes()
            if content == self.last_bytes and self.valid:
                return self.valid
            policy = validate_policy(json.loads(content))
        except (OSError, ValueError, TypeError):
            self.valid = False
            return False
        self.policy = policy
        self.revision = hashlib.sha256(content).hexdigest()[:12]
        self.last_bytes = content
        self.valid = True
        return True


def sanitize(record: dict, service: str, policy: dict, revision: str, analyzer=None) -> dict:
    if not isinstance(record, dict) or service not in SOURCES:
        raise ValueError("Invalid source record")
    level = record.get("level")
    event_name = record.get("event")
    output = {
        "service": service,
        "level": level if isinstance(level, str) and level in {"INFO", "WARN", "ERROR"} else "INFO",
        "event": event_name if isinstance(event_name, str) and event_name in EVENTS else "unknown",
        "policy_version": policy["version"], "policy_revision": revision,
    }
    for field, action in policy["field_actions"].items():
        if field in record and action == "replace":
            output[field] = "<REDACTED>"
    action = policy["message_action"]
    if action == "replace":
        output["message"] = policy.get("message_replacement", "<REDACTED_MESSAGE>")
    elif action == "presidio":
        if analyzer is None:
            raise ValueError("Presidio must be available before forwarding")
        if not isinstance(record.get("message"), str):
            raise ValueError("Message must be text")
        from presidio_anonymizer import AnonymizerEngine
        from presidio_anonymizer.entities import OperatorConfig
        results = analyzer.analyze(text=record["message"], language="en", entities=ENTITIES,
                                   score_threshold=0.5)
        output["message"] = AnonymizerEngine().anonymize(
            text=record["message"], analyzer_results=results,
            operators={"DEFAULT": OperatorConfig("replace")},
        ).text
    return output
