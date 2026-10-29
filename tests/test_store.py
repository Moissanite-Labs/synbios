import copy
import json
import os
import stat
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from synbios.store import Store, DomainError, verify_bundle, digest


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'store.sqlite'
        self.s = Store(self.path)
        self.owner = self.s.bootstrap()['token']
        self.agent = self.cmd('principal.create', name='Worker', kind='agent')
        self.reviewer = self.cmd('principal.create', name='Reviewer', kind='human')
        self.project = self.cmd('project.create', name='Research', description='', repository='')
        self.task = self.new_task()

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def cmd(self, action, token=None, **payload):
        return self.s.command(token or self.owner, action, payload)

    def new_task(self, **extra):
        return self.cmd('task.create', project_id=self.project['id'], title='A task', criteria=['Works'], scope=['src'], **extra)

    def grant(self, task=None, caps=None):
        return self.cmd('grant.create', principal_id=self.agent['principal']['id'], task_id=(task or self.task)['id'], capabilities=caps or ['claim', 'work', 'artifact', 'evidence', 'submit'])

    def artifact(self, token=None, revision='a' * 40):
        return self.cmd('artifact.add', token, task_id=self.task['id'], title='Candidate', kind='git_commit', revision=revision, digest='b' * 64, uri='https://example.invalid/commit', summary='')

    def evidence(self, artifact, token=None, status='passed', **extra):
        payload = dict(task_id=self.task['id'], artifact_id=artifact['id'], artifact_digest=artifact['digest'], revision=artifact['revision'], kind='test', status=status, command='python -m unittest', summary='Reported test', tool='python', tool_version='3.11', assumptions=['Reported, not executed by platform'])
        payload.update(extra)
        return self.cmd('evidence.add', token, **payload)

    def transition(self, status, token=None):
        return self.cmd('task.transition', token, task_id=self.task['id'], status=status)

    def review(self, artifact, token=None, **extra):
        payload = dict(task_id=self.task['id'], artifact_id=artifact['id'], revision=artifact['revision'], decision='approved', comment='Reviewed exact revision')
        payload.update(extra)
        return self.cmd('review.create', token or self.reviewer['token'], **payload)

    def assert_error(self, status, func, *args, **kwargs):
        with self.assertRaises(DomainError) as context:
            func(*args, **kwargs)
        self.assertEqual(context.exception.status, status)

    def test_complete_cycle_persistence_and_private_export(self):
        self.grant()
        token = self.agent['token']
        self.cmd('task.claim', token, task_id=self.task['id'])
        self.transition('in_progress', token)
        artifact = self.artifact(token)
        self.evidence(artifact, token)
        self.transition('in_review', token)
        self.review(artifact)
        self.assert_error(409, self.artifact)
        unrelated = self.cmd('principal.create', name='Private unrelated user', kind='human')
        self.new_task()
        bundle = self.s.export(self.owner, self.task['id'])
        self.assertTrue(verify_bundle(bundle)['valid'])
        serialized = json.dumps(bundle)
        self.assertNotIn(unrelated['principal']['id'], serialized)
        self.assertNotIn(unrelated['token'], serialized)
        self.assertNotIn('credentials', serialized)
        self.s.close()
        self.s = Store(self.path)
        self.assertEqual(self.s.snapshot(self.owner)['tasks'][0]['status'], 'accepted')
        self.assertTrue(self.s.verify_integrity()['valid'])

    def test_capabilities_revocation_and_body_role_spoof(self):
        token = self.agent['token']
        self.assert_error(400, self.cmd, 'project.create', token, name='Spoof', kind='human')
        self.assert_error(403, self.artifact, token)
        grant = self.grant(caps=['artifact'])
        self.artifact(token)
        self.assert_error(403, self.transition, 'in_progress', token)
        other = self.new_task()
        self.assert_error(403, self.cmd, 'artifact.add', token, task_id=other['id'])
        self.cmd('grant.revoke', grant_id=grant['id'])
        self.assert_error(403, self.artifact, token)
        self.assert_error(401, self.s.snapshot, 'forged')
        self.assert_error(409, self.s.bootstrap)

    def test_revision_evidence_and_independent_acceptance(self):
        self.transition('in_progress')
        a = self.artifact()
        self.assert_error(409, self.transition, 'in_review')
        self.assert_error(409, self.evidence, a, artifact_digest='c' * 64)
        self.evidence(a)
        self.transition('in_review')
        self.assert_error(403, self.review, a, self.owner)
        self.grant()
        self.assert_error(403, self.review, a, self.agent['token'])
        b = self.artifact(revision='c' * 40)
        self.assert_error(409, self.review, a)
        self.assert_error(409, self.transition, 'in_review')
        state = self.s.snapshot(self.owner)
        self.assertTrue(state['tasks'][0]['evidence'][0]['stale'])
        self.evidence(b)
        self.evidence(b, status='failed')
        self.assert_error(409, self.transition, 'in_review')

    def test_failed_evidence_after_submission_blocks_review(self):
        self.transition('in_progress')
        a = self.artifact()
        self.evidence(a)
        self.transition('in_review')
        self.evidence(a, status='failed')
        self.assert_error(409, self.review, a)
        self.review(a, decision='changes_requested')
        self.assertEqual(self.s.snapshot(self.owner)['tasks'][0]['status'], 'changes_requested')

    def test_dependencies_and_invalid_transitions_atomic(self):
        dependent = self.new_task(dependencies=[self.task['id']])
        before = self.s.verify_integrity()['event_count']
        self.assert_error(404, self.new_task, dependencies=['self-or-future-cycle'])
        self.assertEqual(before, self.s.verify_integrity()['event_count'])
        self.assert_error(409, self.transition, 'in_review')
        self.task = dependent
        self.transition('in_progress')
        a = self.artifact()
        self.evidence(a)
        self.assert_error(409, self.transition, 'in_review')
        self.transition('cancelled')
        self.assert_error(409, self.artifact)
        self.transition('open')

    def test_tamper_state_credentials_and_audit_fail_closed(self):
        row = self.s.db.execute('SELECT data FROM state').fetchone()[0]
        state = json.loads(row)
        state['credentials']['0' * 64] = self.agent['principal']['id']
        self.s.db.execute('UPDATE state SET data=?', (json.dumps(state),))
        self.assertFalse(self.s.verify_integrity()['valid'])
        self.assert_error(409, self.s.snapshot, self.owner)
        self.assert_error(409, self.cmd, 'project.create', name='No')
        self.s.db.execute('UPDATE state SET data=?', (row,))
        event = json.loads(self.s.db.execute('SELECT data FROM events WHERE seq=1').fetchone()[0])
        event['actor_id'] = 'forged'
        self.s.db.execute('UPDATE events SET data=? WHERE seq=1', (json.dumps(event),))
        self.assert_error(409, self.s.authenticate, self.owner)

    def test_bundle_tamper_and_empty_invalid(self):
        bundle = self.s.export(self.owner, self.task['id'])
        self.assertTrue(verify_bundle(bundle)['valid'])
        modified = copy.deepcopy(bundle)
        modified['task']['title'] = 'Changed'
        self.assertFalse(verify_bundle(modified)['valid'])
        modified = copy.deepcopy(bundle)
        modified['events'][0]['payload']['task']['title'] = 'Changed'
        self.assertFalse(verify_bundle(modified)['valid'])
        for malformed in (None, {}, [], {'version': 1, 'events': [None]}):
            self.assertFalse(verify_bundle(malformed)['valid'])

    def test_two_connections_claim_exactly_once(self):
        self.grant()
        second = Store(self.path)
        def claim(store):
            try:
                store.command(self.agent['token'], 'task.claim', {'task_id': self.task['id']})
                return 'claimed'
            except DomainError as exc:
                return exc.status
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(claim, [self.s, second]))
            self.assertCountEqual(results, ['claimed', 409])
            self.assertTrue(self.s.verify_integrity()['valid'])
        finally:
            second.close()

    def test_audit_failure_rolls_back_mutation(self):
        before = self.s.snapshot(self.owner)
        self.s.db.execute("CREATE TRIGGER reject_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.cmd('project.create', name='Must roll back')
        self.s.db.execute('DROP TRIGGER reject_event')
        after = self.s.snapshot(self.owner)
        self.assertEqual(before, after)

    def test_hash_only_credentials_and_no_event_secret(self):
        state = self.s.db.execute('SELECT data FROM state').fetchone()[0]
        audit = json.dumps(self.s.snapshot(self.owner)['events'])
        for token in [self.owner, self.agent['token'], self.reviewer['token']]:
            self.assertNotIn(token, state)
            self.assertNotIn(token, audit)
        self.assertEqual(len(json.loads(state)['credentials']), 3)

    def test_malformed_audit_fails_closed(self):
        self.s.db.execute("UPDATE events SET data='null' WHERE seq=1")
        self.assertFalse(self.s.verify_integrity()['valid'])
        self.assert_error(409, self.s.snapshot, self.owner)
        for malformed in ({'version': 1, 'events': [{}], 'audit_chain': []}, {'version': 1, 'events': [], 'audit_chain': []}):
            self.assertFalse(verify_bundle(malformed)['valid'])

    def test_required_scope_and_criteria_and_unknown_fields(self):
        before = self.s.snapshot(self.owner)
        base = dict(project_id=self.project['id'], title='Scoped work', criteria=['Works'], scope=['src'])
        for field in ('criteria', 'scope'):
            omitted = dict(base)
            del omitted[field]
            self.assert_error(400, self.cmd, 'task.create', **omitted)
            self.assert_error(400, self.cmd, 'task.create', **dict(base, **{field: []}))
        self.assert_error(400, self.cmd, 'task.create', **dict(base, scpoe=['typo']))
        self.assert_error(400, self.cmd, 'task.claim', task_id=self.task['id'], role='human')
        self.assertEqual(before, self.s.snapshot(self.owner))

    def test_principal_revocation_removes_all_access_atomically(self):
        self.grant()
        revoked = self.cmd('principal.revoke', principal_id=self.agent['principal']['id'])
        self.assertFalse(revoked['active'])
        self.assert_error(401, self.s.authenticate, self.agent['token'])
        self.assert_error(401, self.s.snapshot, self.agent['token'])
        self.assert_error(401, self.cmd, 'task.claim', self.agent['token'], task_id=self.task['id'])
        state = json.loads(self.s.db.execute('SELECT data FROM state').fetchone()[0])
        self.assertNotIn(self.agent['principal']['id'], state['credentials'].values())
        self.assertEqual(self.s.snapshot(self.owner)['events'][-1]['type'], 'principal.revoke')
        self.assertTrue(self.s.verify_integrity()['valid'])
        before = self.s.snapshot(self.owner)
        self.assert_error(409, self.cmd, 'principal.revoke', principal_id=self.agent['principal']['id'])
        self.assert_error(409, self.cmd, 'principal.revoke', principal_id=before['actor']['id'])
        self.assertEqual(before, self.s.snapshot(self.owner))
        self.cmd('principal.revoke', principal_id=self.reviewer['principal']['id'])
        self.assert_error(401, self.s.authenticate, self.reviewer['token'])
        self.assert_error(409, self.cmd, 'principal.revoke', principal_id=before['actor']['id'])

    def test_agents_cannot_revoke_other_principals(self):
        self.assert_error(403, self.cmd, 'principal.revoke', self.agent['token'], principal_id=self.reviewer['principal']['id'])
        self.assertTrue(self.s.authenticate(self.reviewer['token'])['active'])

    @unittest.skipUnless(os.name == 'posix', 'POSIX file permissions')
    def test_new_database_private_and_existing_permissions_preserved(self):
        path = Path(self.tmp.name) / 'private.db'
        previous = os.umask(0o022)
        try:
            private = Store(path)
        finally:
            os.umask(previous)
        try:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            credential = private.bootstrap()['token']
        finally:
            private.close()
        os.chmod(path, 0o640)
        reopened = Store(path)
        try:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual(reopened.snapshot(credential)['actor']['kind'], 'human')
        finally:
            reopened.close()
        before = path.read_bytes()
        link = Path(self.tmp.name) / 'database-link.db'
        link.symlink_to(path)
        self.assert_error(400, Store, link)
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        self.assertTrue(link.is_symlink())

    def test_bundle_sequence_structural_validation(self):
        self.artifact()
        bundle = self.s.export(self.owner, self.task['id'])
        for sequence in (-1, 0, True, False, 1.0, '1'):
            malformed = copy.deepcopy(bundle)
            event = malformed['events'][0]
            event['seq'] = sequence
            event['previous_hash'] = '0' * 64
            event['hash'] = digest({k: v for k, v in event.items() if k != 'hash'})
            malformed['events'] = [event]
            malformed['task'] = event['payload']['task']
            malformed['audit_chain'] = [{k: event[k] for k in ('seq', 'hash', 'previous_hash')}]
            malformed['bundle_digest'] = digest({k: v for k, v in malformed.items() if k != 'bundle_digest'})
            self.assertFalse(verify_bundle(malformed)['valid'], sequence)
        for events in ([bundle['events'][-1], *bundle['events']], [*bundle['events'], bundle['events'][-1]]):
            malformed = copy.deepcopy(bundle)
            malformed['events'] = events
            malformed['bundle_digest'] = digest({k: v for k, v in malformed.items() if k != 'bundle_digest'})
            self.assertFalse(verify_bundle(malformed)['valid'])

    def test_bad_fields_roll_back(self):
        for payload in ({'kind': 'document', 'revision': 'short', 'digest': 'b' * 64}, {'kind': 'git_commit', 'revision': 'a' * 40, 'digest': 'bad'}):
            self.assert_error(400, self.cmd, 'artifact.add', task_id=self.task['id'], title='Bad', **payload)
        self.assert_error(400, self.cmd, 'grant.create', task_id=self.task['id'], principal_id=self.agent['principal']['id'], capabilities=['merge'])
        self.assertEqual(self.s.snapshot(self.owner)['tasks'][0]['artifacts'], [])


if __name__ == '__main__':
    unittest.main()
