"""Compare two sorted schema descriptions: exit 0=same, 1=different, 2=error."""

import argparse
from difflib import unified_diff
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous', type=Path)
    parser.add_argument('current', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        previous = args.previous.read_text(encoding='utf-8').splitlines(keepends=True)
        current = args.current.read_text(encoding='utf-8').splitlines(keepends=True)
        difference = ''.join(unified_diff(previous, current,
            fromfile=args.previous.name, tofile=args.current.name))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(difference, encoding='utf-8', newline='\n')
    except (OSError, UnicodeError) as error:
        print(f'Could not compare schemas: {error}', file=sys.stderr)
        return 2
    if difference:
        print(difference, end='')
        return 1
    print('Schemas are identical.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
