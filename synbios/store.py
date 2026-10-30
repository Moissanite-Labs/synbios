"""Transactional local trust store. Hash chains detect edits, not whole-store replacement."""
import copy
import hashlib
import hmac
import json
import os
import stat
import re
import secrets
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid.uuid4().hex


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status
        self.message = message


Error = DomainError
CAPABILITIES = {'claim', 'work', 'artifact', 'evidence', 'submit'}
COMMAND_FIELDS = {
    'project.create': {'name', 'description', 'repository'},
    'principal.create': {'name', 'kind'},
    'principal.revoke': {'principal_id'},
    'grant.create': {'principal_id', 'task_id', 'capabilities'},
    'grant.revoke': {'grant_id'},
    'task.create': {'project_id', 'title', 'description', 'criteria', 'scope', 'priority', 'dependencies'},
    'task.claim': {'task_id'},
    'task.transition': {'task_id', 'status'},
    'artifact.add': {'task_id', 'title', 'kind', 'revision', 'digest', 'uri', 'summary'},
    'evidence.add': {'task_id', 'artifact_id', 'artifact_digest', 'revision', 'kind', 'status', 'command', 'summary', 'tool', 'tool_version', 'assumptions'},
    'review.create': {'task_id', 'artifact_id', 'revision', 'decision', 'comment'},
}


def _chain(events):
    previous = '0' * 64
    for index, event in enumerate(events, 1):
        if type(event.get('seq')) is not int or event.get('seq') != index or event.get('previous_hash') != previous:
            raise ValueError('Broken audit sequence')
        body = {k: v for k, v in event.items() if k != 'hash'}
        if digest(body) != event.get('hash'):
            raise ValueError('Audit hash mismatch')
        previous = event['hash']


def verify_bundle(bundle):
    errors = []
    try:
        if not isinstance(bundle, dict) or type(bundle.get('version')) is not int or bundle.get('version') != 1 or bundle.get('format') != 'synbios-task':
            raise ValueError('Unsupported bundle')
        events = bundle['events']
        if not isinstance(events, list) or not events:
            raise ValueError('Missing audit')
        links = bundle['audit_chain']
        if not isinstance(links, list) or not links:
            raise ValueError('Missing audit commitments')
        previous = '0' * 64
        for index, link in enumerate(links, 1):
            if type(link['seq']) is not int or link['seq'] != index or link['previous_hash'] != previous or not isinstance(link['hash'], str) or not re.fullmatch(r'[0-9a-f]{64}', link['hash']):
                raise ValueError('Broken audit commitments')
            previous = link['hash']
        last_seq = 0
        for event in events:
            if type(event['seq']) is not int or not last_seq < event['seq'] <= len(links):
                raise ValueError('Task events must have unique increasing positive sequence numbers')
            last_seq = event['seq']
            if digest({k: v for k, v in event.items() if k != 'hash'}) != event['hash']:
                raise ValueError('Task event hash mismatch')
            link = links[event['seq'] - 1]
            if any(event[key] != link[key] for key in ('seq', 'hash', 'previous_hash')):
                raise ValueError('Event commitment mismatch')
        task = bundle['task']
        if task['status'] not in ('open', 'claimed', 'in_progress', 'in_review', 'changes_requested', 'accepted', 'cancelled'):
            raise ValueError('Invalid task status')
        if any(event['task_id'] != task['id'] for event in events):
            raise ValueError('Unrelated task event')
        records = [e['payload'].get('task') for e in events if e.get('task_id') == task['id']]
        if not records or records[-1] != task:
            raise ValueError('Task does not match audit')
        artifacts = {a['id']: a for a in task['artifacts']}
        if len(artifacts) != len(task['artifacts']):
            raise ValueError('Duplicate artifact identifiers')
        for artifact in artifacts.values():
            if artifact['task_id'] != task['id'] or not re.fullmatch(r'[0-9a-f]{64}', artifact['digest']):
                raise ValueError('Invalid artifact binding')
            pattern = r'[0-9a-f]{40}|[0-9a-f]{64}' if artifact['kind'] == 'git_commit' else r'[0-9a-f]{64}'
            if artifact['kind'] not in {'git_commit', 'document'} or not re.fullmatch(pattern, artifact['revision']):
                raise ValueError('Invalid artifact revision')
        for evidence in task['evidence']:
            if evidence['kind'] not in ('test', 'proof', 'analysis') or evidence['status'] not in ('passed', 'failed', 'unavailable'):
                raise ValueError('Invalid evidence kind or status')
            artifact = artifacts[evidence['artifact_id']]
            if evidence['task_id'] != task['id'] or evidence['revision'] != artifact['revision'] or evidence['artifact_digest'] != artifact['digest']:
                raise ValueError('Invalid evidence binding')
        for review in task['reviews']:
            if review['decision'] not in ('approved', 'changes_requested'):
                raise ValueError('Invalid review decision')
            artifact = artifacts[review['artifact_id']]
            if review['task_id'] != task['id'] or review['revision'] != artifact['revision'] or review['created_by'] == artifact['created_by']:
                raise ValueError('Invalid independent review binding')
        if bundle['project']['id'] != task['project_id']:
            raise ValueError('Project binding mismatch')
        if task['status'] == 'accepted':
            artifact = task['artifacts'][-1]
            tests = [e for e in task['evidence'] if e['artifact_id'] == artifact['id'] and e['kind'] == 'test']
            reviewers = {p['id']: p for p in bundle['principals']}
            review = task['reviews'][-1]
            if (not any(e['status'] == 'passed' for e in tests) or any(e['status'] == 'failed' for e in tests)
                    or review['decision'] != 'approved' or review['artifact_id'] != artifact['id']
                    or reviewers[review['created_by']]['kind'] != 'human'):
                raise ValueError('Invalid accepted-task evidence or human review')
        if bundle.get('bundle_digest') != digest({k: v for k, v in bundle.items() if k != 'bundle_digest'}):
            raise ValueError('Bundle digest mismatch')
    except (ValueError, KeyError, TypeError, AttributeError, IndexError, OverflowError) as exc:
        errors.append(str(exc))
    return {'valid': not errors, 'errors': errors}


