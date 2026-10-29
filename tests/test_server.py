import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from synbios.server import create_server, MAX_BODY
from synbios.store import Store


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        store = Store(root / 'test.db')
        self.token = store.bootstrap()['token']
        store.close()
        static = root / 'web'
        static.mkdir()
        (static / 'index.html').write_text('<h1>Forge</h1>')
        self.server = create_server(root / 'test.db', port=0, static_dir=static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def req(self, path, method='GET', body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data

    def test_auth_health_and_static(self):
        self.assertEqual(self.req('/api/health')[0], 200)
        self.assertEqual(self.req('/api/state')[0], 401)
        status, body = self.req('/api/state', headers={'Authorization': 'Bearer ' + self.token})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['version'], 1)
        self.assertEqual(self.req('/tasks/anything')[0], 200)
        self.assertEqual(self.req('/%2e%2e/test.db')[0], 404)
        self.assertEqual(self.req('/missing.js')[0], 404)
        root = Path(self.tmp.name)
        (root / 'web' / 'escape').symlink_to(root / 'test.db')
        self.assertEqual(self.req('/escape')[0], 404)

    def test_origin_host_and_body_guards(self):
        self.assertEqual(self.req('/api/health', headers={'Host': 'evil.invalid'})[0], 403)
        self.assertEqual(self.req('/api/health', headers={'Origin': 'https://evil.invalid'})[0], 403)
        auth = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        self.assertEqual(self.req('/api/commands/project.create', 'POST', '{', auth)[0], 400)
        self.assertEqual(self.req('/api/commands/project.create', 'POST', '[]', auth)[0], 400)
        self.assertEqual(self.req('/api/commands/project.create', 'POST', '{}', {**auth, 'Content-Length': str(MAX_BODY + 1)})[0], 413)
        self.assertEqual(self.req('/api/commands/project.create', 'POST', '{}', {**auth, 'Transfer-Encoding': 'chunked'})[0], 400)

    def test_command_and_events(self):
        status, body = self.req('/api/commands/project.create', 'POST', json.dumps({'name': 'Test', 'description': '', 'repository': ''}), {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)['name'], 'Test')
        self.assertEqual(self.req('/api/events', headers={'Authorization': 'Bearer ' + self.token})[0], 200)

    def test_refuses_public_bind(self):
        with self.assertRaises(ValueError):
            create_server(Path(self.tmp.name) / 'test.db', '0.0.0.0', 0)
