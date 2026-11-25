#!/usr/bin/env python3
"""Loopback Cloudflare API fixture for the cmail binary. No network access.

Fixtures are re-read from the JSON file on every request so tests can change
them between invocations. GET fixtures are keyed by path (with query); a write
is allowed only by an explicit 'METHOD path' fixture. Special keys:
  _status    HTTP status to return (default 200)
  _body      raw body instead of the JSON fixture
  _sequence  successive responses; the last one repeats
Each request is logged as 'METHOD path ' to the calls file; request bodies of
writes go to the payloads file as JSON lines when one is configured. With an
auth log, each request also appends 'METHOD path HASH': the first 16 hex digits
of SHA-256 over the Authorization header, or 'none' without one, so tests can
prove which credential reached a route without storing it.

`prefix` is stripped from request paths ('/client/v4' for the Cloudflare API;
'' serves other fakes, such as the DNS-over-HTTPS JSON endpoint).
"""
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API_PREFIX = '/client/v4'


class FixtureServer:
    def __init__(self, responses, calls, payloads=None, prefix=API_PREFIX, auth_log=None):
        self.responses = responses
        self.calls = calls
        self.payloads = payloads
        self.prefix = prefix
        self.auth_log = auth_log
        self.counts = {}
        self.lock = threading.Lock()
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self):
                length = int(self.headers.get('Content-Length') or 0)
                body = self.rfile.read(length) if length else b''
                status, text = server.answer(self.command, self.path, body, self.headers.get('Authorization'))
                data = text.encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = handle_any

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return 'http://127.0.0.1:%d%s' % (self.httpd.server_port, self.prefix)

    @staticmethod
    def auth_hash(header):
        return hashlib.sha256(header.encode()).hexdigest()[:16] if header else 'none'

    def answer(self, method, raw_path, body, authorization=None):
        path = raw_path[len(self.prefix):] if self.prefix and raw_path.startswith(self.prefix) else raw_path
        with self.lock:
            with open(self.calls, 'a') as stream:
                stream.write(method + ' ' + path + ' \n')
            if self.auth_log:
                with open(self.auth_log, 'a') as stream:
                    stream.write(method + ' ' + path + ' ' + self.auth_hash(authorization) + '\n')
            if body and self.payloads:
                with open(self.payloads, 'a') as stream:
                    stream.write(json.dumps({'method': method, 'path': path, 'body': json.loads(body)}) + '\n')
            with open(self.responses) as stream:
                responses = json.load(stream)
            key = path if method == 'GET' else method + ' ' + path
            if key not in responses:
                return 500, 'unexpected mutation' if method != 'GET' else 'unexpected endpoint'
            response = responses[key]
            if '_sequence' in response:
                index = self.counts.get(key, 0)
                self.counts[key] = index + 1
                response = response['_sequence'][min(index, len(response['_sequence']) - 1)]
            response = dict(response)
            status = response.pop('_status', 200)
            raw = response.pop('_body', None)
            return status, raw if raw is not None else json.dumps(response)

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()
