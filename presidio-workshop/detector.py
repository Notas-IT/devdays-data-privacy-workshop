"""Default Presidio and additive recognizers for the Lithuanian log exercise."""

import regex
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig


def field_pattern(labels: str, value: str) -> str:
    # Presidio uses the regex package, which supports variable-length lookbehind.
    return rf"(?<=\b(?i:{labels})[=:][ \t]{{0,3}}){value}"


def lithuanian_recognizers() -> list[PatternRecognizer]:
    name = r"[A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+"
    rules = [
        ("LT_PERSON_CODE", "Lithuanian personal code in a labeled field",
         field_pattern(r"(?:asmens_kodas|asmens kodas|a\.k\.)", r"[3-6]\d{10}(?!\d)")),
        ("PERSON", "Lithuanian name in a labeled field",
         field_pattern(r"(?:darbuotojas|pacientas|klientas|vardas_pavarde)",
                       rf"{name}(?:-{name})? {name}(?:-{name})?(?![\w-])")),
        ("LOCATION", "Lithuanian address in a labeled field",
         field_pattern(r"(?:adresas|gyvenamoji_vieta)",
                       r"[A-ZĄČĘĖĮŠŲŪŽ][^;\n]+?\bg\. [0-9]+(?:-[0-9]+)?, [A-ZĄČĘĖĮŠŲŪŽ][a-ząčęėįšųūž]+(?=;|$)")),
        ("DATE_TIME", "Birth date in a Lithuanian labeled field",
         field_pattern(r"(?:gimimo_data|gimimo data)",
                       r"(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])(?!\d)")),
        ("PHONE_NUMBER", "Local Lithuanian mobile in a labeled field",
         field_pattern(r"(?:telefonas|tel|mobilus)", r"0[ -]?6\d{2}[ -]?\d{2}[ -]?\d{3}(?!\d)")),
        ("EMAIL_ADDRESS", "Obfuscated email with Lithuanian separators",
         r"\b[\w.+-]+[ \t]+\(eta\)[ \t]+[\w-]+[ \t]+\(taskas\)[ \t]+[a-z]{2,}(?!\w)"),
        ("LT_SALARY", "Salary in a Lithuanian labeled field",
         field_pattern(r"(?:atlyginimas|alga|bruto)", r"\d{3,6}(?:[,.]\d{2})? EUR\b")),
    ]
    return [
        PatternRecognizer(
            supported_entity=entity,
            name=description,
            patterns=[Pattern(description, expression, 0.85)],
            supported_language="en",
            global_regex_flags=regex.MULTILINE,
        )
        for entity, description, expression in rules
    ]


class LithuanianLogAnalyzer(AnalyzerEngine):
    """Apply the log format's known metadata semantics to PERSON detections."""

    def analyze(self, text: str, **kwargs):
        results = super().analyze(text=text, **kwargs)
        metadata_spans = [match.span(1) for match in regex.finditer(
            r"\b(?i:paslauga)[=:][ \t]*([^;\n]+)", text
        )]
        # Only this fixed event vocabulary is metadata, not arbitrary prefix text.
        event = regex.match(
            r"^\S+ (?:INFO|WARN|ERROR) "
            r"(Patikra|Anketa|Sesija|Pranešimas|Kontaktas|Prisijungimas|Siunta|"
            r"Registracija|Užklausa|Pristatymas|Algų eksportas|Užsakymas|Ataskaita):",
            text,
        )
        if event:
            metadata_spans.append(event.span(1))
        return [result for result in results if not (
            result.entity_type == "PERSON" and any(
                start <= result.start and result.end <= end
                for start, end in metadata_spans
            )
        )]


def build_analyzer(mode: str) -> AnalyzerEngine:
    if mode not in {"default", "lithuanian"}:
        raise ValueError(f"Unknown detector mode: {mode}")
    analyzer = AnalyzerEngine() if mode == "default" else LithuanianLogAnalyzer()
    if mode == "lithuanian":
        for recognizer in lithuanian_recognizers():
            analyzer.registry.add_recognizer(recognizer)
    return analyzer


def detect(analyzer: AnalyzerEngine, text: str):
    # Both modes deliberately use the same model, language and threshold.
    return analyzer.analyze(text=text, language="en", score_threshold=0.5)


def redact(analyzer: AnalyzerEngine, text: str) -> str:
    return AnonymizerEngine().anonymize(
        text=text,
        analyzer_results=detect(analyzer, text),
        operators={"DEFAULT": OperatorConfig("replace")},
    ).text
