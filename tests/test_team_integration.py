"""Production Team hookup through real workflow, builder and root acceptance."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import builder
from golden_benchmark import GOAL, Trial
import proof
import root_gate
from test_builder import plan as legacy_builder_plan
import workflow


class ProductionTeamIntegration(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.project = Path(folder.name).resolve() / 'project'
        self.trial = Trial(self.project, ROOT, {})
        self.trial.setup()
        self.goal = self.project / GOAL
        self.contract = proof.load(self.goal / 'root-contract.json')
        self.contract.pop('protocol')
        self.contract['production_team'] = 'mission'
        proof.save(self.goal / 'root-contract.json', self.contract)
        proof.save(self.goal / 'root-seal.json', {
            'root_hash': proof.digest(self.contract), 'request_sha256': self.contract['request_sha256'],
            'sealed_at': proof.now(),
        })
        self.spec = self.trial.plan
        self.spec.pop('golden')
        self.team_binding = {'plan_sha256': 'a' * 64,
                             'tasks': {'sum': {'outputs': ['addition.py'], 'depends_on': []},
                                       'product': {'outputs': ['multiplication.py'], 'depends_on': []}},
                             'integration_outputs': ['tool_cli.py']}
        self.team = SimpleNamespace(binding=Mock(return_value=self.team_binding),
                                    verify_registered=Mock(return_value={'passed': True, 'errors': []}))
        modules = patch.dict(sys.modules, {'team': self.team})
        modules.start()
        self.addCleanup(modules.stop)

    def workflow_command(self, *args):
        out, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(errors):
            code = workflow.main(['--project', str(self.project), *args])
        return code, out.getvalue(), errors.getvalue()

    def test_workflow_bindings_require_real_scoped_implementation_nodes(self):
        linked = workflow.validate_bindings(self.project, self.spec)
        self.assertEqual(linked['production_team'], self.team_binding)
        self.team.binding.assert_called_once_with(self.project, 'mission', self.contract['request_sha256'])
        cases = (
            ('role', 'review', 'must match'),
            ('execution', 'serial', 'native implementation worker'),
            ('write_scope', [], 'write scope must include'),
        )
        for field, value, diagnostic in cases:
            with self.subTest(field=field):
                changed = deepcopy(self.spec)
                changed['tasks'][0][field] = value
                with self.assertRaisesRegex(ValueError, diagnostic):
                    workflow.validate_bindings(self.project, changed)
        changed = deepcopy(self.spec)
        changed['tasks'][-1]['write_scope'] = ['addition.py']
        with self.assertRaisesRegex(ValueError, 'integration can write it'):
            workflow.validate_bindings(self.project, changed)
        self.team_binding['tasks']['product']['depends_on'] = ['sum']
        with self.assertRaisesRegex(ValueError, 'must follow its registered production team dependencies'):
            workflow.validate_bindings(self.project, self.spec)

    def test_direct_root_and_stop_hook_require_team_qa_with_passing_runtime(self):
        with redirect_stdout(io.StringIO()):
            for node in self.spec['tasks']:
                path = self.project / node['proof_task']
                self.assertTrue(proof.run_check(path, 'addition')['passed'])
                proof.update_step(path, 'T01', 'VERIFIED', 'Executed actual CLI and checked the expected result.')
        proof.save(self.project / '.runtime-proof/active.json', {
            'task': 'integration', 'root_goal': 'mission', 'root_required': True,
        })
        self.team.verify_registered.return_value = {'passed': False, 'errors': ['Native implementation receipts are missing']}
        refused = root_gate.check_root(self.goal)
        self.assertFalse(refused['root_goal_achieved'])
        self.assertTrue(all(item['passed'] for item in refused['requirements']))
        self.assertIn('Production team: Native implementation receipts are missing', refused['errors'])
        self.team.verify_registered.assert_called_once_with(self.project, 'mission', require_qa=True)
        self.assertEqual(proof.hook({'cwd': str(self.project)})['decision'], 'block')
        self.team.verify_registered.return_value = {'passed': True, 'errors': []}
        self.assertTrue(root_gate.check_root(self.goal)['root_goal_achieved'])
        self.assertEqual(proof.hook({'cwd': str(self.project)}), {})

        self.team_binding['integration_outputs'] = ['extra.py']
        orphan = root_gate.check_root(self.goal)
        self.assertFalse(orphan['root_goal_achieved'])
        self.assertTrue(any('proof must fingerprint Team output: extra.py' in e for e in orphan['errors']))

    def test_builder_registration_and_claim_cannot_bypass_milestones(self):
        self.spec['tasks'][2].update(role='integrate')
        self.spec['tasks'][2].pop('reviews')
        self.spec['build'] = legacy_builder_plan()['build']
        self.spec['build']['host'].update(delegation_available=True, max_parallel_workers=2)
        first, final = self.spec['build']['milestones']
        first.update(tasks=['sum', 'product', 'qa'], integration_task='qa', requirements=['SUM', 'PRODUCT'])
        final['tasks'] = ['integration']
        final.update(integration_task='integration', requirements=['COMBINED'])
        plan_file = self.project / 'team-build.json'
        proof.save(plan_file, self.spec)
        code, _, error = self.workflow_command('init', '--plan', str(plan_file))
        self.assertEqual(code, 2)
        self.assertIn('Use builder.py init', error)

        self.assertTrue(builder.register(self.project, self.spec)['created'])
        code, _, error = self.workflow_command('claim', '--goal', 'mission', '--task', 'sum',
                                               '--worker', 'fixture-worker', '--lease-seconds', '120')
        self.assertEqual(code, 2)
        self.assertIn('Use builder.py claim', error)
        store, saved, shape = builder.open_build(self.project, 'mission')
        self.assertEqual(store.inspect('mission')[0]['state'], 'TODO')
        with self.assertRaisesRegex(ValueError, 'Earlier milestone integration'):
            builder.claim(self.project, store, saved, shape, 'integration', 'fixture-worker', 120)
        self.assertEqual(builder.claim(self.project, store, saved, shape, 'sum', 'fixture-worker', 120)['task'], 'sum')


if __name__ == '__main__':
    unittest.main()
