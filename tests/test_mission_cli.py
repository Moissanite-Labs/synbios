import contextlib
import io
import json
import os
from pathlib import Path
import queue
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from synbios.cli import main, prepare_workspace, request
from synbios.store import Store, DomainError


class MissionLauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.workspace = self.root / 'existing source with spaces'
        self.workspace.mkdir()
        (self.workspace / 'uncommitted.txt').write_text('Keep this work.\n')
        self.state = self.root / 'private-state'
        self.environment = mock.patch.dict(os.environ, {'SYNBIOS_STATE_DIR': str(self.state), 'SYNBIOS_TOKEN': ''})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def source_files(self):
        return {str(p.relative_to(self.workspace)): p.read_bytes() for p in self.workspace.rglob('*') if p.is_file()}

    def test_first_start_and_restart_preserve_mission_and_source(self):
        before = self.source_files()
        first = prepare_workspace(self.workspace, name='Exo mission')
        store = Store(first['db'])
        self.addCleanup(store.close)
        state = store.snapshot(first['token'])
        second = prepare_workspace(self.workspace)
        self.assertEqual(first['token'], second['token'])
        self.assertEqual(first['project']['id'], second['project']['id'])
        self.assertEqual(state['events'], store.snapshot(second['token'])['events'])
        self.assertEqual(second['project']['name'], 'Exo mission')
        self.assertEqual(second['project']['workspace'], str(self.workspace.resolve()))
        self.assertEqual(self.source_files(), before)
        self.assertFalse(Path(first['db']).is_relative_to(self.workspace))
        self.assertNotIn(first['token'].encode(), Path(first['db']).read_bytes())
        credential = Path(first['credential_file'])
        self.assertEqual(json.loads(credential.read_text())['token'], first['token'])
        if os.name != 'nt':
            self.assertEqual(stat.S_IMODE(credential.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(Path(first['db']).stat().st_mode), 0o600)

    def test_existing_store_requires_current_human_credential(self):
        db = self.root / 'existing.db'
        store = Store(db)
        self.addCleanup(store.close)
        operator = store.bootstrap()['token']
        agent = store.command(operator, 'principal.create', {'name': 'Worker', 'kind': 'agent'})
        before = store.snapshot(operator)['events']
        with self.assertRaisesRegex(ValueError, 'SYNBIOS_TOKEN'):
            prepare_workspace(self.workspace, db)
        with self.assertRaisesRegex(ValueError, 'operator credential'):
            prepare_workspace(self.workspace, db, token=agent['token'])
        self.assertEqual(store.snapshot(operator)['events'], before)
        started = prepare_workspace(self.workspace, db, token=operator)
        resumed = prepare_workspace(self.workspace, db)
        self.assertEqual(started['project']['id'], resumed['project']['id'])
        # A cached credential does not bypass normal revocation.
        other = store.command(operator, 'principal.create', {'name': 'Other operator', 'kind': 'human'})
        actor = store.snapshot(operator)['actor']['id']
        store.command(other['token'], 'principal.revoke', {'principal_id': actor})
        with self.assertRaises(DomainError):
            prepare_workspace(self.workspace, db)

    def test_paths_reject_source_state_and_symlink_database(self):
        before = self.source_files()
        with self.assertRaisesRegex(ValueError, 'outside'):
            prepare_workspace(self.workspace, self.workspace / 'mission.db')
        with mock.patch.dict(os.environ, {'SYNBIOS_STATE_DIR': str(self.workspace / '.state')}):
            with self.assertRaisesRegex(ValueError, 'outside'):
                prepare_workspace(self.workspace, self.root / 'mission.db')
        with self.assertRaisesRegex(ValueError, 'existing folder'):
            prepare_workspace(self.root / 'missing')
        self.assertEqual(self.source_files(), before)
        self.assertFalse(self.state.exists())
        if os.name != 'nt':
            actual = self.root / 'actual.db'
            actual.write_bytes(b'untouched')
            link = self.root / 'linked.db'
            link.symlink_to(actual)
            with self.assertRaisesRegex(ValueError, 'symlinks'):
                prepare_workspace(self.workspace, link)
            self.assertEqual(actual.read_bytes(), b'untouched')

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions and symlinks')
    def test_cache_must_remain_private_and_regular(self):
        first = prepare_workspace(self.workspace)
        cache = Path(first['credential_file'])
        cache.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'private'):
            prepare_workspace(self.workspace)
        cache.chmod(0o600)
        contents = cache.read_bytes()
        cache.unlink()
        target = self.root / 'secret-copy'
        target.write_bytes(contents)
        cache.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            prepare_workspace(self.workspace)

    def test_missing_build_fails_before_creating_state(self):
        with mock.patch('synbios.cli.WEB_BUILD', self.root / 'absent-build'), contextlib.redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main(['start', '--workspace', str(self.workspace)]), 1)
        self.assertIn('npm --prefix web run build', error.getvalue())
        self.assertFalse(self.state.exists())

    def test_busy_port_keeps_credentials_for_retry(self):
        web = self.root / 'web'
        web.mkdir()
        (web / 'index.html').write_text('<h1>Crystal Lattice</h1>')
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen()
            with mock.patch('synbios.cli.WEB_BUILD', web), contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['start', '--workspace', str(self.workspace), '--port', str(occupied.getsockname()[1])]), 1)
        recovered = prepare_workspace(self.workspace)
        self.assertTrue(recovered['token'])
        self.assertEqual(recovered['project']['workspace'], str(self.workspace.resolve()))

    def test_failed_credential_save_rolls_back_only_new_bootstrap(self):
        db = self.root / 'new.db'
        with mock.patch('synbios.cli.os.replace', side_effect=OSError('No space for credential')):
            with self.assertRaisesRegex(OSError, 'No space'):
                prepare_workspace(self.workspace, db)
        self.assertFalse(db.exists())
        first = prepare_workspace(self.workspace, db)
        with mock.patch('synbios.cli.os.replace', side_effect=OSError('No space for credential')):
            with self.assertRaisesRegex(OSError, 'No space'):
                prepare_workspace(self.workspace, db, token=first['token'])
        self.assertTrue(db.exists())
        self.assertEqual(prepare_workspace(self.workspace, db)['token'], first['token'])

    def test_real_cli_launch_serves_saved_workspace(self):
        web = self.root / 'web'
        web.mkdir()
        (web / 'index.html').write_text('<h1>Crystal Lattice</h1>')
        script = (
            'import sys; from pathlib import Path; import synbios.cli as cli; '
            'cli.WEB_BUILD=Path(sys.argv[1]); '
            'sys.exit(cli.main(["start","--workspace",sys.argv[2],"--port","0"]))'
        )
        process = subprocess.Popen([sys.executable, '-u', '-c', script, str(web), str(self.workspace)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=os.environ.copy())
        output = queue.Queue()
        def read_lines():
            for line in process.stdout:
                output.put(line.rstrip('\n'))
            output.put(None)
        reader = threading.Thread(target=read_lines, daemon=True)
        reader.start()
        try:
            lines = []
            for _ in range(7):
                line = output.get(timeout=15)
                self.assertIsNotNone(line, 'Launcher exited before reporting readiness')
                lines.append(line)
            url = next(line[5:] for line in lines if line.startswith('Open '))
            token = lines[lines.index('Paste this private operator token into the local sign-in screen:') + 1]
            state = request(url, token, '/api/state')
            self.assertEqual(len(state['projects']), 1)
            self.assertEqual(state['projects'][0]['workspace'], str(self.workspace.resolve()))
            self.assertEqual(state['tasks'], [])
            self.assertNotIn(token, url)
            self.assertEqual(self.source_files(), {'uncommitted.txt': b'Keep this work.\n'})
        finally:
            process.terminate()
            process.wait(timeout=10)
            reader.join(timeout=2)
            process.stdout.close()
            process.stderr.close()
        self.assertEqual(prepare_workspace(self.workspace)['token'], token)


if __name__ == '__main__':
    unittest.main()
