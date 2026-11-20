"""Exercise the mission gates against real source, subprocesses and sealed receipts."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import mission
import project_memory
import proof
import root_gate
import team
import team_v2


APP = """\
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument('label')
p.add_argument('--upper', action='store_true')
args = p.parse_args()
label = args.label
print(json.dumps({'label': label.upper() if args.upper else label}))
"""
ORACLE = """\
import json
import subprocess
import sys

args = ['Ada', '--upper'] if sys.argv[1] in {'option', 'removed'} else []
result = subprocess.run([sys.executable, '-B', 'app.py', *args], capture_output=True, text=True)
print(json.dumps({'label': json.loads(result.stdout)['label'] if result.returncode == 0 else None,
                  'rejected': result.returncode == 2 and 'error:' in result.stderr}))
"""
LEGACY_TEST = """\
import json
import subprocess
import sys

result = subprocess.check_output([sys.executable, '-B', 'app.py', 'Ada', '--upper'])
assert json.loads(result)['label'] == 'ADA'
"""
REQUEST = 'Trim surrounding whitespace in labels and keep rejection of missing positional input.  \n'
GATE_ERROR = (ValueError, proof.ProofError)


class MissionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        area = tmp.name
        self.project = Path(area).resolve() / 'checkout'
        self.project.mkdir()
        state = patch.dict(os.environ, {'HARRTEST_STATE_HOME': str(Path(area) / 'state')})
        state.start()
        self.addCleanup(state.stop)
        self.private = self.project / '.runtime-proof'
        self.private.mkdir()
        self.app = self.project / 'app.py'
        self.app.write_text(APP, encoding='utf-8')
        (self.project / 'oracle.py').write_text(ORACLE, encoding='utf-8')
        self.old_test = self.project / 'legacy_test.py'
        self.old_test.write_text(LEGACY_TEST, encoding='utf-8')
        self.request = REQUEST
        self.sources = ['app.py', 'oracle.py', 'legacy_test.py']

    def cli(self, script, *argv, ok=True):
        cmd = [sys.executable, '-B', str(ROOT / 'scripts' / script), *map(str, argv)]
        result = subprocess.run(cmd, cwd=self.project, capture_output=True, text=True, timeout=30)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def run_checks(self, *checks):
        with contextlib.redirect_stdout(io.StringIO()):
            return {cid: proof.run_check(self.child, cid)['passed'] for cid in checks}

    def prepare(self, *, effect='PRESERVE', second_owner=False, directory_scope=False, register=True, deletable=()):
        new_receipt = 'removed' if effect in {'REMOVE_EXPLICITLY_REQUESTED', 'POTENTIAL_COLLATERAL_CHANGE'} else 'option'
        if effect == 'REMOVE_EXPLICITLY_REQUESTED':
            self.request += 'Remove the --upper option.\n'
        if second_owner:
            self.sources.append('side.py')
        roots = list(self.sources)
        if directory_scope:
            config = self.project / 'inputs'
            config.mkdir()
            (config / 'config.txt').write_text('legacy routing\n', encoding='utf-8')
            self.sources.append('inputs/config.txt')
            roots.append('inputs')
        self.child = self.private / 'runtime'
        self.child.mkdir()
        contract = proof.load(ROOT / 'examples/cli-contract.json')
        contract.update(task_id='runtime', source_paths=roots,
                        absent_source_paths=['app.py', 'legacy_test.py', *deletable]
                        + (['side.py'] if second_owner else []))
        cases = {
            'trim': (['app.py', '  Ada  '], '/label', 'Ada'),
            'invalid': (['oracle.py', 'invalid'], '/rejected', True),
            new_receipt: (['oracle.py', new_receipt], '/rejected' if new_receipt == 'removed' else '/label',
                          True if new_receipt == 'removed' else 'ADA'),
        }
        contract['checks'] = [
            {'id': cid, 'mode': 'live', 'role': 'acceptance' if cid == 'trim' else 'regression',
             'description': 'Exercise the real CLI and independently assert the exact result.',
             'command': ['{python}', '-B', *command], 'expected_exit_codes': [0], 'timeout_seconds': 15,
             'assertions': [{'type': 'json', 'file': 'stdout.log', 'pointer': pointer, 'op': 'eq', 'value': value}],
             'artifacts': []}
            for cid, (command, pointer, value) in cases.items()
        ]
        contract['requirements'][0].update(id='R1', checks=['trim', new_receipt], source_excerpt='Trim surrounding whitespace')
        contract['requirements'].append({**contract['requirements'][0], 'id': 'R2', 'checks': ['invalid'],
                                         'source_excerpt': 'keep rejection of missing positional input'})
        contract['checks'][1]['role'] = 'acceptance'
        contract['plan']['tasks'][0].update(requirements=['R1', 'R2'], checks=list(cases))
        proof.validate_contract(contract)
        proof.save(self.child / 'contract.json', contract)
        proof.save(self.child / 'context.json', {'project': str(self.project), 'root_goal': 'mission'})
        proof.save(self.child / 'seal.json', {'contract_hash': proof.digest(contract), 'engine_hash': proof.engine_hash(contract)})
        baseline = ['invalid'] + (['option'] if new_receipt == 'option' else [])
        self.assertTrue(all(self.run_checks(*baseline).values()))

        self.draft = {
            'schema': 1, 'goal_id': 'mission', 'kind': 'change', 'author': 'fixture-planner',
            'sources': team.snapshot(self.project, self.sources),
            'requirements': {
                'R1': {'claim': 'Trim ASCII surrounding whitespace from labels.', 'excerpt': 'Trim surrounding whitespace'},
                'R2': {'claim': 'Missing positional labels still produce exit two.',
                       'excerpt': 'keep rejection of missing positional input'},
            },
            'tasks': [
                {'id': 'trim', 'requirement_id': 'R1', 'owner': 'component', 'depends_on': [],
                 'description': 'Trim label input while retaining the other rendering mode.',
                 'done': 'Whitespace is ignored; the relevant rendering behavior passes the sealed CLI checks.',
                 'checks': ['runtime/trim', 'runtime/' + new_receipt]},
                {'id': 'reject_missing', 'requirement_id': 'R2', 'owner': 'side' if second_owner else 'component',
                 'depends_on': [], 'description': 'Verify missing positional input and restore entrypoint coverage.',
                 'done': 'The live CLI must still reject no positional input with exit two and a diagnostic.',
                 'checks': ['runtime/invalid']},
            ],
            'features': [
                {'id': 'upper_mode', 'behavior': 'The optional switch uppercases the rendered label.',
                 'location': 'argparse --upper and label.upper()', 'path': 'app.py', 'contract': 'public',
                 'basis': 'observed', 'related_paths': [], 'test_paths': ['legacy_test.py'],
                 'oracle_paths': ['oracle.py'], 'effect': effect, 'reason': 'The actual old CLI supports this switch.',
                 'planned_effect': 'Keep the alternate branch.' if effect == 'PRESERVE' else 'Retire only the uppercase switch.',
                 'uncertainty': None, 'tasks': ['trim'], 'checks': ['runtime/' + new_receipt]},
                {'id': 'missing_input', 'behavior': 'No label causes a nonzero exit with a diagnostic.',
                 'location': 'argparse positional label', 'path': 'app.py', 'contract': 'public', 'basis': 'observed',
                 'related_paths': [], 'test_paths': [], 'oracle_paths': ['oracle.py'], 'effect': 'PRESERVE',
                 'reason': 'The CLI parser requires a positional label.', 'planned_effect': 'Keep the rejection path.',
                 'uncertainty': None, 'tasks': ['reject_missing'], 'checks': ['runtime/invalid']},
            ],
        }
        if effect == 'REMOVE_EXPLICITLY_REQUESTED':
            self.draft['features'][0]['request_excerpt'] = 'Remove the --upper option.'
        if effect == 'POTENTIAL_COLLATERAL_CHANGE':
            self.draft['features'][0].update(
                alternatives='Investigate keeping the switch and a compatibility wrapper; neither can retain this interface.',
                impact='Existing callers that select uppercase formatting must now choose another entrypoint.',
            )
        self.plan = {
            'schema': 2, 'id': 'mission', 'kind': 'change', 'mission_protocol': mission.PROTOCOL,
            'request': self.request, 'contract': 'The label CLI parser and its observable JSON must stay compatible.',
            'outcomes': {key: value['claim'] for key, value in self.draft['requirements'].items()},
            'tasks': [{'id': 'component', 'brief': 'Change label normalization and exercise stable output.',
                       'outputs': ['app.py', 'legacy_test.py'], 'depends_on': [],
                       'outcomes': ['R1'] if second_owner else ['R1', 'R2']}],
            'integration': {'outputs': [], 'check': 'Re-run the actual old and new CLI behavior with separate QA.'},
            'host': {'kind': 'unverified'},
        }
        if second_owner:
            self.plan['max_parallel_workers'] = 2
            self.plan['tasks'].append({'id': 'side', 'brief': 'Add a separate caller-side helper without changing the product parser.',
                                       'outputs': ['side.py'], 'depends_on': [], 'outcomes': ['R2']})
        if register:
            self.enroll()

    def enroll(self):
        request = self.project / 'request.txt'
        request.write_text(self.request, encoding='utf-8', newline='')
        proof.save(self.private / 'mission-draft.json', self.draft)
        self.cli('mission.py', '--project', '.', '--goal', 'mission', 'init', '--plan',
                 '.runtime-proof/mission-draft.json', '--request-file', 'request.txt')
        self.active = mission.open_mission(self.project, 'mission')

    def register_team(self):
        result = team.init(self.project, self.plan)
        self.state = team.load_state(self.project, 'mission')
        return result

    def candidate(self, *, removal=False, adjacent_regression=False):
        body = APP.replace('label = args.label', 'label = args.label.strip()')
        if removal:
            body = body.replace("p.add_argument('--upper', action='store_true')\n", '')
            body = body.replace('label.upper() if args.upper else label', 'label')
        elif adjacent_regression:
            body = body.replace('label.upper() if args.upper', 'label.lower() if args.upper')
        self.app.write_text(body, encoding='utf-8')

    def implementation_done(self, *, all_tasks=True):
        for tid in ('trim', 'reject_missing') if all_tasks else ('trim',):
            self.active.step(tid, 'IN_PROGRESS', 'Start the admitted implementation scope.')
            self.active.step(tid, 'IMPLEMENTED', 'Changed the implementation; acceptance is still pending.')

    def integrate_team(self):
        team.handoff(self.project, self.state, self.plan['tasks'][0])
        receipt, packet = team.integrate(self.project, self.state)
        self.assertIn('review-input', packet['message'])
        team.runtime_check(self.project, self.state, [sys.executable, '-B', 'app.py', '  Ada  '])
        return receipt

    def review(self):
        body = self.active.review_input()
        body.update(method='fresh-context-agent', reviewer='independent-fixture-actor')
        for section in ('tasks', 'features', 'changed_tests'):
            for item in body[section].values():
                item.update(verdict='PASS',
                            observations='Inspected actual normal output, alternate mode and missing-input process evidence.')
        return body

    def qa(self, body):
        path = self.private / 'teams/mission/independent-qa.json'
        proof.save(path, body)
        return team.review(self.project, self.state, path.relative_to(self.project).as_posix(), 'pass')

    def root(self, *, managed=True):
        request = self.project / 'request.txt'
        request.write_text(self.request, encoding='utf-8', newline='')
        self.cli('root_gate.py', 'init', '--project', self.project, '--id', 'mission', '--request-file', request)
        goal = root_gate.root_dir(self.project, 'mission')
        contract = {
            'schema': 2, 'goal_id': 'mission', 'request_sha256': proof.file_hash(goal / 'original-request.txt'),
            'scope_statement': 'Verify the actual label and missing-input contracts on the integrated CLI.',
            'coverage_review': {'method': 'fresh-context-agent', 'unmapped_segments': [],
                                'rationale': 'Compare the two requested outcomes with the real process results.'},
            'requirements': [
                {'id': rid, 'claim': row['claim'], 'source': 'user_request', 'source_excerpt': row['excerpt'],
                 'oracle': 'Compare exact CLI output and the actual rejected process status.',
                 'evidence_mode': 'live', 'satisfiers': [{'task_id': 'runtime', 'requirement_id': rid}]}
                for rid, row in self.draft['requirements'].items()
            ],
            'integration': {'task_id': 'runtime', 'requirement_id': 'R1',
                            'scope': 'Invoke the real integrated CLI for normal and alternate inputs.'},
        }
        if managed:
            contract['mission_protocol'] = mission.PROTOCOL
        proof.save(goal / 'root-contract.json', contract)
        return goal

    def test_fresh_process_recovers_exact_request_unfinished_work_and_stale_feature(self):
        self.prepare()
        self.register_team()
        self.active.step('trim', 'IN_PROGRESS', 'Work was started before the first session stopped.')
        self.candidate()
        found = json.loads(self.cli('mission.py', '--project', '.', 'list').stdout)
        self.assertEqual(found['goal_ids'], ['mission'])
        self.assertEqual(Path(found['project']), self.project)
        result = self.cli('mission.py', '--project', '.', '--goal', 'mission', 'status')
        resumed = json.loads(result.stdout)
        rendered = json.dumps(resumed)
        self.assertEqual(resumed['original_request'], self.request)
        self.assertEqual(project_memory.Memory(self.project).goal('mission')['text'], self.request)
        self.assertIn('IN_PROGRESS', rendered)
        self.assertIn('upper_mode', rendered)
        self.assertIn(self.draft['tasks'][0]['done'], rendered)
        self.assertIn('stale', rendered.lower())
        self.cli('mission.py', '--project', '.', '--goal', 'mission', 'pre-edit', '--owner', 'component', ok=False)
        self.cli('mission.py', '--project', '.', '--goal', 'mission', 'refresh', '--note',
                 'Read the parser and the whitespace normalization against the original option oracle.')
        self.cli('mission.py', '--project', '.', '--goal', 'mission', 'pre-edit', '--owner', 'component')
        self.assertEqual(mission.open_mission(self.project, 'mission').plan['sources'], self.draft['sources'])

    def test_undocumented_mode_replays_through_real_team_handoff_and_qa(self):
        self.prepare()
        self.assertNotIn('--upper', self.request)
        packets = self.register_team()['ready']
        self.assertIn('upper_mode', packets[0]['message'])
        self.assertIn('legacy_test.py', packets[0]['message'])
        self.implementation_done()
        self.candidate()
        self.integrate_team()
        self.assertEqual(self.run_checks('option', 'trim', 'invalid'), {'option': True, 'trim': True, 'invalid': True})
        self.qa(self.review())
        team_v2.verify_structural(self.project, self.state, True)
        self.active.verify()
        self.assertFalse(team.verify_registered(self.project, 'mission')['passed'],
                         'Managed acceptance must not bypass native host provenance')

    def test_rejects_deleted_inventoried_source_even_in_declared_file_deletion(self):
        self.prepare()
        self.active.admit('component')
        self.app.unlink()
        with self.assertRaisesRegex(GATE_ERROR, 'upper_mode|preserv|delet|absen'):
            self.active.guard_candidate(['app.py'])

    def test_compatible_relocation_into_existing_module_replays_without_approval(self):
        source, destination = self.project / 'old_mode.py', self.project / 'formatters.py'
        implementation = 'def uppercase(label):\n    return label.upper()\n'
        source.write_text(implementation, encoding='utf-8')
        destination.write_text('def identity(label):\n    return label\n', encoding='utf-8')
        original_app = 'from old_mode import uppercase\n' + APP.replace('label.upper()', 'uppercase(label)')
        self.app.write_text(original_app, encoding='utf-8')
        self.sources += [source.name, destination.name]
        self.prepare(register=False, deletable=[source.name])
        self.draft['features'][0].update(path=source.name, location='uppercase(label)',
                                         related_paths=['app.py'], relocation=destination.name)
        self.enroll()
        self.assertTrue(self.active.admit('component'))
        source.unlink()
        with self.assertRaisesRegex(GATE_ERROR, 'proof|replay'):
            self.active.guard_candidate()
        self.app.write_text(original_app.replace('from old_mode', 'from formatters')
                            .replace('label = args.label', 'label = args.label.strip()'), encoding='utf-8')
        destination.write_text(destination.read_text(encoding='utf-8') + '\n' + implementation, encoding='utf-8')
        self.assertTrue(all(self.run_checks('option', 'invalid', 'trim').values()))
        self.assertTrue(self.active.guard_candidate())

    def test_rejects_unavoidable_collateral_before_edit_but_issues_independent_owner(self):
        self.prepare(effect='POTENTIAL_COLLATERAL_CHANGE', second_owner=True)
        packets = self.register_team()['ready']
        self.assertEqual([row['task_name'] for row in packets], ['side'])
        statuses = {row['id']: row['status'] for row in self.active.context()['tasks']}
        self.assertEqual(statuses['trim'], 'BLOCKED_APPROVAL')
        self.assertEqual(statuses['reject_missing'], 'TODO')
        self.assertFalse(self.active.admit('component'))
        self.assertFalse(self.active.admit('side'),
                         'Standalone admission cannot assume shared files are read-only; the Team packet has disjoint writes')
        with self.assertRaisesRegex(GATE_ERROR, 'scoped user reply'):
            self.active.decision('upper_mode', 'approve', 'I approve removing --other rather than --upper.',
                                 'fixture unrelated user reply')
        self.candidate(removal=True)
        with self.assertRaisesRegex(GATE_ERROR, 'approv|authori|admi'):
            team.handoff(self.project, self.state, self.plan['tasks'][0])
        response = self.private / 'fixture-user-response.txt'
        effect = self.draft['features'][0]['planned_effect']
        response.write_text(f'I approve: {effect}', encoding='utf-8')
        args = ('--project', '.', '--goal', 'mission', 'decision', '--feature', 'upper_mode', '--verdict',
                'approve', '--response', '.runtime-proof/fixture-user-response.txt', '--origin', 'fixture-user-turn-2')
        self.cli('mission.py', *args, ok=False)
        self.app.write_text(APP, encoding='utf-8')
        self.cli('mission.py', *args)
        self.assertIn('component', {row['task_name'] for row in team.ready_packets(self.project, self.state)})
        self.active.step('trim', 'IN_PROGRESS', 'The user approved the bounded option removal.')
        self.candidate(removal=True)
        self.active.step('trim', 'IMPLEMENTED', 'The requested normalization and approved option removal are present.')
        team.handoff(self.project, self.state, self.plan['tasks'][0])
        self.assertTrue(all(self.run_checks('removed', 'trim', 'invalid').values()))

    def test_explicit_removal_requires_no_second_user_decision(self):
        self.prepare(effect='REMOVE_EXPLICITLY_REQUESTED')
        self.assertEqual([row['task_name'] for row in self.register_team()['ready']], ['component'])
        self.implementation_done()
        self.candidate(removal=True)
        self.old_test.write_text(
            "import subprocess, sys\n"
            "result = subprocess.run([sys.executable, '-B', 'app.py', 'Ada', '--upper'], capture_output=True)\n"
            "assert result.returncode == 2 and b'unrecognized arguments' in result.stderr\n", encoding='utf-8')
        self.integrate_team()
        self.assertTrue(all(self.run_checks('removed', 'trim', 'invalid').values()))
        review = self.review()
        review['changed_tests']['legacy_test.py']['observations'] = (
            'The original uppercase assertion was replaced only for the user-authorized removal; the sealed oracle '
            'now confirms --upper is specifically rejected and missing positional input still returns exit two.')
        self.qa(review)
        self.active.verify()

    def test_rejects_unrelated_request_excerpt_as_permission_to_remove_an_option(self):
        self.prepare(effect='REMOVE_EXPLICITLY_REQUESTED', register=False)
        unrelated = 'Remove --other instead of --upper.'
        for excerpt in ('Trim surrounding whitespace', unrelated):
            with self.subTest(excerpt=excerpt):
                self.draft['features'][0]['request_excerpt'] = excerpt
                with self.assertRaisesRegex(GATE_ERROR, 'authorization|feature|remov'):
                    mission.initialize(self.project, self.draft, self.request + unrelated, 'fixture request')

    def test_rejects_adjacent_option_regression_even_though_requested_fix_passes(self):
        self.prepare()
        self.register_team()
        self.implementation_done()
        self.candidate(adjacent_regression=True)
        self.integrate_team()
        self.assertEqual(self.run_checks('trim', 'option', 'invalid'), {'trim': True, 'option': False, 'invalid': True})
        with self.assertRaisesRegex(GATE_ERROR, 'option|passing|failed'):
            self.qa(self.review())
        evidence = '.runtime-proof/teams/mission/failed-option.json'
        proof.save(self.project / evidence, {'observation': 'The admitted CLI lowercased Ada in uppercase mode.'})
        team.review(self.project, self.state, evidence, 'fail')
        repair = team.repair(self.project, self.state, 'component', evidence,
                             'Compare the uppercase branch with the original and restore its observable result.')
        self.assertFalse(repair['mission_complete'])
        self.active.refresh('Compared the affected parser and lowercasing branch with its original baseline.')
        packets = team.ready_packets(self.project, self.state)
        self.assertEqual([row['task_name'] for row in packets], ['component'])
        self.implementation_done()
        self.candidate()
        self.integrate_team()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        self.qa(self.review())
        team_v2.verify_structural(self.project, self.state, True)

    def test_rejects_drift_between_discovery_and_pre_edit(self):
        self.prepare(register=False)
        (self.project / 'oracle.py').write_text(ORACLE + '\n# changed dependency\n', encoding='utf-8')
        with self.assertRaisesRegex(GATE_ERROR, 'stale|current|changed|baseline|source'):
            mission.initialize(self.project, self.draft, self.request, 'test request')

    def test_long_crlf_request_is_retained_and_linked_from_real_worker_packet(self):
        self.request = REQUEST.replace('\n', '\r\n') + 'Use the actual project instructions and source.  \r\n' * 180
        self.prepare()
        goal = self.root()
        request = goal / 'original-request.txt'
        self.assertEqual(request.read_bytes(), self.request.encode('utf-8'))
        packet = self.register_team()['ready'][0]['message']
        self.assertIn('upper_mode', packet)
        self.assertIn('state.json', packet)
        self.assertEqual(self.state['plan']['request'], self.request)

    def test_rejects_incomplete_ledger_even_when_child_and_root_behavior_checks_pass(self):
        self.prepare()
        goal = self.root()
        self.cli('root_gate.py', 'seal', '--goal', goal)
        self.assertTrue(self.active.admit('component'))
        self.implementation_done(all_tasks=False)
        self.candidate()
        self.active.integrate()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        proof.update_step(self.child, 'T01', 'VERIFIED', 'All legacy child executions are current and passing.')
        self.assertTrue(proof.verify(self.child)['passed'])
        root = root_gate.check_root(goal)
        self.assertFalse(root['root_goal_achieved'])
        self.assertIn('reject_missing', json.dumps(self.active.context()))
        self.assertRegex(' '.join(root['errors']), r'(?i)mission|ledger|TODO|review')
        self.active.step('reject_missing', 'IN_PROGRESS', 'Resume the outstanding check and edge case.')
        self.active.step('reject_missing', 'IMPLEMENTED', 'Missing-input behavior was reproduced in the real process.')
        self.active.integrate()
        self.active.accept_review(self.review())
        self.assertTrue(root_gate.check_root(goal)['root_goal_achieved'])

    def test_rejects_premature_verified_and_stale_run_evidence(self):
        self.prepare()
        self.register_team()
        with self.assertRaisesRegex(GATE_ERROR, 'VERIFIED|evidence|transition'):
            self.active.step('trim', 'VERIFIED', 'The implementer merely declared completion.')
        self.implementation_done()
        self.candidate()
        self.integrate_team()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        prior = self.review()
        self.qa(prior)
        self.assertTrue(self.run_checks('option')['option'])
        with self.assertRaisesRegex(GATE_ERROR, 'stale|review|receipt|evidence|check'):
            self.active.verify()
        with self.assertRaisesRegex(GATE_ERROR, 'stale|review|receipt|evidence|check'):
            self.qa(prior)

    def test_rejects_standalone_review_and_checks_from_before_reopen(self):
        self.prepare()
        self.assertTrue(self.active.admit('component'))
        self.candidate()
        self.implementation_done()
        self.active.integrate()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        prior = self.review()
        self.active.accept_review(prior)
        self.active.reopen('component', 'A review finding requires repeating validation on the same source.')
        self.assertTrue(self.active.admit('component'))
        self.implementation_done()
        self.active.integrate()
        with self.assertRaisesRegex(GATE_ERROR, 'ledger_epoch'):
            self.active.accept_review(prior)
        with self.assertRaisesRegex(GATE_ERROR, 'latest reopen'):
            self.active.accept_review(self.review())
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        self.active.accept_review(self.review())
        self.active.verify()

    def test_rejects_root_satisfier_from_a_different_goal(self):
        self.prepare()
        goal = self.root()
        context = self.child / 'context.json'
        original = proof.load(context)
        proof.save(context, {**original, 'root_goal': 'unrelated'})
        rejected = self.cli('root_gate.py', 'seal', '--goal', goal, ok=False)
        self.assertIn('different project, task or root goal', rejected.stderr + rejected.stdout)
        proof.save(context, original)
        self.cli('root_gate.py', 'seal', '--goal', goal)

    def test_environment_blocker_stays_unfinished_until_explicit_recovery(self):
        self.prepare()
        note = 'Execution host cannot run the required integration check.'
        self.active.step('trim', 'BLOCKED_ENVIRONMENT', note)
        self.assertFalse(self.active.admit('component'))
        task = next(item for item in self.active.context()['tasks'] if item['id'] == 'trim')
        self.assertEqual((task['status'], task['blocking_reason']), ('BLOCKED_ENVIRONMENT', note))
        recovered = self.active.reopen('component', 'The missing execution host is now available.')
        self.assertEqual(recovered['tasks'], ['trim'])
        self.assertTrue(self.active.admit('component'))

    def test_rejects_changed_tests_without_assurance_review(self):
        self.prepare()
        self.register_team()
        self.implementation_done()
        self.candidate()
        self.old_test.write_text("assert True  # weaker replacement\n", encoding='utf-8')
        self.integrate_team()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        review = self.review()
        self.assertIn('legacy_test.py', review['changed_tests'])
        del review['changed_tests']['legacy_test.py']
        with self.assertRaisesRegex(GATE_ERROR, 'changed_tests|test|review'):
            self.qa(review)

    def test_rejects_old_oracle_replacement_even_with_self_reported_passing_output(self):
        self.prepare()
        self.register_team()
        self.implementation_done()
        self.candidate(adjacent_regression=True)
        (self.project / 'oracle.py').write_text('print(\'{"label":"ADA","rejected":true}\')\n', encoding='utf-8')
        with self.assertRaisesRegex(GATE_ERROR, 'oracle|frozen|changed'):
            self.integrate_team()

    def test_rejects_new_file_in_proof_scope_after_qa(self):
        self.prepare(directory_scope=True)
        self.register_team()
        self.implementation_done()
        self.candidate()
        self.integrate_team()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        self.qa(self.review())
        (self.project / 'inputs/plugin.txt').write_text('new input after verification\n', encoding='utf-8')
        with self.assertRaisesRegex(GATE_ERROR, 'source|scope|current|proof'):
            self.active.verify()

    def test_workflow_claim_withholds_lease_until_scoped_approval(self):
        self.prepare(effect='POTENTIAL_COLLATERAL_CHANGE')
        goal = self.root()
        self.cli('root_gate.py', 'seal', '--goal', goal)
        plan = self.private / 'workflow.json'
        proof.save(plan, {
            'schema': 1, 'goal_id': 'mission', 'root_goal': '.runtime-proof/root-goals/mission',
            'tasks': [{'id': 'component', 'proof_task': '.runtime-proof/runtime', 'role': 'integrate',
                       'outcome': 'Change and integrate the live label CLI with retained validation.',
                       'write_scope': ['app.py'], 'read_scope': ['oracle.py'], 'depends_on': []}],
        })
        self.cli('workflow.py', '--project', '.', 'init', '--plan', plan)
        claim = ('--project', '.', 'claim', '--goal', 'mission', '--task', 'component',
                 '--worker', 'fixture-workflow-actor', '--lease-seconds', '60')
        denied = self.cli('workflow.py', *claim, ok=False)
        self.assertIn('blocked', denied.stderr.lower())
        self.active.decision('upper_mode', 'approve', 'approve upper_mode', 'fixture user turn')
        granted = json.loads(self.cli('workflow.py', *claim).stdout)
        self.assertTrue(granted['token'])
        self.assertEqual(granted['packet']['mission_sha256'], self.active.binding)
        artifact = self.private / 'workflow-handoff.json'
        proof.save(artifact, {'observation': 'Changed the current app, pending independent verification.'})
        handoff = ('--project', '.', 'handoff', '--goal', 'mission', '--task', 'component',
                   '--token', granted['token'], '--evidence', artifact.relative_to(self.project).as_posix())
        self.assertIn('TODO', self.cli('workflow.py', *handoff, ok=False).stderr)
        self.candidate(removal=True)
        self.implementation_done()
        self.assertEqual(json.loads(self.cli('workflow.py', *handoff).stdout)['status'], 'IMPLEMENTED_NOT_VERIFIED')
        for item in self.active.context()['tasks']:
            self.assertEqual(item['handoff'], proof.file_hash(artifact))
            self.assertEqual(item['status'], 'IMPLEMENTED')

    def test_empty_greenfield_scope_can_seal_before_first_product_file(self):
        script = self.project / 'new_app.py'
        request = 'Create a new CLI that emits a greeting.'
        child = self.private / 'hello'
        child.mkdir()
        contract = proof.load(ROOT / 'examples/cli-contract.json')
        contract.update(task_id='hello', source_paths=['new_app.py'], absent_source_paths=['new_app.py'])
        contract['checks'][0].update(command=['{python}', '-B', 'new_app.py'],
                                     assertions=[{'type': 'stdout_contains', 'value': 'Hello'}])
        proof.save(child / 'contract.json', contract)
        proof.save(child / 'context.json', {'project': str(self.project)})
        proof.save(child / 'seal.json', {'contract_hash': proof.digest(contract), 'engine_hash': proof.engine_hash(contract)})
        binding = mission.initialize(self.project, {
            'schema': 1, 'goal_id': 'hello', 'kind': 'greenfield', 'author': 'fixture-planner',
            'sources': {'new_app.py': None}, 'no_existing_behavior': 'This new CLI has no existing caller or baseline.',
            'requirements': {'R01': {'claim': 'The live command emits a greeting.', 'excerpt': request}},
            'tasks': [{'id': 'hello', 'requirement_id': 'R01', 'owner': 'component', 'depends_on': [],
                       'description': 'Create the entrypoint.', 'done': 'The sealed command emits Hello.',
                       'checks': ['hello/addition']}],
            'features': [],
        }, request, 'fixture original request')
        managed = mission.open_mission(self.project, 'hello', binding)
        self.assertTrue(managed.admit('component'))
        self.assertFalse(script.exists())
        script.write_text("print('Hello')\n", encoding='utf-8')
        self.assertTrue(managed.guard_candidate())

    def test_unmarked_legacy_root_and_team_do_not_need_new_state(self):
        self.prepare(register=False)
        goal = self.root(managed=False)
        self.cli('root_gate.py', 'seal', '--goal', goal)
        legacy = copy.deepcopy(self.plan)
        legacy.pop('mission_protocol')
        self.assertEqual(len(team.init(self.project, legacy)['ready']), 1)
        self.candidate()
        state = team.load_state(self.project, 'mission')
        team.handoff(self.project, state, legacy['tasks'][0])
        team.integrate(self.project, state)
        self.assertEqual(self.run_checks('trim', 'option', 'invalid'), {'trim': True, 'option': True, 'invalid': True})
        proof.update_step(self.child, 'T01', 'VERIFIED', 'This legacy proof step uses the current actual CLI results.')
        self.assertFalse(mission.enrolled(self.project, 'mission'))
        self.assertTrue(root_gate.check_root(goal)['root_goal_achieved'])

    def test_managed_corporate_root_rejects_reopened_work_despite_passing_quality_layers(self):
        from test_corporate import CorporateTests

        class ManagedFixture(CorporateTests):
            def register_controlled_team(fixture):
                request = fixture.team_plan['request']
                context = fixture.task / 'context.json'
                proof.save(context, {**proof.load(context), 'root_goal': 'mission'})
                fixture.root['mission_protocol'] = fixture.team_plan['mission_protocol'] = mission.PROTOCOL
                mission.initialize(fixture.project, {
                    'schema': 1, 'goal_id': 'mission', 'kind': 'change', 'author': 'calculator-owner',
                    'sources': fixture.plan['baseline']['source']['files'],
                    'requirements': {'R01': {'claim': fixture.root['requirements'][0]['claim'], 'excerpt': request}},
                    'tasks': [{'id': 'operand', 'owner': 'calculator', 'requirement_id': 'R01', 'depends_on': [],
                               'description': 'Implement the optional operand and preserve two-input arithmetic.',
                               'done': 'Actual one-input and two-input arithmetic work; malformed input is rejected.',
                               'checks': ['verify/baseline', 'verify/change', 'verify/negative']}],
                    'features': [{'id': 'existing_sum', 'behavior': 'Two explicit inputs add to a numeric sum.',
                                  'path': 'src/calc.py', 'location': 'total(a, b)', 'contract': 'public',
                                  'basis': 'observed', 'related_paths': [], 'test_paths': ['checks/check.py'],
                                  'oracle_paths': ['checks/check.py'], 'effect': 'EXTEND',
                                  'reason': 'Existing callers pass an explicit operand.',
                                  'planned_effect': 'Add a default while retaining two-input behavior.',
                                  'uncertainty': None, 'tasks': ['operand'], 'checks': ['verify/baseline']}],
                }, request, 'controlled fixture request')
                fixture.managed = mission.open_mission(fixture.project, 'mission')
                super().register_controlled_team()
                fixture.managed.step('operand', 'IN_PROGRESS', 'Start the admitted calculator change.')

            def complete_controlled_team(fixture):
                fixture.managed.step('operand', 'IMPLEMENTED', 'The optional operand is present in the calculator.')
                super().complete_controlled_team()

            def review_controlled_team(fixture, evidence):
                report = fixture.managed.review_input()
                report.update(method='fresh-context-agent', reviewer='controlled-qa-fixture')
                observation = 'Actual separate executions established one-input seven, two-input twelve and rejected type.'
                for section in ('tasks', 'features'):
                    for row in report[section].values():
                        row.update(verdict='PASS', observations=observation)
                proof.save(fixture.project / evidence, report)
                return team.review(fixture.project, fixture.team_state, evidence, 'pass')

        fixture = ManagedFixture()
        try:
            fixture.setUp()
            accepted = root_gate.check_root(fixture.goal)
            self.assertTrue(accepted['root_goal_achieved'], accepted)
            self.assertTrue(accepted['production_team']['passed'])
            self.assertTrue(accepted['corporate']['passed'])
            fixture.managed.reopen('calculator', 'Retain the calculator item as pending for follow-up review.')
            pending = root_gate.check_root(fixture.goal)
            self.assertFalse(pending['root_goal_achieved'])
            self.assertTrue(pending['corporate']['passed'], pending)
            self.assertRegex(' '.join(pending['errors']), r'(?i)mission|ledger|TODO|review')
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
