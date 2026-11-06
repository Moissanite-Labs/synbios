#!/usr/bin/env python3
"""Loopback Crystal Lattice dashboard over the shared local Coordinator."""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'prototype'))
from coordinator import Coordinator, PROTOCOL

ASSETS = Path(__file__).resolve().parent
MAX_BODY = 65536


def string(data, key, default=None):
    value = data.get(key, default)
    if value is None and default is not None:
        return default
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError(key + ' must be a string of at most 8192 characters')
    return value


def paths(data, key):
    value = data.get(key, [])
    if not isinstance(value, list) or len(value) > 128 or any(not isinstance(p, str) or len(p) > 4096 for p in value):
        raise ValueError(key + ' must be a list of at most 128 path strings')
    return value


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, database, port=7343, root=None):
        coordinator = Coordinator(database, root)
        self.database = str(coordinator.database)
        coordinator.close()
        self.capability = secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = 'http://127.0.0.1:' + str(self.server_port)


class Handler(BaseHTTPRequestHandler):
    server_version = 'CrystalLattice/1'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, format, *args):
        # Avoid printing request paths, headers, bodies, or capabilities.
        pass

    def reply(self, code, value, content_type='application/json; charset=utf-8'):
        body = json.dumps(value).encode() if content_type.startswith('application/json') else value
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def error(self, code, message):
        self.close_connection = True
        self.reply(code, {'ok': False, 'error': message})

    def boundary(self, mutation=False):
        hosts = self.headers.get_all('Host', [])
        origins = self.headers.get_all('Origin', [])
        if hosts != [self.server.origin.removeprefix('http://')]:
            self.error(403, 'Unexpected Host; use the printed 127.0.0.1 URL')
            return False
        if (origins and origins != [self.server.origin]) or (mutation and origins != [self.server.origin]):
            self.error(403, 'Same-origin request required')
            return False
        if self.headers.get('Sec-Fetch-Site', 'same-origin') not in ('same-origin', 'none'):
            self.error(403, 'Cross-site requests are not allowed')
            return False
        return True

    def authorized(self):
        token = self.headers.get('X-Lattice-Token', '')
        if not hmac.compare_digest(token.encode('utf-8'), self.server.capability.encode('ascii')):
            self.error(403, 'Dashboard capability required; reload the page')
            return False
        return True

    def do_GET(self):
        if not self.boundary():
            return
        path = urlsplit(self.path).path
        if path == '/api/session':
            if self.headers.get('X-Lattice-Bootstrap') != '1':
                self.error(403, 'Same-origin bootstrap header required')
                return
            self.reply(200, {'ok': True, 'token': self.server.capability, 'protocol': PROTOCOL})
            return
        if path == '/api/status':
            if not self.authorized():
                return
            self.run_coordinator(lambda c: c.status())
            return
        assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/app.js': ('app.js', 'text/javascript; charset=utf-8'), '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if path not in assets:
            self.error(404, 'Not found')
            return
        name, mime = assets[path]
        self.reply(200, (ASSETS / name).read_bytes(), mime)

    def do_POST(self):
        if not self.boundary(mutation=True) or not self.authorized():
            return
        if self.headers.get_content_type() != 'application/json':
            self.error(415, 'JSON requests only')
            return
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get('Transfer-Encoding') or len(lengths) != 1:
            self.error(400, 'One Content-Length header required; no transfer encoding')
            return
        try:
            length = int(lengths[0])
        except ValueError:
            self.error(400, 'Invalid Content-Length')
            return
        if length < 1 or length > MAX_BODY:
            self.error(413, 'Request body must be 1–65536 bytes')
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete request body')
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
            path = urlsplit(self.path).path
            if path == '/api/intentions':
                supersedes = data.get('supersedes')
                if supersedes is not None:
                    supersedes = string(data, 'supersedes')
                operation = lambda c: c.declare(string(data, 'actor'), paths(data, 'reads'), paths(data, 'writes'), supersedes)
            elif path == '/api/intentions/finish':
                operation = lambda c: c.finish(string(data, 'id'), string(data, 'status'))
            elif path == '/api/alternatives':
                intent_ref = data.get('intent_id')
                if intent_ref is None or (isinstance(intent_ref, str) and not intent_ref.strip()):
                    raise ValueError('intent_id is required')
                candidate_digest = data.get('candidate_digest')
                if candidate_digest is not None:
                    candidate_digest = string(data, 'candidate_digest')
                mode = data.get('materialize_mode') or data.get('materialize')
                if mode is not None and mode != '':
                    mode = string(data, 'materialize_mode') if 'materialize_mode' in data else string(data, 'materialize')
                    parent = string(data, 'materialize_parent')
                    src = data.get('materialize_source')
                    src = string(data, 'materialize_source') if src is not None else None
                    operation = lambda c, m=mode, p=parent, s=src: c.alternative(
                        string(data, 'intent_id'),
                        string(data, 'label'),
                        string(data, 'location', ''),
                        string(data, 'status', 'proposed'),
                        candidate_digest,
                        materialize_mode=m,
                        materialize_parent=p,
                        materialize_source=s,
                    )
                else:
                    operation = lambda c: c.alternative(
                        string(data, 'intent_id'),
                        string(data, 'label'),
                        string(data, 'location'),
                        string(data, 'status', 'proposed'),
                        candidate_digest,
                    )
            elif path == '/api/alternatives/compare':
                operation = lambda c: c.compare_alternative(string(data, 'id'))
            elif path == '/api/alternatives/status':
                operation = lambda c: c.alternative_status(string(data, 'id'), string(data, 'status'))
            elif path == '/api/actors':
                operation = lambda c: c.register_actor(string(data, 'name'))
            else:
                self.error(404, 'Unknown operation')
                return
            self.run_coordinator(operation)
        except (ValueError, UnicodeError) as error:
            self.error(400, str(error))
        except TimeoutError:
            self.error(408, 'Request body timed out')

    def do_OPTIONS(self):
        self.error(403, 'Cross-origin access is not supported')

    def run_coordinator(self, operation):
        coordinator = None
        try:
            coordinator = Coordinator(self.server.database)
            result = operation(coordinator)
            self.reply(200, {'ok': True, 'protocol': PROTOCOL, 'result': result})
        except (ValueError, OSError, sqlite3.Error) as error:
            self.error(400, str(error))
        finally:
            if coordinator:
                coordinator.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='SQLite path outside target workspace')
    parser.add_argument('--root', help='Initialize the database for this existing folder')
    parser.add_argument('--port', type=int, default=7343)
    args = parser.parse_args()
    try:
        server = DashboardServer(args.db, args.port, args.root)
    except (ValueError, OSError, sqlite3.Error) as error:
        parser.exit(1, str(error) + '\n')
    print('Crystal Lattice: ' + server.origin + '/', flush=True)
    print('Local coordination only. Actor names are caller-asserted. Ctrl+C stops the server.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
