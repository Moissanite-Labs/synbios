"""Synthetic, explicit demonstration fixture using ordinary authorization rules."""
import hashlib
from pathlib import Path

from .store import Store


def seed_demo(path):
    if Path(path).exists():
        raise ValueError('Demo requires a new database path')
    store = Store(path)
    try:
        operator = store.bootstrap('Synthetic demo operator')
        token = operator['token']
        reviewer = store.command(token, 'principal.create', {'name': 'Synthetic independent reviewer', 'kind': 'human'})
        agent = store.command(token, 'principal.create', {'name': 'Synthetic build agent', 'kind': 'agent'})
        project = store.command(token, 'project.create', {'name': 'Synthetic · Commons starter', 'description': 'Demonstration records only. Evidence is a labeled fixture, not executed validation.', 'repository': 'https://example.invalid/synthetic/commons'})
        tasks = []
        for title in ('Define contribution guide', 'Build evidence intake', 'Review release readiness'):
            tasks.append(store.command(token, 'task.create', {'project_id': project['id'], 'title': title, 'description': 'Synthetic demonstration task', 'criteria': ['Artifact has exact revision binding', 'Independent human reviews evidence'], 'scope': ['docs/'], 'priority': 'normal', 'dependencies': []}))
        for task in tasks[:2]:
            tid = task['id']
            store.command(token, 'grant.create', {'principal_id': agent['principal']['id'], 'task_id': tid, 'capabilities': ['claim', 'work', 'artifact', 'evidence', 'submit']})
            at = agent['token']
            store.command(at, 'task.claim', {'task_id': tid})
            store.command(at, 'task.transition', {'task_id': tid, 'status': 'in_progress'})
            digest = hashlib.sha256(('SYNTHETIC fixture ' + tid).encode()).hexdigest()
            artifact = store.command(at, 'artifact.add', {'task_id': tid, 'title': 'Synthetic document fixture', 'kind': 'document', 'revision': digest, 'digest': digest, 'uri': 'https://example.invalid/synthetic/document', 'summary': 'SYNTHETIC fixture; no external content fetched.'})
            store.command(at, 'evidence.add', {'task_id': tid, 'artifact_id': artifact['id'], 'artifact_digest': digest, 'revision': digest, 'kind': 'test', 'status': 'passed', 'command': 'SYNTHETIC FIXTURE — no command executed', 'summary': 'SYNTHETIC demonstration only; this is not an actual test result.', 'tool': 'synthetic-fixture', 'tool_version': '1', 'assumptions': ['Synthetic evidence, not executed validation']})
            store.command(at, 'task.transition', {'task_id': tid, 'status': 'in_review'})
            if task == tasks[0]:
                store.command(reviewer['token'], 'review.create', {'task_id': tid, 'artifact_id': artifact['id'], 'revision': digest, 'decision': 'approved', 'comment': 'Synthetic independent human review for demonstration.'})
        return {'synthetic': True, 'token': token, 'principal': operator['principal'], 'reviewer_token': reviewer['token'], 'reviewer': reviewer['principal'], 'message': 'Synthetic fixture seeded. Store credentials securely; they are shown only here.'}
    finally:
        store.close()
