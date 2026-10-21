"""The agent's authorized API client; never knows any database credential."""

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def request(path, *, method='GET', headers=None, authenticated=True):
    if not path.startswith('/') or path.startswith('//'):
        raise ValueError('Use a path on the fixed workshop gateway')
    values = dict(headers or {})
    if authenticated:
        token = json.loads(Path('/run/agent/access.json').read_text())['gateway_token']
        values['Authorization'] = 'Bearer ' + token
    call = Request('http://gateway:8000' + path, method=method, headers=values)
    try:
        response = urlopen(call, timeout=5)
    except HTTPError as error:
        response = error
    with response:
        return {'status': response.status, 'request_id': response.headers.get('X-Request-ID'),
                'body': json.loads(response.read())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    parser.add_argument('--method', default='GET')
    parser.add_argument('--anonymous', action='store_true')
    parser.add_argument('--header', action='append', default=[])
    args = parser.parse_args()
    print(json.dumps(request(args.path, method=args.method,
        authenticated=not args.anonymous, headers=dict(item.split('=', 1) for item in args.header))))
