"""Stock Presidio baseline. Implement custom detection for the exercise."""

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine


def build_analyzer(mode: str) -> AnalyzerEngine:
    if mode not in {"default", "lithuanian"}:
        raise ValueError(f"Unknown detector mode: {mode}")
    if mode == "lithuanian":
        raise NotImplementedError("Custom detection is a student exercise")
    return AnalyzerEngine()


def detect(analyzer: AnalyzerEngine, text: str):
    return analyzer.analyze(text=text, language="en", score_threshold=0.5)


def redact(analyzer: AnalyzerEngine, text: str) -> str:
    return AnonymizerEngine().anonymize(
        text=text, analyzer_results=detect(analyzer, text),
    ).text
