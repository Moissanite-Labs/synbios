"""Explicit local administration and authenticated API client."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, 'Redirect refused', headers, fp)


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
    for action in ('init', 'serve', 'demo'):
        p = sub.add_parser(action)
        p.add_argument('--db', default='synbios.db')
        if action == 'init':
            p.add_argument('--name', default='Maintainer')
        if action == 'serve':
            p.add_argument('--host', default='127.0.0.1')
            p.add_argument('--port', type=int, default=8765)
    for action in ('state', 'command', 'export', 'capture'):
        p = sub.add_parser(action)
        p.add_argument('--url', default=os.getenv('SYNBIOS_URL', 'http://127.0.0.1:8765'))
        if action == 'command':
            p.add_argument('command')
            p.add_argument('--data', required=True)
        if action == 'export':
            p.add_argument('task')
            p.add_argument('--output', required=True)
        if action == 'capture':
            p.add_argument('--task', required=True)
            p.add_argument('--repo', required=True)
            p.add_argument('--title')
    p = sub.add_parser('verify')
    p.add_argument('bundle')
    args = parser.parse_args(argv)
    try:
        if args.action == 'init':
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
                data = json.loads(args.data)
                if not isinstance(data, dict):
                    raise ValueError('--data must be a JSON object')
                result = request(args.url, token, '/api/commands/' + args.command, data)
            elif args.action == 'export':
                from urllib.parse import quote
                result = request(args.url, token, '/api/tasks/' + quote(args.task, safe='') + '/export')
                Path(args.output).write_text(json.dumps(result, indent=2) + '\n')
                result = {'output': args.output}
            else:
                result = request(args.url, token, '/api/commands/artifact.add', capture(args.repo, args.task, args.title))
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, URLError) as exc:
        print('synbios: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        if hasattr(exc, 'status'):
            print('synbios: ' + str(exc), file=sys.stderr)
            return 1
        raise
