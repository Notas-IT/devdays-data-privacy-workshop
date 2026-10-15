# Lithuanian PII In Logs With Presidio

This standalone workshop exercise generates 19 synthetic Lithuanian log cases
and compares unmodified Presidio with additional Lithuanian log recognizers.
It does not need the Postgres dataset or a running database.

The corpus includes personal codes, names with Lithuanian letters, addresses,
birth dates, local mobile numbers, obfuscated emails, and salaries linked to
named employees. A standard email is a positive control. Order numbers, a
budget, a service name, and a short invalid personal code are negative controls.
The personal-code examples are synthetic format examples, not verified issued
identifiers. Email examples use `example.invalid` or the reserved `example.com`
domain. The standard-email control uses `example.com` because the stock
recognizer validates public suffixes and rejects `.invalid`.

## Docker

Run these commands from this workshop directory. This service is independent of
Postgres and requires no local Python installation:

```bash
cd presidio-workshop
```

Build once (downloads dependencies and the approximately 401 MB model):

```bash
docker compose build presidio
```

Run the intentionally failing default validation (exit status 1):

```bash
docker compose run --rm presidio python -m pytest exercises/default_validation.py -q -p no:cacheprovider
```

Run the passing customized test suite (exit status 0):

```bash
docker compose run --rm presidio
```

Compare the default validation report with the customized redacted output:

```bash
docker compose run --rm presidio python scan_logs.py --mode default
docker compose run --rm presidio python scan_logs.py --mode lithuanian --show-redacted
```

The default report exits with status 1; the customized report exits with status
0. Regenerate the fixtures on your machine through the container:

```bash
docker compose run --rm presidio python generate_examples.py
```

The source directory is mounted in the container, so edits and regenerated
examples are immediately available. Rebuild when changing `requirements.txt`
or the Dockerfile. The public suffix list is cached during the build so the
stock email recognizer can run offline. The repository-level Docker setup also
includes this service under the `logs` profile, so the same build and run
commands work from the repository root. Targeting `presidio` explicitly
activates the log exercise.

## Local Python Setup

Run from the repository root with Python 3.10 or newer:

```bash
cd presidio-workshop
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python generate_examples.py
```

The dependencies and the default spaCy model are pinned. The model download is
approximately 401 MB. Detection runs locally; the stock email recognizer may
fetch a public suffix list on its first run, then use its local cache. It can
fall back to the suffix snapshot bundled with its dependency when offline.

## Failing Baseline

```bash
.venv/bin/python -m pytest exercises/default_validation.py -q
```

This is an **intentionally failing** acceptance test: it uses `AnalyzerEngine()`
with the stock recognizers and default `en_core_web_lg` model. Failures are real
assertion failures, not skipped tests or expected-failure markers. The command
must exit with status 1. It is kept outside the normal test suite so routine
verification remains useful.

For a per-log validation report:

```bash
.venv/bin/python scan_logs.py --mode default
```

## Passing Lithuanian Version

```bash
.venv/bin/python -m pytest -q
.venv/bin/python scan_logs.py --mode lithuanian --show-redacted
```

These commands must exit with status 0. `detector.py` adds recognizers through
Presidio's registry, retaining all stock recognizers and the same language
model. The improved analyzer also rejects `PERSON` detections contained in the
known `paslauga` (service) field or a fixed vocabulary of log event labels.
For example, the stock model labels the event word `Patikra` as a person.
Tests ensure metadata validation does not suppress adjacent employees or the
same word within a person field. Both versions use `language="en"`: that is the default model's supported
language, even though the log content is Lithuanian. Registering these patterns
under `en` lets the same pipeline run them; it does not supply Lithuanian NER.

The **validation is unchanged** between versions. Every annotated value must
have an exact matching entity type and character span, and the value must be
absent after Presidio redaction. Partial name or address detections fail.
Negative controls reject specified false-positive entity types.

## Files

| File | Purpose |
| --- | --- |
| `Dockerfile` | Python, pinned packages, language model, and cached email suffix list |
| `generate_examples.py` | Deterministic generator with Lithuanian text and span annotations |
| `examples/lithuanian_logs.jsonl` | Committed fixtures: raw log text and expected entities |
| `examples/lithuanian_logs.log` | The same examples as a readable log file |
| `detector.py` | Stock analyzer, additional recognizers, metadata validation, and redaction |
| `validation.py` | Shared acceptance criteria for both modes |
| `scan_logs.py` | Validation report and optional redacted log output |
| `exercises/default_validation.py` | Explicitly invoked failing baseline test |
| `tests/` | Passing custom validation, controls, and generator reproducibility |

## Workshop Sequence

1. Run the default test and inspect missed entities and partial detections.
2. Review the annotated logs and identify the local formats and field labels.
3. Add or adjust recognizers in `detector.py` without changing the gold labels
   or weakening `validation.py`.
4. Run the passing suite and compare redacted logs.
5. Add unfamiliar fields, inflected names, JSON logs, multiline addresses, and
   misleading labels to test the limits of the solution.

The additional patterns target the included log format. They are not general
Lithuanian language recognition. Personal-code rules check labeled format, not
date validity or checksums; salary rules identify a sensitive financial field,
not a universal PII category. Metadata validation assumes these log events and
the `paslauga` field contain no personal names. The controls measure selected false positives,
not complete precision across arbitrary logs. Passing this corpus does not
establish that all real logs are safe to publish.

Presidio references:
[custom recognizers](https://github.com/microsoft/presidio/blob/main/docs/analyzer/adding_recognizers.md),
[default model configuration](https://github.com/microsoft/presidio/blob/main/presidio-analyzer/presidio_analyzer/conf/default.yaml).
