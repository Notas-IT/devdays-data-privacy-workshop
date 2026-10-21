"""Real SQL and HTTP clients for the cumulative exercises."""

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import psycopg
from psycopg.rows import dict_row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['sql', 'api'])
    parser.add_argument('request')
    parser.add_argument('--anonymous', action='store_true')
    parser.add_argument('--method', default='GET')
    parser.add_argument('--header', action='append', default=[])
    args = parser.parse_args()
    access = json.loads(Path('/run/agent/access.json').read_text())
    if args.mode == 'sql':
        if 'database' not in access:
            raise SystemExit('Direct database credentials are not available in this stage. Use the API.')
        with psycopg.connect(**access['database'], row_factory=dict_row) as connection:
            rows = connection.execute(args.request).fetchall()
        print(json.dumps(rows, default=str))
    else:
        if not args.request.startswith('/') or args.request.startswith('//'):
            raise SystemExit('Use a path on the workshop gateway')
        headers = dict(item.split('=', 1) for item in args.header)
        if not args.anonymous:
            headers['Authorization'] = 'Bearer ' + access['gateway_token']
        request = Request('http://gateway:8000' + args.request, headers=headers, method=args.method)
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            print(json.dumps({'status': response.status,
                'request_id': response.headers.get('X-Request-ID'), 'body': json.loads(response.read())}))


if __name__ == '__main__':
    main()
