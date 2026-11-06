"""Explicit local administration and authenticated API client."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import stat
import sqlite3
import subprocess
import sys
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError

WEB_BUILD = Path(__file__).resolve().parent.parent / 'web' / 'dist'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


def app_state_dir():
    """Keep mission state out of the code being coordinated."""
    if os.getenv('SYNBIOS_STATE_DIR'):
        return Path(os.environ['SYNBIOS_STATE_DIR']).expanduser().resolve()
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'Synbios'
    if os.name == 'nt':
        return Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local'))) / 'Synbios'
    return Path(os.getenv('XDG_STATE_HOME', str(Path.home() / '.local' / 'state'))) / 'synbios'


def prepare_workspace(workspace, db=None, name=None, token=None):
    """Initialize/reopen a mission without altering files in its working folder.

    The launcher retains its operator credential in a private client file. The
    database still stores only a credential hash. Existing databases without a
    launcher credential require an explicit SYNBIOS_TOKEN; there is no reset or
    credential recovery here.
    """
    from .store import Store
    root = Path(workspace).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Workspace must be an existing folder')
    state_root = app_state_dir().resolve()
    workspace_key = hashlib.sha256(str(root).encode()).hexdigest()[:20]
    path = Path(db).expanduser().absolute() if db else state_root / 'workspaces' / workspace_key / 'mission.db'
    if path.is_symlink():
        raise ValueError('Database symlinks are not supported')
    path = path.resolve()
    credential_key = hashlib.sha256(str(path).encode()).hexdigest()
    credential_path = state_root / 'credentials' / (credential_key + '.json')
    if path.is_relative_to(root) or credential_path.resolve().is_relative_to(root):
        raise ValueError('Mission state must be outside the workspace. Choose --db and SYNBIOS_STATE_DIR outside that folder.')
    if credential_path.is_symlink():
        raise ValueError('Launcher credential symlinks are not supported')
    existed = path.exists()
    supplied_token = token or os.getenv('SYNBIOS_TOKEN', '')
    if existed and not supplied_token and credential_path.exists():
        info = credential_path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise ValueError('Launcher credential must be a regular file')
        if os.name != 'nt' and stat.S_IMODE(info.st_mode) & 0o077:
            raise ValueError('Launcher credential permissions must be private (chmod 600 the credential file)')
        try:
            cached = json.loads(credential_path.read_text(encoding='utf-8'))
            supplied_token = cached['token']
            if cached.get('version') != 1 or not isinstance(supplied_token, str) or not supplied_token:
                raise ValueError()
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError('Invalid launcher credential file; provide a current operator SYNBIOS_TOKEN') from exc
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    credential_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    store = Store(path)
    database_identity = (path.stat().st_dev, path.stat().st_ino)
    created_credential = False
    try:
        if not existed:
            supplied_token = store.bootstrap('Local operator')['token']
            created_credential = True
        elif not supplied_token:
            raise ValueError('Existing database needs its operator credential. Set SYNBIOS_TOKEN, then rerun start. No credentials were reset.')
        snapshot = store.snapshot(supplied_token)
        if snapshot['actor']['kind'] != 'human':
            raise ValueError('Starting mission control requires an operator credential, not an agent credential')
        # Save once, and replace only after an explicitly supplied credential has
        # authenticated. Atomic publication never exposes a partially written
        # token. The directory and file are private on POSIX; Windows inherits
        # the user's local application-data access controls.
        if created_credential or token or os.getenv('SYNBIOS_TOKEN'):
            import tempfile
            temporary = None
            try:
                descriptor, temporary = tempfile.mkstemp(prefix='.credential-', dir=credential_path.parent)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                    json.dump({'version': 1, 'token': supplied_token}, output)
                    output.write('\n')
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, credential_path)
            except OSError:
                if created_credential:
                    # No project or tasks exist yet. Roll back only the new
                    # database this invocation bootstrapped, never an existing
                    # store or a file that replaced ours during initialization.
                    store.close()
                    store = None
                    current = path.stat()
                    if (current.st_dev, current.st_ino) == database_identity:
                        path.unlink()
                raise
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
        project = next((p for p in snapshot['projects']
                        if p.get('workspace') == str(root) or p.get('repository') == str(root)), None)
        if project is None:
            project = store.command(supplied_token, 'project.create', {
                'name': name or root.name or 'Local mission',
                'description': 'Coordinate work in this folder. Add your desired outcome and first work slice.',
                'repository': str(root), 'workspace': str(root),
            })
        return {'db': str(path), 'workspace': str(root), 'project': project,
                'token': supplied_token, 'credential_file': str(credential_path)}
    finally:
        if store is not None:
            store.close()


def request(url, token, path, data=None):
    parsed = urlsplit(url)
    try:
        local = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        local = False
    if (parsed.scheme != 'http' or not local or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')):
        raise ValueError('API URL must be a loopback HTTP origin without userinfo, path, query or fragment')
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError('Invalid API port') from exc
    headers = {'Authorization': 'Bearer ' + token}
    raw = None
    if data is not None:
        raw = json.dumps(data).encode()
        headers['Content-Type'] = 'application/json'
    req = Request(url.rstrip('/') + path, data=raw, headers=headers)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=20) as response:
            return json.load(response)
    except HTTPError as exc:
        try:
            message = json.load(exc).get('error', str(exc))
        except ValueError:
            message = str(exc)
        finally:
            exc.close()
        raise ValueError(message) from exc


def capture(repo, task, title=None):
    """Read a clean revision; neither execute tests nor modify Git state."""
    repo = str(Path(repo).resolve())
    # System and global Git config often define filter drivers (Git LFS on a
    # hosted runner does). Git status can execute clean/process filters while
    # refreshing the index. Drop those files for every invocation in this
    # function so ambient drivers are not loaded and cannot run. Repository
    # config, includes, and process-level overrides such as GIT_CONFIG_COUNT
    # stay visible and are refused before any command that may refresh.
    env = os.environ.copy()
    env['GIT_CONFIG_NOSYSTEM'] = '1'
    env['GIT_CONFIG_SYSTEM'] = os.devnull
    env['GIT_CONFIG_GLOBAL'] = os.devnull
    def git(*args):
        result = subprocess.run(['git', '--no-replace-objects', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', repo, *args], capture_output=True, check=True, env=env)
        return result.stdout
    # Refuse filters that this same environment would actually execute.
    # Vector arguments alone do not stop hooks or filter drivers.
    configured = subprocess.run(['git', '--no-replace-objects', '--no-optional-locks', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=/dev/null', '-C', repo, 'config', '--get-regexp', r'^filter\..*\.(clean|process)$'], capture_output=True, env=env)
    if configured.returncode not in (0, 1):
        raise ValueError('Unable to inspect Git filter configuration')
    if configured.returncode == 0:
        raise ValueError('Capture refuses configured Git clean/process filters because Git may execute them')
    if any(line.startswith(b'160000 ') for line in git('ls-files', '--stage', '-z').split(b'\0')):
        raise ValueError('Capture refuses submodules because their Git configuration may execute filters')
    flags = git('ls-files', '-v', '-z').split(b'\0')
    if any(entry and (entry[:1].islower() or entry[:1].upper() == b'S') for entry in flags):
        raise ValueError('Capture refuses assume-unchanged or skip-worktree index entries')
    if git('status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Capture requires a clean Git working tree, including untracked files')
    revision = git('rev-parse', '--verify', 'HEAD^{commit}').decode().strip()
    # Canonical NUL-delimited manifest: full modes, types, object IDs and paths.
    manifest = git('ls-tree', '-r', '-z', '--full-tree', revision)
    # Recheck both tree and HEAD to catch ordinary concurrent edits during intake.
    flags_after = git('ls-files', '-v', '-z').split(b'\0')
    if (any(entry and (entry[:1].islower() or entry[:1].upper() == b'S') for entry in flags_after)
            or git('status', '--porcelain', '--untracked-files=all').strip()
            or git('rev-parse', 'HEAD').decode().strip() != revision):
        raise ValueError('Repository changed during capture; retry from a stable clean tree')
    return {'task_id': task, 'title': title or 'Git revision ' + revision[:12], 'kind': 'git_commit',
            'revision': revision, 'digest': hashlib.sha256(manifest).hexdigest(),
            'uri': Path(repo).as_uri() + '#' + revision,
            'summary': 'Read-only Git capture. SHA-256 of raw git ls-tree -r -z --full-tree REVISION manifest (mode/type/object ID/path); no tests executed.'}


def main(argv=None):
    parser = argparse.ArgumentParser(prog='synbios')
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('start', help='Open Crystal Lattice mission control for an existing folder')
    p.add_argument('--workspace', required=True, help='Existing source folder; its files are not changed')
    p.add_argument('--db', help='Optional database outside the source folder (default: local application state)')
    p.add_argument('--name', help='Mission name on first use (default: folder name)')
    p.add_argument('--port', type=int, default=8765, help='Loopback port; 0 chooses an available port')
    for action in ('init', 'serve', 'demo'):
        p = sub.add_parser(action)
        p.add_argument('--db', default='synbios.db')
        if action == 'init':
            p.add_argument('--name', default='Maintainer')
        if action == 'serve':
            p.add_argument('--host', default='127.0.0.1')
            p.add_argument('--port', type=int, default=8765)
    for action in ('state', 'command', 'export', 'capture', 'prompt', 'coordinator-prompt'):
        p = sub.add_parser(action)
        p.add_argument('--url', default=os.getenv('SYNBIOS_URL', 'http://127.0.0.1:8765'))
        if action == 'command':
            p.add_argument('command')
            payload = p.add_mutually_exclusive_group(required=True)
            payload.add_argument('--data', help='JSON command object')
            payload.add_argument('--data-file', help='UTF-8 JSON command file (recommended for agent plans)')
        if action == 'export':
            p.add_argument('task')
            p.add_argument('--output', required=True)
        if action == 'capture':
            p.add_argument('--task', required=True)
            p.add_argument('--repo', required=True)
            p.add_argument('--title')
        if action == 'prompt':
            p.add_argument('task')
        if action == 'coordinator-prompt':
            p.add_argument('project')
    p = sub.add_parser('verify')
    p.add_argument('bundle')
    args = parser.parse_args(argv)
    try:
        if args.action == 'start':
            from .server import create_server
            static_dir = WEB_BUILD
            if not (static_dir / 'index.html').is_file():
                raise ValueError('Build Crystal Lattice first: npm --prefix web ci && npm --prefix web run build (from the Synbios checkout)')
            if not 0 <= args.port <= 65535:
                raise ValueError('Port must be between 0 and 65535')
            result = prepare_workspace(args.workspace, args.db, args.name)
            server = create_server(result['db'], '127.0.0.1', args.port, static_dir)
            print(f"Synbios mission: {result['project']['name']}", flush=True)
            print(f"Workspace: {result['workspace']}", flush=True)
            print(f"State: {result['db']}", flush=True)
            print(f"Open http://127.0.0.1:{server.server_port}", flush=True)
            print('Paste this private operator token into the local sign-in screen:', flush=True)
            print(result['token'], flush=True)
            print('For agent handoffs, use the task-scoped credentials issued in the app. Ctrl+C stops the server; your mission is saved.', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        elif args.action == 'init':
            from .store import Store
            store = Store(args.db)
            try:
                result = store.bootstrap(args.name)
            finally:
                store.close()
        elif args.action == 'demo':
            from .demo import seed_demo
            result = seed_demo(args.db)
        elif args.action == 'serve':
            from .server import create_server
            server = create_server(args.db, args.host, args.port)
            print(f'Synbios listening at http://{args.host}:{server.server_port}', flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
            return 0
        elif args.action == 'verify':
            from .store import verify_bundle
            result = verify_bundle(json.loads(Path(args.bundle).read_text()))
            print(json.dumps(result, indent=2))
            return 0 if result['valid'] else 1
        else:
            token = os.getenv('SYNBIOS_TOKEN', '')
            if not token:
                raise ValueError('Set SYNBIOS_TOKEN to your credential')
            if args.action == 'state':
                result = request(args.url, token, '/api/state')
            elif args.action == 'command':
                data = json.loads(Path(args.data_file).read_text(encoding='utf-8') if args.data_file else args.data)
                if not isinstance(data, dict):
                    raise ValueError('Command data must be a JSON object')
                result = request(args.url, token, '/api/commands/' + args.command, data)
            elif args.action == 'export':
                from urllib.parse import quote
                result = request(args.url, token, '/api/tasks/' + quote(args.task, safe='') + '/export')
                Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
                result = {'output': args.output}
            elif args.action in ('prompt', 'coordinator-prompt'):
                from urllib.parse import quote
                path = ('/api/tasks/' + quote(args.task, safe='') + '/prompt' if args.action == 'prompt'
                        else '/api/projects/' + quote(args.project, safe='') + '/coordinator-prompt')
                result = request(args.url, token, path)
                print(result['prompt'])
                return 0
            else:
                result = request(args.url, token, '/api/commands/artifact.add', capture(args.repo, args.task, args.title))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, sqlite3.DatabaseError, subprocess.CalledProcessError, URLError) as exc:
        print('synbios: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        if hasattr(exc, 'status'):
            print('synbios: ' + str(exc), file=sys.stderr)
            return 1
        raise
