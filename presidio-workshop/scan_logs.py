"""Validate the annotated log corpus; exit 1 for missed PII or false positives."""

import argparse
from detector import build_analyzer, redact
from validation import load_examples, validate_case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["default", "lithuanian"], required=True)
    parser.add_argument("--show-redacted", action="store_true")
    args = parser.parse_args()
    analyzer = build_analyzer(args.mode)
    cases = load_examples()
    failures = 0
    for case in cases:
        errors = validate_case(analyzer, case)
        failures += bool(errors)
        print(f"{'FAIL' if errors else 'PASS'} {case['id']}")
        for error in errors:
            print(f"  {error}")
        if args.show_redacted:
            print(f"  {redact(analyzer, case['text'])}")
    print(f"{args.mode}: {len(cases) - failures}/{len(cases)} cases passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
