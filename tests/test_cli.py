import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from synbios.cli import capture, main, request
from synbios.demo import seed_demo
from synbios.store import Store, verify_bundle


class CLITests(unittest.TestCase):
    def test_capture_clean_root_and_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            def git(*args):
                return subprocess.run(['git', '-C', directory, *args], check=True, capture_output=True).stdout
            git('init', '-q')
            git('config', 'user.name', 'Synthetic')
            git('config', 'user.email', 'synthetic@example.invalid')
            (repo / 'document.txt').write_text('hello\n')
            git('add', '.')
            git('commit', '-qm', 'fixture')
            first = capture(repo, 'task')
            self.assertEqual(len(first['revision']), 40)
            self.assertEqual(first['digest'], hashlib.sha256(git('ls-tree', '-r', '-z', '--full-tree', first['revision'])).hexdigest())
            (repo / 'untracked').write_text('dirty')
            with self.assertRaisesRegex(ValueError, 'clean'):
                capture(repo, 'task')
            (repo / 'untracked').unlink()
            (repo / 'document.txt').write_text('updated\n')
            git('commit', '-qam', 'second')
            second = capture(repo, 'task')
            self.assertNotEqual(first['revision'], second['revision'])
            self.assertNotEqual(first['digest'], second['digest'])
            self.assertEqual(second['digest'], hashlib.sha256(git('ls-tree', '-r', '-z', '--full-tree', second['revision'])).hexdigest())
            main_branch = git('branch', '--show-current').decode().strip()
            git('checkout', '-qb', 'side', first['revision'])
            (repo / 'side.txt').write_text('side\n')
            git('add', '.')
            git('commit', '-qm', 'side')
            git('checkout', '-q', main_branch)
            git('merge', '--no-ff', '-qm', 'merge fixture', 'side')
            merged = capture(repo, 'task')
            self.assertEqual(merged['digest'], hashlib.sha256(git('ls-tree', '-r', '-z', '--full-tree', merged['revision'])).hexdigest())
            for key, value in [('diff.noprefix', 'true'), ('color.diff', 'always'),
                               ('core.abbrev', '5'), ('diff.renames', 'false'),
                               ('diff.algorithm', 'histogram'), ('diff.context', '100')]:
                git('config', key, value)
            hostile = capture(repo, 'task')
            self.assertEqual(merged['revision'], hostile['revision'])
            self.assertEqual(merged['digest'], hostile['digest'])
            for bit in ('assume-unchanged', 'skip-worktree'):
                git('update-index', '--' + bit, 'document.txt')
                (repo / 'document.txt').write_text('hidden dirty\n')
                self.assertEqual(git('status', '--porcelain'), b'')
                with self.assertRaisesRegex(ValueError, 'assume-unchanged or skip-worktree'):
                    capture(repo, 'task')
                git('update-index', '--no-' + bit, 'document.txt')
                git('checkout', '--', 'document.txt')
            original_manifest = git('ls-tree', '-r', '-z', '--full-tree', merged['revision'])
            replacement_tree = git('rev-parse', first['revision'] + '^{tree}').decode().strip()
            replacement = subprocess.run(
                ['git', '-C', directory, 'commit-tree', replacement_tree, '-m', 'Replacement fixture'],
                check=True, capture_output=True).stdout.decode().strip()
            git('replace', merged['revision'], replacement)
            self.assertNotEqual(git('ls-tree', '-r', '-z', '--full-tree', merged['revision']), original_manifest)
            (repo / 'document.txt').touch()
            index = repo / '.git' / 'index'
            index_before = (index.read_bytes(), index.stat().st_mtime_ns)
            protected = capture(repo, 'task')
            self.assertEqual((index.read_bytes(), index.stat().st_mtime_ns), index_before)
            self.assertEqual(protected['revision'], merged['revision'])
            self.assertEqual(protected['digest'], merged['digest'])
            git('replace', '-d', merged['revision'])
            marker = repo / 'unexpected-execution'
            git('config', 'filter.evil.clean', 'touch ' + str(marker) + '; cat')
            with self.assertRaisesRegex(ValueError, 'filters'):
                capture(repo, 'task')
            self.assertFalse(marker.exists())

    def test_demo_and_portable_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / 'demo.db'
            result = seed_demo(db)
            store = Store(db)
            self.addCleanup(store.close)
            state = store.snapshot(result['token'])
            self.assertTrue(result['synthetic'])
            self.assertEqual({t['status'] for t in state['tasks']}, {'accepted', 'in_review', 'open'})
            accepted = next(t for t in state['tasks'] if t['status'] == 'accepted')
            self.assertNotEqual(accepted['reviews'][0]['created_by'], accepted['artifacts'][0]['created_by'])
            bundle = store.export(result['token'], accepted['id'])
            self.assertTrue(verify_bundle(bundle)['valid'])
            file = Path(directory) / 'record.json'
            file.write_text(json.dumps(bundle))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['verify', str(file)]), 0)
            with self.assertRaises(ValueError):
                seed_demo(db)

    def test_client_refuses_nonlocal_origins(self):
        for url in ('https://127.0.0.1', 'http://example.invalid', 'http://0.0.0.0',
                    'http://user@localhost', 'http://localhost?x=1', 'http://localhost/#x',
                    'http://localhost/base'):
            with self.assertRaises(ValueError):
                request(url, 'sensitive-token', '/api/state')

    def test_client_does_not_follow_redirect_or_forward_credential(self):
        received = []
        class Destination(BaseHTTPRequestHandler):
            def do_GET(self):
                received.append(self.headers.get('Authorization'))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{}')
            def log_message(self, *_): pass
        target = ThreadingHTTPServer(('127.0.0.1', 0), Destination)
        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', f'http://127.0.0.1:{target.server_port}/leak')
                self.end_headers()
            def log_message(self, *_): pass
        source = ThreadingHTTPServer(('127.0.0.1', 0), Redirect)
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (target, source)]
        for thread in threads: thread.start()
        try:
            with self.assertRaises(ValueError):
                request(f'http://127.0.0.1:{source.server_port}', 'sensitive-token', '/api/state')
            self.assertEqual(received, [])
        finally:
            for server in (source, target):
                server.shutdown()
                server.server_close()
            for thread in threads: thread.join()

    def test_cli_init(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(['init', '--db', str(Path(directory) / 'new.db')]), 0)
            self.assertTrue(json.loads(out.getvalue())['token'])
