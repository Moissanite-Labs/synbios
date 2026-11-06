import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from synbios.cli import main
from synbios.server import create_server
from synbios.store import Store


class MissionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / 'mission.db'
        store = Store(self.db)
        self.operator = store.bootstrap()['token']
        self.project = store.command(self.operator, 'project.create', {
            'name': 'Exo mission', 'description': 'Coordinate independent agents', 'workspace': '/example/exo',
        })
        store.close()
        static = self.root / 'web'
        static.mkdir()
        (static / 'index.html').write_text('<h1>Crystal Lattice</h1>')
        self.server = create_server(self.db, port=0, static_dir=static)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path, method='GET', data=None, token=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        request_headers = {'Content-Type': 'application/json', **(headers or {})}
        if token:
            request_headers['Authorization'] = 'Bearer ' + token
        body = json.dumps(data) if data is not None else None
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def command(self, action, data, token=None):
        status, result = self.request('/api/commands/' + action, 'POST', data, token or self.operator)
        self.assertEqual(status, 200, result)
        return result

    def create_task(self):
        return self.command('task.create', {
            'project_id': self.project['id'], 'title': 'Improve startup',
            'description': 'Keep sessions independent and visible', 'criteria': ['Startup preserves source files'],
            'scope': ['synbios/cli.py'], 'stage': 'build',
        })

    def test_prompt_routes_use_real_origin_without_credentials(self):
        task = self.create_task()
        worker = self.command('task.delegate', {'task_id': task['id'], 'name': 'CLI agent', 'expected_revision': task['revision']})
        paths = ['/api/tasks/' + task['id'] + '/prompt',
                 '/api/projects/' + self.project['id'] + '/coordinator-prompt']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 401)
                status, result = self.request(path, token=self.operator,
                                              headers={'X-Forwarded-Host': 'attacker.invalid'})
                self.assertEqual(status, 200, result)
                self.assertIn(self.url, result['prompt'])
                self.assertNotIn('attacker.invalid', result['prompt'])
                self.assertNotIn(self.operator, result['prompt'])
                self.assertNotIn(worker['token'], result['prompt'])
                self.assertEqual(self.request(path, token=self.operator, headers={'Host': 'evil.invalid'})[0], 403)
                self.assertEqual(self.request(path, token=self.operator, headers={'Origin': 'https://evil.invalid'})[0], 403)
        status, result = self.request(paths[0], token=worker['token'])
        self.assertEqual(status, 200, result)
        self.assertIn('Improve startup', result['prompt'])
        self.assertEqual(self.request('/api/tasks/unknown/prompt', token=self.operator)[0], 404)

    def test_agent_plan_delegate_report_and_human_decision(self):
        coordinator = self.command('coordinator.enroll', {'project_id': self.project['id'], 'name': 'Mission coordinator'})
        plan = self.command('plan.create', {'project_id': self.project['id'], 'tasks': [
            {'key': 'design', 'title': 'Choose architecture', 'scope': ['docs/'], 'criteria': ['Record agreed interfaces'], 'stage': 'shape'},
            {'key': 'build', 'title': 'Implement runtime', 'scope': ['synbios/'], 'criteria': ['Passing integration checks'], 'stage': 'build', 'dependencies': ['design']},
        ]}, coordinator['token'])
        task = plan['tasks'][0]
        worker = self.command('task.delegate', {'task_id': task['id'], 'name': 'Design agent', 'expected_revision': task['revision']}, coordinator['token'])
        task = worker['task']
        report = {'task_id': task['id'], 'expected_revision': task['revision'], 'summary': 'Compared alternatives', 'progress': 40}
        self.command('task.report', report, worker['token'])
        self.assertEqual(self.request('/api/commands/task.report', 'POST', report, worker['token'])[0], 409)
        status, state = self.request('/api/state', token=worker['token'])
        self.assertEqual(status, 200)
        task = next(t for t in state['tasks'] if t['id'] == task['id'])
        decision = self.command('decision.create', {'task_id': task['id'], 'expected_revision': task['revision'],
            'title': 'Choose storage', 'question': 'Which persistence option fits the mission?', 'options': ['SQLite', 'Files']}, worker['token'])
        _, state = self.request('/api/state', token=self.operator)
        task = next(t for t in state['tasks'] if t['id'] == task['id'])
        resolution = {'task_id': task['id'], 'decision_id': decision['id'], 'expected_revision': task['revision'], 'choice': 'SQLite'}
        self.assertEqual(self.request('/api/commands/decision.resolve', 'POST', resolution, worker['token'])[0], 403)
        self.command('decision.resolve', resolution)
        _, state = self.request('/api/state', token=self.operator)
        task = next(t for t in state['tasks'] if t['id'] == task['id'])
        self.assertEqual(task['decisions'][-1]['status'], 'resolved')
        self.assertNotEqual(task['status'], 'accepted')
        self.assertEqual(state['resources']['telemetry'], 'unavailable')

    def test_cli_json_file_and_prompt_work_against_server(self):
        payload = self.root / 'plan.json'
        payload.write_text(json.dumps({'project_id': self.project['id'], 'tasks': [
            {'key': 'work', 'title': 'A quoted "task"', 'scope': ['src/'], 'criteria': ['Keep newlines\nand quotation intact']},
        ]}), encoding='utf-8')
        with mock.patch.dict(os.environ, {'SYNBIOS_TOKEN': self.operator}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['command', 'plan.create', '--url', self.url, '--data-file', str(payload)]), 0)
        plan = json.loads(output.getvalue())
        task = plan['tasks'][0]
        with mock.patch.dict(os.environ, {'SYNBIOS_TOKEN': self.operator}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['prompt', task['id'], '--url', self.url]), 0)
        self.assertIn('A quoted "task"', output.getvalue())
        self.assertNotIn(self.operator, output.getvalue())
        with mock.patch.dict(os.environ, {'SYNBIOS_TOKEN': self.operator}), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(['coordinator-prompt', self.project['id'], '--url', self.url]), 0)
        self.assertIn('Exo mission', output.getvalue())


if __name__ == '__main__':
    unittest.main()
