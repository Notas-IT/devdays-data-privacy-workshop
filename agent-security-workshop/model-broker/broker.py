"""Credential-injecting Responses proxy, not a general outbound HTTP proxy."""

import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, HTTPRedirectHandler, Request

UPSTREAM = 'https://api.openai.com/v1/responses'


def local_tools_only(tools):
    if not isinstance(tools, list):
        return False
    for tool in tools:
        if not isinstance(tool, dict):
            return False
        if tool.get('type') in ('function', 'custom'):
            continue
        if tool.get('type') == 'namespace' and local_tools_only(tool.get('tools')):
            continue
        return False
    return True


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def handler_factory(token, api_key, model, *, limit=60, opener=None):
    counter = [0]
    lock = threading.Lock()
    open_upstream = opener or build_opener(NoRedirect()).open

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/health':
                configured = bool(api_key and model)
                self.respond(200 if configured else 503,
                    {'status': 'ok' if configured else 'unconfigured', 'configured': configured})
            else:
                self.respond(404, {'error': 'No such broker endpoint'})

        def do_POST(self):
            if self.path != '/v1/responses':
                self.respond(404, {'error': 'Only the Responses endpoint is available'})
                return
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.respond(401, {'error': 'Invalid broker credential'})
                return
            if self.headers.get('Content-Encoding', 'identity') != 'identity':
                self.respond(415, {'error': 'Compressed model requests are not supported'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 2_000_000:
                    self.respond(413, {'error': 'Model request length must be between 1 and 2000000 bytes'})
                    return
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or body.get('model') != model:
                    self.respond(400, {'error': 'Model name is not allowed'})
                    return
                # The CLI may use local function/custom tools, not upstream
                # web/file/computer tools with separate data/egress capabilities.
                if not local_tools_only(body.get('tools', [])):
                    self.respond(400, {'error': 'Unsupported upstream tool type',
                        'detail': 'Only local function/custom tools and their namespaces are allowed'})
                    return
                body['store'] = False
                body['max_output_tokens'] = min(int(body.get('max_output_tokens', 4096)), 4096)
                if body['max_output_tokens'] <= 0:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                self.respond(400, {'error': 'Invalid or disallowed model request'})
                return
            if not api_key or not model:
                self.respond(503, {'error': 'Presenter has not configured the model provider'})
                return
            with lock:
                if counter[0] >= limit:
                    self.respond(429, {'error': 'Workshop model request budget exhausted'})
                    return
                counter[0] += 1
            call = Request(UPSTREAM, data=json.dumps(body).encode(), headers={
                'Authorization': 'Bearer ' + api_key, 'Content-Type': 'application/json',
                'Accept': 'text/event-stream' if body.get('stream') else 'application/json'})
            try:
                response = open_upstream(call, timeout=90)
                with response:
                    self.send_response(response.status)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while chunk := response.read1(65536):
                        self.wfile.write(chunk)
                        self.wfile.flush()
                    self.close_connection = True
            except HTTPError as error:
                # Upstream error bodies/headers may include provider metadata.
                self.respond(502, {'error': 'Model provider rejected the request', 'provider_status': error.code})
            except (URLError, TimeoutError):
                self.respond(502, {'error': 'Model provider unavailable'})
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_CONNECT(self):
            self.respond(405, {'error': 'General outbound proxying is disabled'})

    return Handler


if __name__ == '__main__':
    token = json.loads(Path('/run/broker/access.json').read_text())['model_token']
    handler = handler_factory(token, os.environ.get('OPENAI_API_KEY', ''),
        os.environ.get('OPENAI_MODEL', ''), limit=int(os.environ.get('MODEL_REQUEST_LIMIT', '60')))
    ThreadingHTTPServer(('0.0.0.0', 8081), handler).serve_forever()
