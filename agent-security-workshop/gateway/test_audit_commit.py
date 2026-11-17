"""Isolated handler tests: commit ordering and a simulated commit failure."""

from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import gateway
import psycopg


class Connection:
    def __init__(self, fail_commit):
        self.fail_commit = fail_commit
        self.inserted = False
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            if self.fail_commit:
                raise psycopg.OperationalError('Simulated commit failure')
            self.committed = True

    def execute(self, query, params=None):
        if 'authenticate' in query:
            self.row = {'actor': 'workshop-agent', 'company_id': 1}
        elif 'salary_summary' in query:
            self.row = {'company_id': 1, 'employee_count': 3, 'average_salary_eur': 4000}
        elif 'INSERT INTO lab_audit.events' in query:
            self.inserted = True
        else:
            raise AssertionError('Unexpected test SQL')
        return self

    def fetchone(self):
        return self.row


class AuditCommitTest(unittest.TestCase):
    def exercise(self, fail_commit):
        connection = Connection(fail_commit)
        sent = []
        original_reply = gateway.Handler.reply

        def observe_reply(handler, status, body, request_id):
            sent.append((status, connection.inserted, connection.committed))
            original_reply(handler, status, body, request_id)

        with patch.object(gateway.psycopg, 'connect', return_value=connection), \
             patch.object(gateway.Handler, 'reply', observe_reply):
            server = ThreadingHTTPServer(('127.0.0.1', 0), gateway.Handler)
            thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=0.01))
            thread.start()
            try:
                request = Request(f'http://127.0.0.1:{server.server_port}/companies/1/salary-summary',
                                  headers={'Authorization': 'Bearer local-test-token'})
                try:
                    response = urlopen(request, timeout=5)
                except HTTPError as error:
                    response = error
                with response:
                    body = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
        return sent, body

    def test_success_is_sent_only_after_audit_commit(self):
        sent, body = self.exercise(False)
        self.assertEqual(sent, [(200, True, True)])
        self.assertEqual(body['company_id'], 1)

    def test_commit_failure_withholds_computed_salary_data(self):
        sent, body = self.exercise(True)
        self.assertEqual(sent, [(503, True, False)])
        self.assertEqual(body, {'error': 'Database or audit unavailable'})


if __name__ == '__main__':
    unittest.main()
