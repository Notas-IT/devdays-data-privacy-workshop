"""Check deployed broker controls without forwarding a paid model request."""

import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    access = json.loads(Path('/run/agent/access.json').read_text())
    if set(access) != {'model', 'model_token'}:
        sys.exit('FAIL: agent model configuration contains unexpected credential fields')
    if any(os.environ.get(name) for name in
           ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPEN_AI_API', 'OPEN_AI_API_KEY')):
        sys.exit('FAIL: provider credentials are present in the agent environment')
    if any(Path(path).exists() for path in ('/workspace/.env', '/run/credentials/agent.env',
                                           '/run/broker/access.json', '/state/model-usage.sqlite3')):
        sys.exit('FAIL: provider or broker-only files are exposed to the agent')
    print('PASS: agent has only local proxy credentials', flush=True)
    base = os.environ['MODEL_PROXY_URL']

    def call(path, expected, body=None, authenticated=True):
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            headers['Authorization'] = 'Bearer ' + access['model_token']
        request = Request(base + path, headers=headers,
                          data=json.dumps(body).encode() if body is not None else None)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            if response.status != expected:
                sys.exit(f'FAIL: {path} returned {response.status}, expected {expected}')
            return json.load(response)

    policy = call('/policy', 200)
    if policy['upstream'] != 'https://api.openai.com/v1/responses' or policy['model'] != access['model']:
        sys.exit('FAIL: endpoint or model policy does not match the workshop configuration')
    print('PASS: OpenAI Responses endpoint and allowed model are pinned', flush=True)
    if (policy['request_limit'] != 60 or policy['max_output_tokens'] != 4096
            or policy['max_request_bytes'] != 2_000_000 or not policy['persistent_budget']
            or not 0 <= policy['requests_used'] <= policy['request_limit']
            or policy['requests_remaining'] != policy['request_limit'] - policy['requests_used']):
        sys.exit('FAIL: persistent request or token limits are missing')
    print(f"PASS: persistent budget {policy['requests_used']}/60; output cap 4096 tokens", flush=True)

    call('/v1/responses', 401, {'model': access['model']}, authenticated=False)
    print('PASS: missing proxy credentials are rejected', flush=True)
    call('/v1/responses', 400, {'model': access['model'] + '-not-allowed'})
    print('PASS: other models are rejected', flush=True)
    call('/v1/chat/completions', 404, {'model': access['model']})
    print('PASS: other upstream endpoints are rejected', flush=True)
    call('/v1/responses', 400, {'model': access['model'], 'tools': [{'type': 'web_search'}]})
    call('/v1/responses', 400, {'model': access['model'], 'max_output_tokens': True})
    call('/v1/responses', 400, {'model': access['model'], 'background': True})
    print('PASS: hosted tools, malformed token limits and background work are rejected', flush=True)
    print('PASS: model broker checks passed; no paid model request was sent')


if __name__ == '__main__':
    main()
