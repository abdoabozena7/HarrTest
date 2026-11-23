"""Behavioral and edge-case tests for the execution-threshold-v1 contract."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import execution_gate


class ExecutionGateTests(unittest.TestCase):
    def test_ordinary_daily_tasks_stay_direct_without_subagents_or_branches(self):
        cases = [
            ('data_fetch', {'kind': 'data_or_script', 'estimated_write_files': 1}, 'direct', 1),
            ('single_page', {'kind': 'single_surface', 'estimated_write_files': 2}, 'direct', 1),
            ('small_bugfix', {'kind': 'localized_change', 'estimated_write_files': 3}, 'direct', 1),
            ('small_greenfield', {'kind': 'greenfield_product', 'estimated_write_files': 3}, 'direct', 1),
            ('pure_query', {'kind': 'read_only'}, 'read-only', 0),
        ]
        for label, signals, expected_tier, expected_owners in cases:
            with self.subTest(case=label):
                res = execution_gate.evaluate({'task_signals': signals}, env={})
                self.assertEqual(res['tier'], expected_tier)
                self.assertFalse(res['needs_subagents'])
                self.assertFalse(res['needs_independent_qa'])
                self.assertFalse(res['needs_branch'])
                self.assertFalse(res['needs_worktree'])
                self.assertFalse(res['split_allowed'])
                self.assertEqual(res['max_implementation_owners'], expected_owners)
                self.assertEqual(res['runtime_ceremony'], 'none')

    def test_high_risk_or_shared_contract_escalates_to_single_owner_not_fanout(self):
        res = execution_gate.evaluate({
            'task_signals': {
                'kind': 'localized_change',
                'estimated_write_files': 2,
                'shared_public_contract': True,
                'high_risk_domains': ['security_boundary'],
            }
        }, env={})
        self.assertEqual(res['tier'], 'managed-single')
        self.assertTrue(res['needs_subagents'])
        self.assertTrue(res['needs_independent_qa'])
        self.assertEqual(res['max_implementation_owners'], 1)
        self.assertFalse(res['split_allowed'])
        self.assertFalse(res['needs_branch'])
        self.assertEqual(res['runtime_ceremony'], 'quickstart')

    def test_multi_owner_split_requires_all_invariants_and_rejects_fake_splits(self):
        rejected = execution_gate.evaluate({
            'user_intent': {'explicit_mode': 'team'},
            'task_signals': {
                'kind': 'cross_cutting_change',
                'estimated_write_files': 5,
                'independent_deliverables': 3,
                'disjoint_write_scopes': True,
                'stable_interface': False,
                'independent_checks': True,
            },
        }, env={})
        self.assertEqual(rejected['tier'], 'managed-single')
        self.assertFalse(rejected['split_allowed'])
        self.assertEqual(rejected['max_implementation_owners'], 1)
        self.assertIn('stable_interface', rejected['split_rejected_reason'])

        accepted = execution_gate.evaluate({
            'task_signals': {
                'kind': 'cross_cutting_change',
                'estimated_write_files': 5,
                'independent_deliverables': 2,
                'disjoint_write_scopes': True,
                'stable_interface': True,
                'independent_checks': True,
            },
        }, env={})
        self.assertEqual(accepted['tier'], 'team-parallel')
        self.assertTrue(accepted['split_allowed'])
        self.assertEqual(accepted['max_implementation_owners'], 2)
        self.assertFalse(accepted['needs_branch'])
        self.assertFalse(accepted['needs_worktree'])

    def test_user_intent_overrides_and_branch_worktree_opt_in_only(self):
        # Conflicting checkouts still do NOT auto-authorize a worktree without user request.
        no_wt = execution_gate.evaluate({
            'task_signals': {
                'kind': 'cross_cutting_change',
                'estimated_write_files': 4,
                'conflicting_checkouts': True,
            },
        }, env={})
        self.assertFalse(no_wt['needs_branch'])
        self.assertFalse(no_wt['needs_worktree'])
        self.assertIn('did not request a branch or worktree', no_wt['isolation_note'])

        # Explicit user forbid_subagents overrides intrinsic risk when not Corporate-enrolled.
        forced_direct = execution_gate.evaluate({
            'user_intent': {'forbid_subagents': True, 'requested_branch': True},
            'task_signals': {
                'kind': 'cross_cutting_change',
                'estimated_write_files': 6,
                'shared_public_contract': True,
                'high_risk_domains': ['security_boundary', 'strict_performance_or_streaming'],
            },
        }, env={})
        self.assertEqual(forced_direct['tier'], 'direct')
        self.assertFalse(forced_direct['needs_subagents'])
        self.assertTrue(forced_direct['needs_branch'])
        self.assertFalse(forced_direct['needs_worktree'])

        # HARRTEST_CORPORATE_GOAL env enrolls Corporate automatically (unless read_only_plan).
        corp = execution_gate.evaluate(
            {'task_signals': {'kind': 'localized_change', 'estimated_write_files': 1}},
            env={'HARRTEST_CORPORATE_GOAL': 'mission'},
        )
        self.assertEqual(corp['tier'], 'corporate')
        self.assertEqual(corp['runtime_ceremony'], 'corporate-v1')

        plan_only = execution_gate.evaluate(
            {
                'user_intent': {'explicit_mode': 'read_only_plan'},
                'task_signals': {'kind': 'cross_cutting_change', 'estimated_write_files': 4},
            },
            env={'HARRTEST_CORPORATE_GOAL': 'mission'},
        )
        self.assertEqual(plan_only['tier'], 'read-only')
        self.assertFalse(plan_only['needs_subagents'])

    def test_rejects_malformed_unknown_or_contradictory_inputs(self):
        bad_payloads = [
            {'unknown_top': True, 'task_signals': {'kind': 'read_only'}},
            {'user_intent': {'requested_subagent': True}, 'task_signals': {'kind': 'read_only'}},
            {
                'user_intent': {'forbid_subagents': True, 'requested_subagents': True},
                'task_signals': {'kind': 'localized_change'},
            },
            {'task_signals': {'kind': 'localized_change', 'estimated_write_files': True}},
            {'task_signals': {'kind': 'localized_change', 'independent_deliverables': 100}},
            {'task_signals': {'kind': 'localized_change', 'high_risk_domains': ['unknown_risk']}},
        ]
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    execution_gate.evaluate(payload, env={})

    def test_template_and_cli_entrypoints_work_end_to_end(self):
        template = ROOT / 'assets/templates/execution-threshold.json'
        direct_run = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'scripts/execution_gate.py'), '--input', str(template)],
            capture_output=True, text=True, env={'PATH': ''},
        )
        self.assertEqual(direct_run.returncode, 0, direct_run.stderr)
        parsed = json.loads(direct_run.stdout)
        self.assertEqual(parsed['tier'], 'direct')
        self.assertFalse(parsed['needs_subagents'])

        with tempfile.TemporaryDirectory() as tmp:
            team_cli = subprocess.run(
                [
                    sys.executable, '-B', str(ROOT / 'scripts/team.py'),
                    '--project', tmp, 'threshold',
                    '--kind', 'single_surface', '--write-files', '1',
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(team_cli.returncode, 0, team_cli.stderr + team_cli.stdout)
            out = json.loads(team_cli.stdout)
            self.assertEqual(out['tier'], 'direct')
            self.assertEqual(out['runtime_ceremony'], 'none')


if __name__ == '__main__':
    unittest.main(verbosity=2)
