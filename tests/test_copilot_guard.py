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
        for name in ('view', 'grep', 'glob', 'powershell', 'bash', 'task'):
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
        self.assertEqual(hook['exec'], sys.executable)
        result = subprocess.run([hook['exec'], *hook['args']], input=json.dumps(self.event()),
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['permissionDecision'], 'deny')
        inactive = subprocess.run([hook['exec'], *hook['args']],
                                  input=json.dumps({**self.event(), 'sessionId': str(uuid4())}),
                                  capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(inactive.stdout), {})

    def test_current_real_team_admission_and_stale_records(self):
        data = fixture.CorporateTests('test_actual_runtime_and_all_quality_rows_pass')
        self.addCleanup(data.tearDown)
        data.setUp()
        data.team_plan['host'] = {'kind': 'copilot'}
        goal, state, _ = data.reviewed_draft()
        self.project, self.goal = data.project, goal.name
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
        checks = (admission_path, goal / 'root-seal.json', goal / 'corporate-plan.json',
                  self.project / f'.runtime-proof/teams/{self.goal}/receipts/plan_review.json')
        for location in checks:
            with self.subTest(changed=location.name):
                old = location.read_bytes()
                report = proof.load(location)
                report['drift'] = 'changed after admission'
                proof.save(location, report)
                self.denied(self.event())
                location.write_bytes(old)
                self.assertEqual(self.decide(self.event()), {})


if __name__ == '__main__':
    unittest.main()
