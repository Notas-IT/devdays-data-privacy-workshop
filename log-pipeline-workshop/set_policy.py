"""Change the active policy atomically without restarting the processor."""

import argparse
from pathlib import Path


def activate(name):
    directory = Path(__file__).parent / "config"
    content = (directory / "policies" / f"{name}.json").read_bytes()
    temporary = directory / "active.tmp"
    temporary.write_bytes(content)
    temporary.replace(directory / "active.json")
    print(f"Activated {name} policy; processor will reload within one polling cycle")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", choices=["strict", "presidio", "invalid"])
    args = parser.parse_args()
    activate(args.policy)


if __name__ == "__main__":
    main()
