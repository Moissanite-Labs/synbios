"""HTTP integration tests against real Coordinator SQLite state; no browser simulation."""
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from server import DashboardServer, MAX_BODY
from coordinator import canonical_database_path, canonical_workspace_root

BASE = Path(__file__).resolve().parents[1]


class DashboardHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'target'
        self.root.mkdir()
        (self.root / 'source.py').write_text('original source\n')
        self.iso_parent = Path(self.temp.name) / 'iso-candidates'
        self.iso_parent.mkdir()
        self.db = Path(self.temp.name) / 'state.sqlite'
        self.server = DashboardServer(self.db, 0, self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        code, payload, _ = self.request('GET', '/api/session', headers={'X-Lattice-Bootstrap':'1'}, authorized=False)
        self.assertEqual(code, 200)
        self.token = payload['token']

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, data=None, headers=None, authorized=True, raw=None):
        request_headers = {}
        if authorized:
            request_headers['X-Lattice-Token'] = self.token
        if method == 'POST':
            request_headers.update({'Origin':self.server.origin, 'Content-Type':'application/json'})
        request_headers.update(headers or {})
        body = json.dumps(data) if data is not None else raw
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            content = response.read()
            payload = json.loads(content) if response.getheader('Content-Type','').startswith('application/json') else content
            return response.status, payload, dict(response.getheaders())
        finally:
            connection.close()

    def post(self, path, data):
        code, payload, _ = self.request('POST', path, data)
        self.assertEqual(code, 200, payload)
        self.assertTrue(payload['ok'])
        return payload['result']

    def status(self):
        code, payload, _ = self.request('GET', '/api/status')
        self.assertEqual(code, 200, payload)
        return payload['result']

    def cli_status(self):
        command = [sys.executable, str(BASE / 'prototype/coordinator.py'), '--db', str(self.db), 'status']
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)['result']

    def test_full_http_workflow_visible_to_cli_and_no_source_writes(self):
        self.post('/api/actors', {'name':'reviewer'})
        first = self.post('/api/intentions', {'actor':'reviewer', 'reads':[], 'writes':['source.py']})['intention']
        second = self.post('/api/intentions', {'actor':'second', 'reads':['source.py'], 'writes':[]})
        self.assertEqual(len(second['conflicts']), 1)
        alternative = self.post('/api/alternatives', {
            'intent_id': first['id'],
            'label': 'Candidate A',
            'materialize_mode': 'copy',
            'materialize_parent': str(self.iso_parent),
            'materialize_source': str(self.root),
            'candidate_digest': 'a' * 64,
        })
        self.post('/api/alternatives/compare', {'id': alternative['id']})
        self.post('/api/alternatives/status', {'id': alternative['id'], 'status': 'accepted'})
        self.post('/api/intentions/finish', {'id':second['intention']['id'], 'status':'completed'})
        state = self.status()
        cli = self.cli_status()
        for key in ('actors','intentions','alternatives','events','conflicts'):
            self.assertEqual(state[key], cli[key])
        self.assertEqual(state['alternatives'][0]['status'], 'accepted')
        self.assertEqual(state['workspace']['integration_surface']['name'], 'synbios.local_collab.exo_harness')
        self.assertEqual(state['observations'][0]['state'], 'current')
        self.assertEqual(state['conflicts'], [])
        self.assertEqual((self.root / 'source.py').read_text(), 'original source\n')
        self.assertEqual([p.name for p in self.root.iterdir()], ['source.py'])

    def test_stale_and_replacement_capture_actual_file_changes(self):
        initial = self.post('/api/intentions', {'actor':'worker', 'writes':['source.py']})['intention']
        (self.root / 'source.py').write_text('outside edit\n')
        self.assertEqual(self.status()['observations'][0]['state'], 'stale')
        renewed = self.post('/api/intentions', {'actor':'worker', 'writes':['source.py'], 'supersedes':initial['id']})['intention']
        state = self.status()
        self.assertEqual(renewed['revision'], 2)
        self.assertEqual(state['observations'][0]['state'], 'current')
        self.assertEqual(state['intentions'][0]['status'], 'superseded')
        self.assertEqual((self.root / 'source.py').read_text(), 'outside edit\n')

    def test_cross_origin_host_and_capability_denials_do_not_mutate(self):
        before = self.cli_status()['events']
        attempts = [({'Origin':'https://evil.example'}, True), ({'Origin':'null'}, True), ({'Origin':''}, True), ({'Host':'evil.example'}, True), ({'Sec-Fetch-Site':'cross-site'}, True), ({'X-Lattice-Token':'wrong'}, True), ({}, False)]
        for headers, authorized in attempts:
            with self.subTest(headers=headers, authorized=authorized):
                code, _, response_headers = self.request('POST','/api/actors',{'name':'blocked'},headers,authorized)
                self.assertEqual(code,403)
                self.assertNotIn('Access-Control-Allow-Origin',response_headers)
        self.assertEqual(before,self.cli_status()['events'])
        self.assertEqual((self.root / 'source.py').read_text(), 'original source\n')

    def test_missing_origin_and_duplicate_origin_denied(self):
        before = self.cli_status()['events']
        for origins in ([], [self.server.origin,self.server.origin]):
            connection = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
            connection.putrequest('POST','/api/actors')
            connection.putheader('X-Lattice-Token',self.token)
            connection.putheader('Content-Type','application/json')
            for origin in origins:
                connection.putheader('Origin',origin)
            body = b'{"name":"denied"}'
            connection.putheader('Content-Length',str(len(body)))
            connection.endheaders(body)
            response=connection.getresponse()
            self.assertEqual(response.status,403)
            response.read()
            connection.close()
        self.assertEqual(before,self.cli_status()['events'])

    def test_bootstrap_and_read_protection(self):
        for path,headers,expected in [('/api/session',{},403),('/api/session',{'X-Lattice-Bootstrap':'1','Origin':'https://evil.example'},403),('/api/session',{'X-Lattice-Bootstrap':'1','Host':'localhost:'+str(self.server.server_port)},403),('/api/status',{},403)]:
            code,_,_=self.request('GET',path,headers=headers,authorized=False)
            self.assertEqual(code,expected)
        code,_,headers=self.request('OPTIONS','/api/actors',authorized=False)
        self.assertEqual(code,403)
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_invalid_and_oversized_requests_do_not_mutate(self):
        before=self.cli_status()['events']
        for data,headers,raw,expected in [({'name':'bad'},{'Content-Type':'text/plain'},None,415), (None,{},'{',400), ([],{},None,400), ({'name':[]},{},None,400), (None,{},'x'*(MAX_BODY+1),413)]:
            code,_,_=self.request('POST','/api/actors',data,headers,raw=raw)
            self.assertEqual(code,expected)
        self.assertEqual(self.cli_status()['events'],before)

    def test_alternative_requires_intent_id(self):
        first = self.post('/api/intentions', {'actor': 'a', 'reads': [], 'writes': ['source.py']})['intention']
        before = self.cli_status()['events']
        code, payload, _ = self.request('POST', '/api/alternatives', {
            'label': 'orphan',
            'location': str(self.iso_parent / 'noop'),
        })
        self.assertEqual(code, 400)
        self.assertFalse(payload.get('ok'))
        self.assertIn('intent_id', payload.get('error', '').lower())
        self.assertEqual(before, self.cli_status()['events'])

    def test_static_assets_and_path_allowlist(self):
        for path in ['/','/app.js','/style.css']:
            code,body,headers=self.request('GET',path,authorized=False)
            self.assertEqual(code,200)
            self.assertGreater(len(body),100)
            self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertNotIn(self.token.encode(),body)
        for path in ['/../prototype/coordinator.py','/state.sqlite','/api/unknown']:
            code,_,_=self.request('GET',path)
            self.assertEqual(code,404)

    def test_home_relative_database_reopens_for_http_requests(self):
        with patch.dict(os.environ, {'HOME': self.temp.name, 'USERPROFILE': self.temp.name}):
            server = DashboardServer('~/tilde-state.sqlite', 0, self.root)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            try:
                connection.request('GET', '/api/status', headers={'X-Lattice-Token': server.capability})
                response = connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 200, payload)
                expected_root = canonical_workspace_root(self.root)
                self.assertEqual(payload['result']['workspace']['root'], expected_root)
                expected_db = canonical_database_path('~/tilde-state.sqlite')
                self.assertEqual(Path(server.database), expected_db)
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
