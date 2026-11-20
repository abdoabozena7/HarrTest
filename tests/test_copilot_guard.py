"""Copilot readiness decisions, including the observed native patch shape."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

import test_corporate as fixture

import copilot_guard
import proof


class CopilotGuardTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.project = Path(work.name).resolve()
        self.session = str(uuid4())
        self.goal = 'mission'

    def event(self, tool='edit', args=None):
        return {'sessionId': self.session, 'cwd': str(self.project), 'toolName': tool,
                'toolArgs': {'path': 'src/service.py'} if args is None else args}

    def decide(self, event):
        return copilot_guard.decide(self.project, self.goal, self.session, event)

    def denied(self, event):
        self.assertEqual(self.decide(event).get('permissionDecision'), 'deny')

    def test_direct_native_edits_need_admission(self):
        self.denied(self.event('edit', {'path': 'src/service.py', 'old_str': 'old', 'new_str': 'new'}))
        self.denied(self.event('create', json.dumps({'path': 'new_file.py', 'file_text': 'sample'})))
        self.denied(self.event('str_replace_editor', {'command': 'undo_edit', 'path': 'src/service.py'}))

    def test_normal_host_permissions_handle_passive_and_non_enrolled_calls(self):
        for name in ('view', 'grep', 'glob', 'powershell', 'bash'):
            with self.subTest(tool=name):
                self.assertEqual(self.decide(self.event(name)), {})
        self.assertEqual(self.decide(self.event('str_replace_editor', {'command': 'view', 'path': 'x'})), {})
        self.assertEqual(self.decide({**self.event(), 'sessionId': str(uuid4())}), {})
        self.assertEqual(self.decide({**self.event(), 'cwd': str(self.project.parent)}), {})
        self.assertEqual(self.decide(self.event('create', {'path': str(self.project.parent / 'another-checkout/file')})), {})

    def test_private_setup_is_eligible_under_normal_permissions(self):
        self.assertEqual(self.decide(self.event('create', {'path': '.runtime-proof/plan.json'})), {})
        self.assertEqual(self.decide(self.event('edit', {'path': str(self.project / '.runtime-proof/review.txt')})), {})
        self.denied(self.event('create', {'path': '.runtime-proof-other/file'}))
        self.denied(self.event('create', {'path': '.runtime-proof/../actual.py'}))

    def test_parent_blocks_unauthorized_worker_dispatch_before_children_start(self):
        dispatch = {'name': 'component', 'agent_type': 'general-purpose', 'mode': 'background',
                    'description': 'Synthetic component', 'prompt': 'Change the fixture component.'}
        for name in ('component', 'qa', 'plan_review', 'explore'):
            with self.subTest(name=name):
                args = {**dispatch, 'name': name,
                        'agent_type': 'explore' if name == 'explore' else 'general-purpose'}
                self.denied(self.event('task', args))
                self.denied(self.event('task', json.dumps(args)))
        self.denied(self.event('task', 'unstructured task'))
        self.assertEqual(self.decide({**self.event('task', dispatch), 'sessionId': str(uuid4())}), {})
        self.assertEqual(self.decide({**self.event('task', dispatch), 'cwd': str(self.project.parent)}), {})

    def test_raw_native_apply_patch_checks_all_files_and_move_destinations(self):
        # The input is a plain multiline string in the retained Copilot
        # tool execution start event. These file names and contents are fictional.
        body = ('*** Begin Patch\n*** Update File: .runtime-proof/plan.txt\n@@\n-old\n+new\n'
                '*** Update File: src/service with spaces.py\n@@\n-old\n+new\n*** End Patch')
        self.denied(self.event('apply_patch', body))
        self.denied(self.event('apply_patch', {'patch': body}))
        self.denied(self.event('apply_patch', ('*** Begin Patch\n*** Update File: .runtime-proof/plan.txt\n'
                   '*** Move to: src/plan.txt\n@@\n-old\n+new\n*** End Patch')))
        self.assertEqual(self.decide(self.event('apply_patch', ('*** Begin Patch\n'
                         '*** Delete File: .runtime-proof/scratch\n*** End Patch'))), {})

    def test_malformed_matched_active_edit_denies_without_exposing_input(self):
        for args in ([], {}, {'path': None}, {'path': '', 'file_path': 'other'}, 'secret-arg'):
            with self.subTest(args_type=type(args)):
                result = self.decide(self.event('edit', args))
                self.assertEqual(result['permissionDecision'], 'deny')
                self.assertNotIn('secret-arg', result['permissionDecisionReason'])
        for body in ('*** Begin Patch\n*** End Patch', '*** Begin Patch\n*** Unknown: b\n*** End Patch'):
            self.denied(self.event('apply_patch', body))
        self.denied({**self.event(), 'cwd': 'relative'})
        self.assertEqual(self.decide({'toolName': 'edit'}), {})

    def test_generated_local_config_uses_literal_arguments_and_hook_stdout(self):
        command = [sys.executable, '-B', str(fixture.ROOT / 'scripts/copilot_guard.py'), 'config',
                   '--project', str(self.project), '--goal', self.goal, '--session', self.session]
        generated = subprocess.run(command, capture_output=True, text=True, check=True)
        hook = json.loads(generated.stdout)['hooks']['preToolUse'][0]
        self.assertIn('apply_patch', hook['matcher'].split('|'))
        self.assertIn('task', hook['matcher'].split('|'))
        self.assertEqual(hook['exec'], sys.executable)
        result = subprocess.run([hook['exec'], *hook['args']], input=json.dumps(self.event()),
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['permissionDecision'], 'deny')
        inactive = subprocess.run([hook['exec'], *hook['args']],
                                  input=json.dumps({**self.event(), 'sessionId': str(uuid4())}),
                                  capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(inactive.stdout), {})

    def registered_team(self):
        data = fixture.CorporateTests('test_actual_runtime_and_all_quality_rows_pass')
        self.addCleanup(data.tearDown)
        data.setUp()
        data.team_plan['host'] = {'kind': 'copilot'}
        goal, state, _ = data.reviewed_draft()
        self.project, self.goal = data.project, goal.name
        return data, goal, state

    def test_only_the_registered_review_packet_can_dispatch_before_sealing(self):
        data, goal, state = self.registered_team()
        packet = fixture.team_v2.plan_review_packet(self.project, state)
        args = {'name': packet['task_name'], 'prompt': packet['message'], 'agent_type': 'general-purpose',
                'description': 'Inspect the registered scope', 'mode': 'background',
                'model': 'fixture-model', 'reasoning_effort': 'low'}
        self.assertEqual(self.decide(self.event('task', args)), {})
        self.assertEqual(self.decide(self.event('task', json.dumps(args))), {})
        for changes in ({'prompt': args['prompt'] + '\nEdit the product.'}, {'name': 'reviewer'},
                        {'agent_type': 'custom-reviewer'}, {'mode': 'resume'}, {'cwd': str(self.project.parent)},
                        {'resume_agent_id': 'another-worker'}, {'model': None}):
            with self.subTest(changes=list(changes)):
                self.denied(self.event('task', {**args, **changes}))
        original = goal / 'original-request.txt'
        request_bytes = original.read_bytes()
        original.write_bytes(request_bytes + b'\n')
        mismatch = self.decide(self.event('task', args))
        self.assertEqual(mismatch['permissionDecision'], 'deny')
        self.assertIn('root request and registered Team request must match', mismatch['permissionDecisionReason'])
        original.write_bytes(request_bytes)
        changed_packet = self.decide(self.event('task', {**args, 'prompt': args['prompt'] + '\n'}))
        self.assertEqual(changed_packet['permissionDecision'], 'deny')
        self.assertIn('Copy the current plan_review message verbatim', changed_packet['permissionDecisionReason'])
        data.source.write_text('New code appeared before Corporate admission.\n')
        stale = self.decide(self.event('task', args))
        self.assertEqual(stale['permissionDecision'], 'deny')
        self.assertIn('implementation baseline changed', stale['permissionDecisionReason'])

    def test_only_current_corporate_coverage_review_packet_can_dispatch(self):
        _, goal, _ = self.registered_team()
        fixture.corporate.scaffold(goal, 'verify', ['baseline'], 'calculator-owner')
        draft_path = goal / 'root-contract.json'
        draft = proof.load(draft_path)
        packet = fixture.corporate.coverage_packet(goal)
        args = {'name': packet['task_name'], 'prompt': packet['message'], 'agent_type': 'general-purpose'}
        self.assertEqual(args['name'], 'coverage_review')
        self.assertEqual(self.decide(self.event('task', args)), {})
        self.assertIn('Keep product files and the draft read-only', args['prompt'])
        self.denied(self.event('task', {**args, 'prompt': args['prompt'] + '\nExtra instruction.'}))
        self.denied(self.event('task', {**args, 'name': 'implementation'}))
        draft['requirements'][0]['claim'] = 'A revised requirement in the actual draft.'
        proof.save(draft_path, draft)
        self.denied(self.event('task', args))
        current = fixture.corporate.coverage_packet(goal)
        self.assertEqual(self.decide(self.event('task', {**args, 'prompt': current['message']})), {})
        proof.save(goal / 'root-seal.json', {'example': 'Sealed but not admitted'})
        self.denied(self.event('task', {**args, 'prompt': current['message']}))

    def test_rejected_plan_can_be_replaced_without_relaxing_admission(self):
        data, goal, state = self.registered_team()
        prior = fixture.team_v2.plan_review_packet(self.project, state)
        evidence = fixture.team.plan_review_evidence(state)
        (self.project / evidence).write_text('Two proven component responsibilities need distinct checks.',
                                             encoding='utf-8')
        fixture.team_v2.review_plan(self.project, state, evidence, 'fail')
        revised = {**state['plan'], 'contract': state['plan']['contract'] + ' Check the public oracle directly.'}
        packet = fixture.team_v2.revise_plan(self.project, revised)['plan_review']
        args = {'name': 'plan_review', 'prompt': packet['message'], 'agent_type': 'general-purpose'}
        self.denied(self.event('task', {**args, 'prompt': prior['message']}))
        self.assertEqual(self.decide(self.event('task', args)), {})
        self.denied(self.event())
        self.denied(self.event('task', {**args, 'name': 'component'}))
        current = fixture.team.load_state(self.project, self.goal)
        fixture.corporate.scaffold(goal, 'verify', ['baseline'], 'calculator-owner')
        data.fill_reviewed_draft(goal, current)
        root = subprocess.run([sys.executable, '-B', str(fixture.ROOT / 'scripts/root_gate.py'),
                               'seal', '--goal', str(goal)], capture_output=True, encoding='utf-8')
        self.assertEqual(root.returncode, 0, root.stdout + root.stderr)
        fixture.team.ready_packets(self.project, current)
        self.assertEqual(self.decide(self.event()), {})

    def test_current_real_team_admission_and_stale_records(self):
        data, goal, state = self.registered_team()
        fixture.corporate.scaffold(goal, 'verify', ['baseline'], 'calculator-owner')
        data.fill_reviewed_draft(goal, state)
        root = subprocess.run([sys.executable, '-B', str(fixture.ROOT / 'scripts/root_gate.py'),
                               'seal', '--goal', str(goal)], capture_output=True, text=True)
        self.assertEqual(root.returncode, 0, root.stdout + root.stderr)
        self.denied(self.event())
        # Execute the real first-dispatch preflight against the real baseline.
        issued = subprocess.run([sys.executable, '-B', str(fixture.ROOT / 'scripts/team.py'),
                                 '--project', str(self.project), 'packets', '--team', self.goal],
                                capture_output=True, text=True)
        self.assertEqual(issued.returncode, 0, issued.stdout + issued.stderr)
        admission_path = self.project / f'.runtime-proof/teams/{self.goal}/corporate-dispatch.json'
        self.assertTrue(admission_path.is_file())
        self.assertEqual(self.decide(self.event()), {})
        dispatch = self.event('task', {'name': 'component', 'agent_type': 'general-purpose',
                                      'description': 'Fixture implementation task', 'mode': 'background',
                                      'prompt': 'Implement the now admitted fixture change.'})
        self.assertEqual(self.decide(dispatch), {})
        self.assertEqual(self.decide(self.event('task', 'unsupported future task envelope')), {})
        checks = (admission_path, goal / 'root-seal.json', goal / 'corporate-plan.json',
                  self.project / f'.runtime-proof/teams/{self.goal}/receipts/plan_review.json')
        for location in checks:
            with self.subTest(changed=location.name):
                old = location.read_bytes()
                report = proof.load(location)
                report['drift'] = 'changed after admission'
                proof.save(location, report)
                self.denied(self.event())
                self.denied(dispatch)
                location.write_bytes(old)
                self.assertEqual(self.decide(self.event()), {})
                self.assertEqual(self.decide(dispatch), {})


if __name__ == '__main__':
    unittest.main()
