"""Loopback-only HTTP transport for the local Forge."""
import ipaddress
import json
import mimetypes
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, unquote

from .store import Store, verify_bundle

MAX_BODY = 1024 * 1024


def create_server(db, host='127.0.0.1', port=8765, static_dir=None):
    if host != 'localhost':
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError('Server binding must be loopback')
        except ValueError as exc:
            raise ValueError('Server binding must be loopback') from exc
    store = Store(db)
    root = Path(static_dir or Path(__file__).resolve().parent.parent / 'web' / 'dist').resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # URLs and credentials do not belong in the console.

        def send(self, status, body, content_type='application/json'):
            data = json.dumps(body).encode() if content_type == 'application/json' else body
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(data)

        def guard(self):
            hosts = self.headers.get_all('Host', [])
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}', f'[::1]:{self.server.server_port}'}
            if len(hosts) != 1 or hosts[0] not in allowed:
                self.send(403, {'error': 'Invalid Host'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + hosts[0]:
                self.send(403, {'error': 'Cross-origin request refused'})
                return False
            return True

        def token(self):
            auth = self.headers.get('Authorization', '')
            token = auth[7:] if auth.startswith('Bearer ') else ''
            store.authenticate(token)
            return token

        def body(self):
            if self.headers.get('Transfer-Encoding'):
                raise RequestError(400, 'Transfer encoding is not supported')
            lengths = self.headers.get_all('Content-Length', [])
            if len(lengths) != 1:
                raise RequestError(400, 'Content-Length required')
            try:
                size = int(lengths[0])
            except ValueError:
                raise RequestError(400, 'Invalid Content-Length')
            if not 0 <= size <= MAX_BODY:
                raise RequestError(413, 'Request body too large')
            if self.headers.get_content_type() != 'application/json':
                raise RequestError(415, 'Expected application/json')
            self.connection.settimeout(10)
            try:
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise ValueError()
                value = json.loads(raw)
            except (ValueError, UnicodeError):
                raise RequestError(400, 'Invalid JSON')
            if not isinstance(value, dict):
                raise RequestError(400, 'Expected JSON object')
            return value

        def dispatch(self):
            if not self.guard():
                return
            path = urlsplit(self.path).path
            if self.command == 'GET' and path == '/.well-known/synbios.json':
                from .protocol import discovery_document
                return self.send(200, discovery_document())
            if self.command == 'GET' and path == '/api/health':
                return self.send(200, {'ok': True, 'version': 1})
            if path.startswith('/api/'):
                token = self.token()
                if self.command == 'GET' and path == '/api/schema':
                    from .protocol import openapi_document
                    return self.send(200, openapi_document())
                if self.command == 'GET' and path == '/api/state':
                    return self.send(200, store.snapshot(token))
                if self.command == 'GET' and path == '/api/events':
                    return self.send(200, store.snapshot(token)['events'])
                if self.command == 'GET' and path.startswith('/api/tasks/') and path.endswith('/export'):
                    task_id = unquote(path[len('/api/tasks/'):-len('/export')])
                    return self.send(200, store.export(token, task_id))
                if self.command == 'POST' and path.startswith('/api/commands/'):
                    return self.send(200, store.command(token, path[len('/api/commands/'):], self.body()))
                if self.command == 'POST' and path == '/api/bundles/verify':
                    return self.send(200, verify_bundle(self.body()))
                return self.send(404, {'error': 'Unknown API route'})
            if self.command != 'GET':
                return self.send(405, {'error': 'Method not allowed'})
            decoded = unquote(path)
            if '\\' in decoded or '\x00' in decoded or '..' in decoded.split('/'):
                return self.send(404, {'error': 'Not found'})
            target = (root / decoded.lstrip('/')).resolve()
            if not target.is_relative_to(root):
                return self.send(404, {'error': 'Not found'})
            if not target.is_file():
                if Path(decoded).suffix:
                    return self.send(404, {'error': 'Not found'})
                target = (root / 'index.html').resolve()
            if not target.is_relative_to(root):
                return self.send(404, {'error': 'Not found'})
            if not target.is_file():
                return self.send(404, {'error': 'Web client not built; run npm run build in web/'})
            return self.send(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or 'application/octet-stream')

        def handle_request(self):
            try:
                self.dispatch()
            except Exception as exc:
                status = getattr(exc, 'status', 500)
                self.send(status, {'error': str(exc) if status != 500 else 'Internal server error'})
        do_GET = handle_request
        do_POST = handle_request
        do_OPTIONS = handle_request

    class LocalServer(ThreadingHTTPServer):
        def server_close(self):
            super().server_close()
            store.close()

    server_class = LocalServer
    if ':' in host:
        class IPv6Server(LocalServer):
            address_family = socket.AF_INET6
        server_class = IPv6Server
    server = server_class((host, port), Handler)
    server.daemon_threads = True
    return server


class RequestError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
