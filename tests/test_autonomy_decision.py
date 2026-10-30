"""Negative and positive controls for the advisory autonomy interruption policy."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import json
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import autonomy_decision as agent


class AutonomyDecisionTests(unittest.TestCase):
    def outcome(self, event, allowed=True):
        return agent.decide({'event': event, 'authorized_independent_work': allowed})

    def assert_not_authorized(self, item):
        self.assertFalse(item['grants_new_permission'])
        self.assertFalse(item['gated_action_is_authorized'])
        self.assertEqual(item['root_goal_verified'], 'NOT_EVALUATED')
        self.assertTrue(item['must_preserve_completed_work'])

    def test_optional_leader_timeout_is_not_user_absent(self):
        actual = self.outcome('OPTIONAL_CONSULTATION_UNAVAILABLE')
        self.assertEqual(actual['decision'], 'CONTINUE_AUTONOMOUSLY')
        self.assertIn('does not prove the user is absent', actual['next_action'])
        self.assert_not_authorized(actual)

    def test_optional_leader_without_authorized_work_is_skipped(self):
        actual = self.outcome('OPTIONAL_CONSULTATION_UNAVAILABLE', False)
        self.assertEqual(actual['decision'], 'SKIP_OPTIONAL_CONSULTATION')
        self.assertFalse(actual['may_continue_previously_authorized_independent_work'])
        self.assert_not_authorized(actual)

    def test_required_approval_timeout_blocks_only_protected_action(self):
        actual = self.outcome('REQUIRED_APPROVAL_UNAVAILABLE')
        self.assertEqual(actual['decision'], 'CONTINUE_OTHER_AUTHORIZED_WORK')
        self.assertTrue(actual['may_continue_previously_authorized_independent_work'])
        self.assert_not_authorized(actual)

    def test_required_approval_timeout_with_no_other_work(self):
        actual = self.outcome('REQUIRED_APPROVAL_UNAVAILABLE', False)
        self.assertEqual(actual['decision'], 'AWAIT_EXPLICIT_APPROVAL')
        self.assert_not_authorized(actual)

    def test_soft_time_estimate_not_mission_limit(self):
        actual = self.outcome('SOFT_TIME_ESTIMATE_EXCEEDED')
        self.assertEqual(actual['decision'], 'CONTINUE_GOAL_WORK')
        self.assert_not_authorized(actual)

    def test_soft_time_estimate_never_overrides_admission(self):
        actual = self.outcome('SOFT_TIME_ESTIMATE_EXCEEDED', False)
        self.assertEqual(actual['decision'], 'CHECK_ACTUAL_AUTHORITY')
        self.assert_not_authorized(actual)

    def test_command_timeout_requests_diagnosis_not_infinite_wait(self):
        actual = self.outcome('COMMAND_TIMEOUT')
        self.assertEqual(actual['decision'], 'DIAGNOSE_AND_RETRY_IF_JUSTIFIED')
        self.assert_not_authorized(actual)

    def test_command_timeout_no_safe_work_pauses(self):
        actual = self.outcome('COMMAND_TIMEOUT', False)
        self.assertEqual(actual['decision'], 'CHECKPOINT_PAUSE')

    def test_real_host_limit_cannot_be_ignored(self):
        actual = self.outcome('HOST_HARD_LIMIT')
        self.assertEqual(actual['decision'], 'CHECKPOINT_FOR_RESUME')
        self.assertFalse(actual['may_continue_previously_authorized_independent_work'])
        self.assert_not_authorized(actual)

    def test_resource_denial_never_becomes_credit_permission(self):
        actual = self.outcome('RESOURCE_ADMISSION_DENIED')
        self.assertEqual(actual['decision'], 'CONTINUE_OTHER_AUTHORIZED_WORK')
        self.assert_not_authorized(actual)

    def test_resource_denial_with_nothing_else_is_action_required(self):
        actual = self.outcome('RESOURCE_ADMISSION_DENIED', False)
        self.assertEqual(actual['decision'], 'AWAIT_EXTERNAL_AUTHORIZATION')
        self.assert_not_authorized(actual)

    def test_stagnation_needs_new_hypothesis(self):
        actual = self.outcome('NO_PROGRESS')
        self.assertEqual(actual['decision'], 'REPLAN_WITH_FALSIFIABLE_NEXT_STEP')
        self.assert_not_authorized(actual)

    def test_no_progress_and_no_authorized_next_step(self):
        actual = self.outcome('NO_PROGRESS', False)
        self.assertEqual(actual['decision'], 'CHECKPOINT_STALLED')

    def test_invalid_event_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown event'):
            self.outcome('IGNORE_REAL_HOST_LIMIT')

    def test_missing_authority_classification_rejected(self):
        with self.assertRaisesRegex(ValueError, 'explicit boolean'):
            agent.decide({'event': 'SOFT_TIME_ESTIMATE_EXCEEDED'})

    def test_string_bool_rejected(self):
        with self.assertRaisesRegex(ValueError, 'explicit boolean'):
            agent.decide({'event': 'RESOURCE_ADMISSION_DENIED', 'authorized_independent_work': 'true'})

    def test_cli_reads_json_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as path:
            p = Path(path)/'input.json'
            p.write_text(json.dumps({'event': 'OPTIONAL_CONSULTATION_UNAVAILABLE',
                                     'authorized_independent_work': True}), encoding='utf-8')
            before = p.read_bytes()
            result = subprocess.run([sys.executable, str(ROOT/'scripts'/'autonomy_decision.py'),
                                     '--input', str(p)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'CONTINUE_AUTONOMOUSLY')
            self.assertEqual(before, p.read_bytes())


if __name__ == '__main__':
    unittest.main()