class Store:
    def __init__(self, path):
        self.path = str(path)
        self._lock = threading.RLock()
        # SQLite's default creation mode follows umask and may expose private
        # workspace data. Reserve a new regular file atomically with mode 0600.
        # Existing regular files retain their operator-selected permissions.
        if self.path != ':memory:':
            try:
                descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if stat.S_ISLNK(os.lstat(self.path).st_mode):
                    raise DomainError('Database symlinks are not supported', 400)
            else:
                os.close(descriptor)
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.execute('PRAGMA busy_timeout=10000')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, data TEXT NOT NULL)')
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if not self.db.execute('SELECT 1 FROM state').fetchone():
                    if self.db.execute('SELECT 1 FROM events').fetchone():
                        raise DomainError('Missing state; integrity failure', 409)
                    self.db.execute('INSERT INTO state VALUES (1,?)', (canonical({'projects': [], 'tasks': [], 'principals': [], 'grants': [], 'credentials': {}}),))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

    def close(self):
        self.db.close()

    def _load(self):
        try:
            state = json.loads(self.db.execute('SELECT data FROM state WHERE id=1').fetchone()[0])
            events = [json.loads(row[0]) for row in self.db.execute('SELECT data FROM events ORDER BY seq')]
            _chain(events)
            if events:
                if events[-1]['payload']['state_digest'] != digest(state):
                    raise ValueError('State does not match audit')
            elif state != {'projects': [], 'tasks': [], 'principals': [], 'grants': [], 'credentials': {}}:
                raise ValueError('Unaudited state')
            return state, events
        except (ValueError, KeyError, TypeError, IndexError, AttributeError, OverflowError, sqlite3.DatabaseError) as exc:
            raise DomainError('Store integrity failure: ' + str(exc), 409) from exc

    def verify_integrity(self):
        with self._lock:
            self.db.execute('BEGIN')
            try:
                _, events = self._load()
                return {'valid': True, 'event_count': len(events)}
            except DomainError as exc:
                try:
                    count = self.db.execute('SELECT count(*) FROM events').fetchone()[0]
                except sqlite3.DatabaseError:
                    count = 0
                return {'valid': False, 'event_count': count, 'errors': [str(exc)]}
            finally:
                self.db.rollback()

    def _auth(self, state, token):
        if not isinstance(token, str) or not token:
            raise DomainError('Authentication required', 401)
        hashed = hashlib.sha256(token.encode()).hexdigest()
        principal_id = next((pid for stored, pid in state['credentials'].items() if hmac.compare_digest(stored, hashed)), None)
        principal = next((p for p in state['principals'] if p['id'] == principal_id and p['active']), None)
        if not principal:
            raise DomainError('Invalid credential', 401)
        return principal

    def _principal(self, state, name, kind):
        principal = {'id': uid(), 'name': self._text(name, 'name'), 'kind': kind, 'active': True, 'created_at': now()}
        token = secrets.token_urlsafe(32)
        state['principals'].append(principal)
        state['credentials'][hashlib.sha256(token.encode()).hexdigest()] = principal['id']
        return {'principal': principal, 'token': token}

    def _save(self, state, events, actor, action, entity, task=None, *, sym2p_packet_hash=None, sym2p_audit=None):
        payload = {'state_digest': digest(state), 'entity': entity}
        if sym2p_packet_hash:
            payload['sym2p_packet_hash'] = sym2p_packet_hash
        if sym2p_audit:
            payload['sym2p_audit'] = sym2p_audit
        if task:
            payload['task'] = task
        event = {'seq': len(events) + 1, 'id': uid(), 'type': action, 'actor_id': actor['id'], 'task_id': task['id'] if task else None, 'created_at': now(), 'payload': payload, 'previous_hash': events[-1]['hash'] if events else '0' * 64}
        event['hash'] = digest(event)
        self.db.execute('UPDATE state SET data=? WHERE id=1', (canonical(state),))
        self.db.execute('INSERT INTO events VALUES (?,?)', (event['seq'], canonical(event)))

    def bootstrap(self, name='Maintainer'):
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                state, events = self._load()
                if state['principals']:
                    raise DomainError('Store already bootstrapped', 409)
                result = self._principal(state, name, 'human')
                self._save(state, events, result['principal'], 'bootstrap', result['principal'])
                self.db.commit()
                return result
            except Exception:
                self.db.rollback()
                raise

    def authenticate(self, token):
        return self.snapshot(token)['actor']

    def snapshot(self, token):
        with self._lock:
            self.db.execute('BEGIN')
            try:
                state, events = self._load()
                actor = self._auth(state, token)
                result = {k: copy.deepcopy(state[k]) for k in ('projects', 'tasks', 'principals', 'grants')}
                for task in result['tasks']:
                    current = task['artifacts'][-1] if task['artifacts'] else None
                    for evidence in task['evidence']:
                        evidence['stale'] = not current or evidence['artifact_id'] != current['id']
                result.update(version=1, actor=actor, events=events, integrity={'valid': True, 'event_count': len(events)}, metrics={'tasks': len(state['tasks']), 'accepted': sum(t['status'] == 'accepted' for t in state['tasks'])})
                return result
            finally:
                self.db.rollback()

    @staticmethod
    def _text(value, field, optional=False):
        if not isinstance(value, str) or (not optional and not value.strip()) or len(value) > 50000:
            raise DomainError('Invalid ' + field)
        try:
            value.encode('utf-8')
        except UnicodeEncodeError as exc:
            raise DomainError('Invalid Unicode in ' + field) from exc
        return value

    def _strings(self, value, field, required=False):
        if not isinstance(value, list) or (required and not value) or len(value) > 1000:
            raise DomainError('Invalid ' + field)
        return [self._text(v, field) for v in value]

    @staticmethod
    def _find(items, identifier, label):
        item = next((x for x in items if x['id'] == identifier), None)
        if item is None:
            raise DomainError(label + ' not found', 404)
        return item

    def _ready(self, state, task):
        if not task['artifacts']:
            raise DomainError('Current artifact required', 409)
        current = task['artifacts'][-1]
        tests = [e for e in task['evidence'] if e['artifact_id'] == current['id'] and e['kind'] == 'test']
        if not any(e['status'] == 'passed' for e in tests) or any(e['status'] == 'failed' for e in tests):
            raise DomainError('Passing current test evidence without failures required', 409)
        if any(self._find(state['tasks'], dep, 'Dependency')['status'] != 'accepted' for dep in task['dependencies']):
            raise DomainError('Dependencies must be accepted', 409)
        return current

    def command(self, token, action, payload, *, sym2p_packet_hash=None, sym2p_audit=None):
        if not isinstance(action, str):
            raise DomainError('Invalid command')
        if not isinstance(payload, dict):
            raise DomainError('Payload must be an object')
        if sym2p_packet_hash is not None and (
                not isinstance(sym2p_packet_hash, str)
                or not re.fullmatch(r'[0-9a-f]{64}', sym2p_packet_hash)):
            raise DomainError('Invalid sym2p packet hash')
        if sym2p_audit is not None and (not isinstance(sym2p_audit, str) or not sym2p_audit.strip()):
            raise DomainError('Invalid sym2p audit line')
        with self._lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                state, events = self._load()
                actor = self._auth(state, token)
                result, task = self._command(state, actor, action, payload)
                entity = result.get('principal', result) if isinstance(result, dict) else result
                self._save(
                    state, events, actor, action, entity, task,
                    sym2p_packet_hash=sym2p_packet_hash,
                    sym2p_audit=sym2p_audit,
                )
                self.db.commit()
                return copy.deepcopy(result)
            except Exception:
                self.db.rollback()
                raise

    def _command(self, s, actor, action, p):
        human = actor['kind'] == 'human'
        if action not in COMMAND_FIELDS:
            raise DomainError('Unknown command', 404)
        if set(p) - COMMAND_FIELDS[action]:
            raise DomainError('Unknown command fields: ' + ', '.join(sorted(set(p) - COMMAND_FIELDS[action])))
        task = None
        def human_only():
            if not human:
                raise DomainError('Human authority required', 403)
        def text(key, default=None):
            return self._text(p.get(key, default), key, default == '')
        def choice(key, options, default=None):
            value = p.get(key, default)
            if not isinstance(value, str) or value not in options:
                raise DomainError('Invalid ' + key)
            return value
        if action in {'project.create', 'principal.create', 'principal.revoke', 'grant.create', 'grant.revoke', 'task.create'}:
            human_only()
        if action == 'project.create':
            result = dict(id=uid(), name=text('name'), description=text('description', ''), repository=text('repository', ''), created_at=now())
            s['projects'].append(result)
        elif action == 'principal.create':
            result = self._principal(s, p.get('name'), choice('kind', {'human', 'agent'}))
        elif action == 'principal.revoke':
            result = self._find(s['principals'], p.get('principal_id'), 'Principal')
            if result['id'] == actor['id']:
                raise DomainError('Cannot revoke your own credential', 409)
            if not result['active']:
                raise DomainError('Principal already revoked', 409)
            if result['kind'] == 'human' and sum(principal['active'] and principal['kind'] == 'human' for principal in s['principals']) <= 1:
                raise DomainError('Cannot revoke the last active human', 409)
            result['active'] = False
            s['credentials'] = {hashed: principal_id for hashed, principal_id in s['credentials'].items() if principal_id != result['id']}
        elif action == 'grant.create':
            self._find(s['principals'], p.get('principal_id'), 'Principal')
            self._find(s['tasks'], p.get('task_id'), 'Task')
            caps = self._strings(p.get('capabilities'), 'capabilities', True)
            if not set(caps) <= CAPABILITIES:
                raise DomainError('Unknown capability')
            result = dict(id=uid(), principal_id=p['principal_id'], task_id=p['task_id'], capabilities=list(dict.fromkeys(caps)), created_by=actor['id'], created_at=now(), revoked_at=None)
            s['grants'].append(result)
        elif action == 'grant.revoke':
            result = self._find(s['grants'], p.get('grant_id'), 'Grant')
            if result['revoked_at']:
                raise DomainError('Grant already revoked', 409)
            result['revoked_at'] = now()
        elif action == 'task.create':
            self._find(s['projects'], p.get('project_id'), 'Project')
            deps = self._strings(p.get('dependencies', []), 'dependencies')
            for dep in deps:
                self._find(s['tasks'], dep, 'Dependency')
            result = dict(id=uid(), project_id=p['project_id'], title=text('title'), description=text('description', ''), criteria=self._strings(p.get('criteria'), 'criteria', True), scope=self._strings(p.get('scope'), 'scope', True), status='open', priority=choice('priority', {'low', 'normal', 'high'}, 'normal'), assignee_id=None, dependencies=list(dict.fromkeys(deps)), created_by=actor['id'], created_at=now(), updated_at=now(), artifacts=[], evidence=[], reviews=[])
            s['tasks'].append(result)
            task = result
        elif action in {'task.claim', 'task.transition', 'artifact.add', 'evidence.add', 'review.create'}:
            task = self._find(s['tasks'], p.get('task_id'), 'Task')
            if task['status'] == 'accepted':
                raise DomainError('Accepted tasks are immutable', 409)
            capability = {'task.claim': 'claim', 'artifact.add': 'artifact', 'evidence.add': 'evidence', 'review.create': None, 'task.transition': 'submit' if p.get('status') == 'in_review' else 'work'}[action]
            if not human and (capability is None or not any(g['principal_id'] == actor['id'] and g['task_id'] == task['id'] and not g['revoked_at'] and capability in g['capabilities'] for g in s['grants'])):
                raise DomainError('Task capability required', 403)
            if action == 'task.claim':
                if task['status'] != 'open' or task['assignee_id']:
                    raise DomainError('Task is not available to claim', 409)
                task.update(status='claimed', assignee_id=actor['id'])
                result = task
            elif action == 'task.transition':
                status = choice('status', {'in_progress', 'in_review', 'cancelled', 'open'})
                allowed = {'open': {'cancelled'}, 'claimed': {'in_progress', 'cancelled', 'open'}, 'in_progress': {'in_review', 'cancelled', 'open'}, 'in_review': {'cancelled', 'open'}, 'changes_requested': {'in_progress', 'in_review', 'cancelled', 'open'}, 'cancelled': {'open'}}
                if status not in allowed.get(task['status'], set()):
                    raise DomainError('Invalid task transition', 409)
                if status in {'cancelled', 'open'}:
                    human_only()
                if status == 'in_review':
                    self._ready(s, task)
                task['status'] = status
                if status == 'open':
                    task['assignee_id'] = None
                result = task
            elif action == 'artifact.add':
                if task['status'] == 'cancelled':
                    raise DomainError('Reopen cancelled task first', 409)
                kind = choice('kind', {'git_commit', 'document'})
                revision, sha = text('revision'), text('digest')
                if not re.fullmatch(r'[0-9a-fA-F]{64}', sha) or not re.fullmatch(r'[0-9a-fA-F]{40}|[0-9a-fA-F]{64}' if kind == 'git_commit' else r'[0-9a-fA-F]{64}', revision):
                    raise DomainError('Invalid revision or SHA-256 digest')
                result = dict(id=uid(), task_id=task['id'], title=text('title'), kind=kind, revision=revision.lower(), digest=sha.lower(), uri=text('uri', ''), summary=text('summary', ''), created_by=actor['id'], created_at=now())
                task['artifacts'].append(result)
                if task['status'] == 'in_review':
                    task['status'] = 'in_progress'
            elif action == 'evidence.add':
                artifact = self._find(task['artifacts'], p.get('artifact_id'), 'Artifact')
                if p.get('artifact_digest') != artifact['digest'] or p.get('revision') != artifact['revision']:
                    raise DomainError('Evidence binding mismatch', 409)
                if task['status'] == 'cancelled':
                    raise DomainError('Reopen cancelled task first', 409)
                result = dict(id=uid(), task_id=task['id'], artifact_id=artifact['id'], artifact_digest=artifact['digest'], revision=artifact['revision'], kind=choice('kind', {'test', 'proof', 'analysis'}), status=choice('status', {'passed', 'failed', 'unavailable'}), command=text('command', ''), summary=text('summary'), tool=text('tool'), tool_version=text('tool_version'), assumptions=self._strings(p.get('assumptions', []), 'assumptions'), created_by=actor['id'], created_at=now())
                task['evidence'].append(result)
            else:
                human_only()
                if task['status'] != 'in_review':
                    raise DomainError('Task must be in review', 409)
                artifact = task['artifacts'][-1] if task['artifacts'] else None
                if not artifact or p.get('artifact_id') != artifact['id'] or p.get('revision') != artifact['revision']:
                    raise DomainError('Review must bind exact current candidate', 409)
                if artifact['created_by'] == actor['id']:
                    raise DomainError('Independent human reviewer required', 403)
                decision = choice('decision', {'approved', 'changes_requested'})
                if decision == 'approved':
                    self._ready(s, task)
                result = dict(id=uid(), task_id=task['id'], artifact_id=artifact['id'], revision=artifact['revision'], decision=decision, comment=text('comment', ''), created_by=actor['id'], created_at=now())
                task['reviews'].append(result)
                task['status'] = 'accepted' if decision == 'approved' else 'changes_requested'
            task['updated_at'] = now()
        else:
            raise DomainError('Unknown command', 404)
        return result, task

    def export(self, token, task_id):
        snapshot = self.snapshot(token)
        task = copy.deepcopy(self._find(snapshot['tasks'], task_id, 'Task'))
        for evidence in task['evidence']:
            evidence.pop('stale', None)
        involved = {task['created_by'], task['assignee_id']} | {x['created_by'] for key in ('artifacts', 'evidence', 'reviews') for x in task[key]}
        bundle = {'version': 1, 'format': 'synbios-task', 'exported_at': now(), 'task': task, 'project': self._find(snapshot['projects'], task['project_id'], 'Project'), 'principals': [p for p in snapshot['principals'] if p['id'] in involved], 'events': [e for e in snapshot['events'] if e['task_id'] == task_id], 'audit_chain': [{k: e[k] for k in ('seq', 'hash', 'previous_hash')} for e in snapshot['events']], 'limitations': ['Local tamper detection only; not signed identity or proof of completeness. Unrelated event payloads are omitted; their commitments are not independently verifiable.', 'Evidence is reported by principals; proof is shadow evidence, not platform-verified truth.']}
        bundle['bundle_digest'] = digest(bundle)
        return bundle
