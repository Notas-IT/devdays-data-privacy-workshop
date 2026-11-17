"""Call the workshop gateway without displaying its bearer token."""

import argparse
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', help='For example /me or /companies/1/salary-summary')
    parser.add_argument('--anonymous', action='store_true')
    args = parser.parse_args()
    if not args.path.startswith('/') or args.path.startswith('//'):
        parser.error('Use a path on the workshop gateway')
    headers = {}
    if not args.anonymous:
        access = json.loads(Path('/run/identity/access.json').read_text())
        headers['Authorization'] = 'Bearer ' + access['gateway_token']
    request = Request(os.environ['GATEWAY_URL'] + args.path, headers=headers)
    try:
        response = urlopen(request, timeout=10)
    except HTTPError as error:
        response = error
    with response:
        print(json.dumps({'status': response.status,
                          'request_id': response.headers.get('X-Request-ID'),
                          'body': json.load(response)}))
        return 0 if response.status < 400 else 1


if __name__ == '__main__':
    raise SystemExit(main())
