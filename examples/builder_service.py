#!/usr/bin/env python3
"""Disposable loopback-only task API for the build-controller demonstration.

A deterministic fixture, not a production service or a model-generated benchmark.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path

PERSIST = True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--ready', type=Path, required=True)
    args = parser.parse_args()
    items = json.loads(args.store.read_text(encoding='utf-8')) if PERSIST and args.store.exists() else []
    identity = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    run_id = os.environ.get('PROVE_IT_RUN_ID', 'manual-demo')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *values):
            print(fmt % values, flush=True)

        def respond(self, status, value):
            data = json.dumps(value).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('X-Source-SHA256', identity)
            self.send_header('X-Run-ID', run_id)
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            if self.path == '/health': self.respond(200, {'ok': True})
            elif self.path == '/items': self.respond(200, {'items': items})
            else: self.respond(404, {'error': 'not found'})

        def do_POST(self):
            if self.path != '/items': self.respond(404, {'error': 'not found'}); return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 4096: raise ValueError('invalid input size')
                value = json.loads(self.rfile.read(size))
                if not isinstance(value, dict): raise ValueError('object required')
                title = value.get('title')
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
                    raise ValueError('title required')
            except (ValueError, UnicodeError):
                self.respond(400, {'error': 'invalid task'}); return
            item = {'id': len(items) + 1, 'title': title.strip()}; items.append(item)
            if PERSIST:
                temporary = args.store.with_suffix('.tmp')
                temporary.write_text(json.dumps(items), encoding='utf-8')
                os.replace(temporary, args.store)
            self.respond(201, item)

    server = HTTPServer(('127.0.0.1', 0), Handler)
    args.ready.write_text(json.dumps({'url': f'http://127.0.0.1:{server.server_port}',
                                     'pid': os.getpid(), 'sha256': identity, 'run_id': run_id}), encoding='utf-8')
    try: server.serve_forever()
    finally: server.server_close()


if __name__ == '__main__': main()
