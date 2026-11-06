import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from synbios.store import DomainError, Store, canonical, verify_bundle


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'mission.db'
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.operator = self.store.bootstrap('Operator')['token']
        self.project = self.call('project.create', name='Exo', description='Make local collaboration clear', workspace='/work/exo')

    def call(self, action, token=None, **payload):
        return self.store.command(token or self.operator, action, payload)

    def snapshot(self):
        return self.store.snapshot(self.operator)

    def task(self, identity):
        return next(t for t in self.snapshot()['tasks'] if t['id'] == identity)

    def create_task(self, **kwargs):
        return self.call('task.create', project_id=self.project['id'], title='Make a clear mission view',
                         criteria=['A user can identify the next action'], scope=['src/mission/'], **kwargs)

    def mutate(self, action, task_id, token=None, **payload):
        return self.call(action, token=token, task_id=task_id, expected_revision=self.task(task_id)['revision'], **payload)

    def assert_rejected(self, action, expected_status, token=None, **payload):
        before = self.snapshot()
        with self.assertRaises(DomainError) as caught:
            self.call(action, token=token, **payload)
        self.assertEqual(caught.exception.status, expected_status)
        self.assertEqual(self.snapshot(), before)

    def candidate(self, task_id, token, digit='a'):
        artifact = self.call('artifact.add', token=token, task_id=task_id, title='Candidate', kind='git_commit',
                             revision=digit * 40, digest=digit * 64)
        self.call('evidence.add', token=token, task_id=task_id, artifact_id=artifact['id'],
                  artifact_digest=artifact['digest'], revision=artifact['revision'], kind='test', status='passed',
                  summary='Checked the behavior', tool='unittest', tool_version='3.11')
        return artifact

    def test_atomic_plan_dependencies_and_each_task_export(self):
        result = self.call('plan.create', project_id=self.project['id'], tasks=[
            {'key': 'build', 'title': 'Implement', 'criteria': ['Works'], 'scope': ['src/'], 'dependencies': ['shape']},
            {'key': 'shape', 'title': 'Agree interfaces', 'criteria': ['Recorded'], 'scope': ['docs/'], 'stage': 'shape'},
        ])
        self.assertEqual(result['tasks'][0]['dependencies'], [result['keys']['shape']])
        self.assertEqual(result['tasks'][1]['stage'], 'shape')
        for task in result['tasks']:
            self.assertTrue(verify_bundle(self.store.export(self.operator, task['id']))['valid'])
            self.assertEqual(task['revision'], 1)
        good = {'key': 'good', 'title': 'Valid', 'criteria': ['Pass'], 'scope': ['docs/']}
        self.assert_rejected('plan.create', 400, project_id=self.project['id'], tasks=[good, {'key': 'bad'}])
        self.assert_rejected('plan.create', 400, project_id=self.project['id'], tasks=[good, good])
        self.assert_rejected('plan.create', 409, project_id=self.project['id'], tasks=[
            {**good, 'dependencies': ['other']}, {**good, 'key': 'other', 'dependencies': ['good']}])

    def test_plan_audit_failure_rolls_back_every_task_and_event(self):
        before = self.snapshot()
        save = self.store._save
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('Injected audit storage failure')
            return save(*args, **kwargs)

        with patch.object(self.store, '_save', side_effect=fail_second), self.assertRaises(RuntimeError):
            self.call('plan.create', project_id=self.project['id'], tasks=[
                {'key': 'one', 'title': 'First', 'criteria': ['Pass'], 'scope': ['src/']},
                {'key': 'two', 'title': 'Second', 'criteria': ['Pass'], 'scope': ['tests/']},
            ])
        self.assertEqual(self.snapshot(), before)

    def test_decision_requester_can_withdraw_but_not_resolve(self):
        task = self.create_task()
        worker = self.mutate('task.delegate', task['id'], name='Agent')
        decision = self.mutate('decision.create', task['id'], token=worker['token'], title='Obsolete question',
                               question='Choose a direction', options=['A', 'B'])
        self.mutate('decision.withdraw', task['id'], token=worker['token'], decision_id=decision['id'], note='Resolved by new evidence; no human choice needed')
        self.assertEqual(self.task(task['id'])['decisions'][0]['status'], 'withdrawn')
        self.assertEqual(self.task(task['id'])['blockers'], [])

    def test_coordinator_can_plan_only_authorized_mission_and_revoke(self):
        enrolled = self.call('coordinator.enroll', project_id=self.project['id'], name='Coordinator')
        token = enrolled['token']
        result = self.call('plan.create', token=token, project_id=self.project['id'], tasks=[
            {'key': 'one', 'title': 'Plan this mission', 'criteria': ['Done'], 'scope': ['docs/']}])
        self.mutate('task.delegate', result['tasks'][0]['id'], token=token, name='Worker')
        other = self.call('project.create', name='Other')
        self.assert_rejected('plan.create', 403, token=token, project_id=other['id'], tasks=[
            {'key': 'one', 'title': 'Forbidden', 'criteria': ['Done'], 'scope': ['src/']}])
        self.assert_rejected('principal.create', 403, token=token, name='Admin', kind='human')
        self.assert_rejected('coordinator.enroll', 403, token=token, project_id=other['id'], name='Expansion')
        self.call('coordinator.revoke', grant_id=enrolled['coordinator_grant']['id'])
        self.assert_rejected('plan.create', 403, token=token, project_id=self.project['id'], tasks=[
            {'key': 'two', 'title': 'Now forbidden', 'criteria': ['Done'], 'scope': ['src/']}])
        self.assertNotIn(token, canonical(self.snapshot()))
        self.assertNotIn(token, self.path.read_bytes().decode('utf-8', errors='ignore'))

    def test_delegate_reassign_revokes_outgoing_worker_and_rejects_stale_writes(self):
        task = self.create_task()
        first = self.mutate('task.delegate', task['id'], name='Agent one')
        self.assertEqual(first['task']['revision'], 2)
        self.call('task.transition', token=first['token'], task_id=task['id'], status='in_progress')
        revision = self.task(task['id'])['revision']
        second = self.mutate('task.delegate', task['id'], name='Agent two')
        self.assertEqual(second['task']['assignee_id'], second['principal']['id'])
        self.assert_rejected('task.report', 409, task_id=task['id'], expected_revision=revision, summary='Stale form')
        for action, extra in [
            ('task.report', {'summary': 'Old agent', 'expected_revision': self.task(task['id'])['revision']}),
            ('artifact.add', {'title': 'Old candidate', 'kind': 'git_commit', 'revision': 'a' * 40, 'digest': 'a' * 64}),
            ('task.transition', {'status': 'in_progress'}),
        ]:
            self.assert_rejected(action, 403, token=first['token'], task_id=task['id'], **extra)
        self.mutate('task.report', task['id'], token=second['token'], summary='New owner working', progress=25)
        self.assertNotIn(second['token'], canonical(self.snapshot()))
        self.assertTrue(any(g['revoked_at'] for g in self.snapshot()['grants'] if g['principal_id'] == first['principal']['id']))

    def test_explicit_decisions_block_submission_resolve_and_cannot_be_self_approved(self):
        task = self.create_task()
        worker = self.mutate('task.delegate', task['id'], name='Agent')
        token = worker['token']
        self.call('task.transition', token=token, task_id=task['id'], status='in_progress')
        self.candidate(task['id'], token)
        choice = self.mutate('decision.create', task['id'], token=token, title='Choose approach',
                             question='Which behavior do you want?', options=['Option A', 'Option B'])
        self.assertTrue(any(b['kind'] == 'decision' for b in self.task(task['id'])['blockers']))
        self.assert_rejected('task.transition', 409, token=token, task_id=task['id'], status='in_review')
        self.assert_rejected('decision.resolve', 403, token=token, task_id=task['id'], expected_revision=self.task(task['id'])['revision'],
                             decision_id=choice['id'], choice='Option A')
        self.mutate('decision.resolve', task['id'], decision_id=choice['id'], choice='Option A', note='Fits the goal')
        self.call('task.transition', token=token, task_id=task['id'], status='in_review')
        self.assertFalse(any(b['kind'] == 'decision' for b in self.task(task['id'])['blockers']))

    def test_contract_change_preserves_candidates_but_requires_new_evidence(self):
        task = self.create_task()
        worker = self.mutate('task.delegate', task['id'], name='Agent')
        token = worker['token']
        self.call('task.transition', token=token, task_id=task['id'], status='in_progress')
        original = self.candidate(task['id'], token)
        self.call('task.transition', token=token, task_id=task['id'], status='in_review')
        self.mutate('task.update', task['id'], criteria=['New behavior must work'])
        current = self.task(task['id'])
        self.assertEqual(current['status'], 'in_progress')
        self.assertEqual(current['artifacts'][0]['id'], original['id'])
        self.assertTrue(current['evidence'][0]['stale'])
        self.assert_rejected('task.transition', 409, token=token, task_id=task['id'], status='in_review')
        artifact = self.candidate(task['id'], token, 'b')
        self.call('task.transition', token=token, task_id=task['id'], status='in_review')
        self.call('review.create', task_id=task['id'], artifact_id=artifact['id'], revision=artifact['revision'], decision='approved')
        self.assertTrue(verify_bundle(self.store.export(self.operator, task['id']))['valid'])
        self.assert_rejected('task.update', 409, task_id=task['id'], expected_revision=self.task(task['id'])['revision'], title='Cannot mutate accepted')

    def test_cross_mission_and_cycles_cannot_be_introduced(self):
        first = self.create_task()
        second = self.create_task(dependencies=[first['id']])
        self.assert_rejected('task.update', 409, task_id=first['id'], expected_revision=first['revision'], dependencies=[second['id']])
        other_project = self.call('project.create', name='Another mission')
        other = self.call('task.create', project_id=other_project['id'], title='Other work', criteria=['Done'], scope=['src/'])
        self.assert_rejected('task.update', 409, task_id=first['id'], expected_revision=first['revision'], dependencies=[other['id']])
        self.assert_rejected('task.create', 409, project_id=self.project['id'], title='Wrong dependency', criteria=['Done'], scope=['docs/'], dependencies=[other['id']])

    def test_two_connections_compare_and_swap_one_write_wins(self):
        task = self.create_task()
        second = Store(self.path)
        self.addCleanup(second.close)
        barrier = threading.Barrier(2)
        results = []

        def attempt(store, title):
            barrier.wait()
            try:
                store.command(self.operator, 'task.update', {'task_id': task['id'], 'expected_revision': task['revision'], 'title': title})
                results.append('ok')
            except DomainError as exc:
                results.append(exc.status)

        threads = [threading.Thread(target=attempt, args=(store, title)) for store, title in [(self.store, 'One'), (second, 'Two')]]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
        self.assertCountEqual(results, ['ok', 409])
        self.assertTrue(self.store.verify_integrity()['valid'])

    def test_resources_reports_prompts_and_scope_alerts_are_honest(self):
        task = self.create_task()
        self.create_task()
        delegated = self.mutate('task.delegate', task['id'], name='Agent')
        self.mutate('task.report', task['id'], token=delegated['token'], summary='Investigating', progress=20, blocker='Need a test fixture')
        snapshot = self.snapshot()
        self.assertEqual(snapshot['resources']['telemetry'], 'unavailable')
        self.assertIsNone(snapshot['resources']['cost'])
        self.assertTrue(snapshot['scope_overlaps'][0]['advisory'])
        self.assertEqual(self.task(task['id'])['blockers'][0]['kind'], 'reported')
        prompt = self.store.task_prompt(self.operator, task['id'], 'http://127.0.0.1:9444')['prompt']
        for content in ('Make a clear mission view', 'src/mission/', 'A user can identify', '9444', '--data-file'):
            self.assertIn(content, prompt)
        for secret in (self.operator, delegated['token']):
            self.assertNotIn(secret, prompt)
        self.assertIn('http://127.0.0.1:9444', self.store.coordinator_prompt(self.operator, self.project['id'], 'http://127.0.0.1:9444')['prompt'])
        self.mutate('task.report', task['id'], token=delegated['token'], summary='Fixture found', progress=40, blocker='')
        self.assertFalse(self.task(task['id'])['blockers'])

    def test_old_database_defaults_are_read_only_and_export_still_verifies(self):
        task = self.create_task()
        # Build an audited legacy-shaped fixture; opening it must not rewrite
        # old records merely to add display defaults.
        with self.store._lock:
            self.store.db.execute('BEGIN IMMEDIATE')
            state, events = self.store._load()
            old = next(t for t in state['tasks'] if t['id'] == task['id'])
            for key in ('stage', 'candidate_path', 'revision', 'reports', 'decisions', 'assignment_revision', 'contract_revision'):
                old.pop(key)
            actor = self.store._auth(state, self.operator)
            self.store._save(state, events, actor, 'legacy.fixture', old, old)
            self.store.db.commit()
        before = self.store.db.execute('SELECT data FROM state').fetchone()[0]
        current = self.task(task['id'])
        self.assertEqual(current['stage'], 'build')
        self.assertEqual(current['revision'], 1)
        self.assertEqual(self.store.db.execute('SELECT data FROM state').fetchone()[0], before)
        self.assertTrue(verify_bundle(self.store.export(self.operator, task['id']))['valid'])
        self.mutate('task.update', task['id'], title='A current title')
        self.assertEqual(self.task(task['id'])['revision'], 2)

    def test_project_goal_can_change_with_cas_without_rebinding_workspace(self):
        updated = self.call('project.update', project_id=self.project['id'], expected_revision=1, description='A precise goal')
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(updated['workspace'], '/work/exo')
        self.assert_rejected('project.update', 409, project_id=self.project['id'], expected_revision=1, name='Stale')
        self.assert_rejected('project.update', 400, project_id=self.project['id'], expected_revision=2, workspace='/other')

    def test_reopen_revokes_old_owner_before_a_new_delegation(self):
        task = self.create_task()
        old = self.mutate('task.delegate', task['id'], name='Former owner')
        self.mutate('task.report', task['id'], token=old['token'], summary='Waiting', blocker='Old blocker')
        self.call('task.transition', task_id=task['id'], status='open')
        new = self.mutate('task.delegate', task['id'], name='Current owner')
        self.assertEqual(self.task(task['id'])['blockers'], [])
        self.assert_rejected('artifact.add', 403, token=old['token'], task_id=task['id'], title='Stale owner', kind='git_commit', revision='a' * 40, digest='a' * 64)
        self.mutate('task.report', task['id'], token=new['token'], summary='Current owner can work')

    def test_root_and_wildcard_scope_signals_are_conservative(self):
        from synbios.mission import _scopes_overlap
        for a, b in [('.', 'src/'), ('./', 'src/'), ('./src/', 'src/file.py'),
                     ('src/foo*.py', 'src/foobar.py'), ('*.py', 'src/file.py'),
                     ('src\\nested', 'src/nested/file.py')]:
            self.assertTrue(_scopes_overlap(a, b), (a, b))
        self.assertFalse(_scopes_overlap('docs/', 'src/'))

    def test_export_resolves_reporters_and_decision_participants_only(self):
        task = self.create_task()
        reporter = self.mutate('task.delegate', task['id'], name='Previous reporter')
        self.mutate('task.report', task['id'], token=reporter['token'], summary='Investigated the work')
        current = self.mutate('task.delegate', task['id'], name='Current owner')
        requester = self.call('principal.create', name='Decision requester', kind='agent')
        self.call('grant.create', principal_id=requester['principal']['id'], task_id=task['id'], capabilities=['work'])
        decision = self.mutate('decision.create', task['id'], token=requester['token'],
                               title='Choose behavior', question='Which outcome is intended?', options=['A', 'B'])
        resolver = self.call('principal.create', name='Decision resolver', kind='human')
        unrelated = self.call('principal.create', name='Unrelated agent', kind='agent')
        self.mutate('decision.resolve', task['id'], token=resolver['token'], decision_id=decision['id'], choice='A')

        bundle = self.store.export(self.operator, task['id'])
        identities = {principal['id'] for principal in bundle['principals']}
        self.assertEqual(identities, {task['created_by'], reporter['principal']['id'], current['principal']['id'],
                                     requester['principal']['id'], resolver['principal']['id']})
        self.assertNotIn(unrelated['principal']['id'], identities)
        self.assertTrue(verify_bundle(bundle)['valid'])
        for result in (reporter, current, requester, resolver, unrelated):
            self.assertNotIn(result['token'], canonical(bundle))


if __name__ == '__main__':
    unittest.main()
