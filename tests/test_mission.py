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

    def qa(self, body, verdict='pass'):
        path = self.private / 'teams/mission/independent-qa.json'
        proof.save(path, body)
        return team.review(self.project, self.state, path.relative_to(self.project).as_posix(), verdict)

    def quality_body(self):
        result = self.cli('team.py', 'review-input', '--team', 'mission')
        body = self.review()
        form = json.loads(result.stdout)
        body.update({key: form[key] for key in ('integration_sha256', 'check_sha256', 'prior_findings',
                                               'quality_layers', 'findings', 'resolutions')})
        observations = {
            'functionality': 'The CLI returned Ada for a label with ASCII surrounding spaces.',
            'preservation': 'The CLI uppercases the alternate mode and rejects a missing label.',
            'architecture': 'Normalization stays in the existing parser before selecting a renderer.',
            'security': 'No trust boundary, new parser, permission, or I/O was added.',
            'performance': 'A bounded string transformation is not on a latency-sensitive path in this fixture.',
            'resilience': 'This CLI is stateless and does not change the lifecycle of any resource.',
        }
        for name, row in body['quality_layers'].items():
            checks = {'functionality': ['runtime/trim'], 'preservation': ['runtime/option', 'runtime/invalid'],
                      'architecture': ['runtime/trim']}.get(name, [])
            row.update(verdict='PASS' if checks else 'NOT_APPLICABLE', observations=observations[name],
                       paths=['app.py'], checks=checks)
        return body

    def report_finding(self, name, layer, verdict, observation, *, owner=None):
        body = self.quality_body()
        body['quality_layers'][layer].update(verdict=verdict, observations=observation, checks=[])
        body['findings'][name] = {'layers': [layer], 'owner': owner, 'observations': observation}
        return self.qa(body, 'fail')

    def quality_candidate(self, *, adjacent_regression=False, directory_scope=False):
        self.prepare(directory_scope=directory_scope)
        self.plan['integration']['quality_review'] = 'review-loop-v1'
        self.register_team()
        self.candidate(adjacent_regression=adjacent_regression)
        self.implementation_done()
        self.integrate_team()

    def check_cli_journey(self):
        command = (
            'import json, subprocess, sys\n'
            'def run(*args):\n'
            '    return subprocess.run([sys.executable, "-B", "app.py", *args], capture_output=True)\n'
            'assert json.loads(run("  Ada  ").stdout) == {"label": "Ada"}\n'
            'assert json.loads(run("Ada", "--upper").stdout) == {"label": "ADA"}\n'
            'assert run().returncode == 2\n'
        )
        return team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c', command])

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

    def test_managed_qa_requires_detail_evidence_as_well_as_ledger_review(self):
        self.prepare()
        self.plan['integration']['detail_review'] = {
            'display-label': 'Observe the exact displayed label after trimming spaces.',
        }
        self.register_team()
        self.implementation_done()
        self.candidate()
        self.integrate_team()
        self.assertTrue(all(self.run_checks('option', 'trim', 'invalid').values()))
        command = (
            'import json, os, subprocess, sys\nfrom pathlib import Path\n'
            'result = subprocess.check_output([sys.executable, "-B", "app.py", " Ada "])\n'
            'assert json.loads(result)["label"] == "Ada"\n'
            '(Path(os.environ["PROVE_IT_OUTPUT_DIR"]) / "label.json").write_bytes(result)\n'
        )
        check = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c', command])
        body = self.review()
        body.update(check_sha256=check['sha256'], observations='The live label and old CLI modes were checked.',
                    details={})
        with self.assertRaisesRegex(ValueError, 'missing display-label'):
            self.qa(body)
        with self.assertRaisesRegex(ValueError, 'No current independently accepted'):
            self.active.verify()
        body['details']['display-label'] = {
            'verdict': 'pass', 'observation': 'The current CLI displayed Ada without surrounding spaces.',
            'artifacts': ['label.json'],
        }
        qa = self.qa(body)
        team_v2.verify_structural(self.project, self.state, True)
        self.assertTrue(self.active.verify(evidence_ref=qa['sha256'])['passed'])

    def test_review_loop_requires_each_layer_and_real_current_evidence(self):
        self.quality_candidate()
        self.assertTrue(all(self.run_checks('option', 'trim', 'invalid').values()))
        body = self.quality_body()
        performance = body['quality_layers'].pop('performance')
        with self.assertRaisesRegex(GATE_ERROR, 'six quality layers'):
            self.qa(body)
        body['quality_layers']['performance'] = {**performance, 'verdict': 'PASS'}
        with self.assertRaisesRegex(GATE_ERROR, 'performance: PASS needs'):
            self.qa(body)
        body['quality_layers']['performance']['checks'] = ['guessed/timing']
        with self.assertRaisesRegex(GATE_ERROR, 'performance: cite actual'):
            self.qa(body)
        body['quality_layers']['performance'] = {**performance, 'paths': ['unsealed/notes.md']}
        with self.assertRaisesRegex(GATE_ERROR, 'performance: cite source'):
            self.qa(body)
        body['quality_layers']['performance'] = performance
        architecture = body['quality_layers']['architecture']
        architecture['verdict'] = 'NOT_APPLICABLE'
        with self.assertRaisesRegex(GATE_ERROR, 'architecture: core quality layer'):
            self.qa(body)
        architecture['verdict'] = 'PASS'
        self.qa(body)
        team_v2.verify_structural(self.project, self.state, True)

    def test_review_loop_rejects_stale_and_source_mutating_checks(self):
        self.quality_candidate(directory_scope=True)
        config = self.project / 'inputs/config.txt'
        config.write_text('updated routing\n', encoding='utf-8')
        current = config.read_bytes()
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        body = self.quality_body()
        self.assertIsNone(body['check_sha256'], 'A changed unowned mission input invalidates the old QA check')
        with self.assertRaisesRegex(GATE_ERROR, 'successful current integrated check'):
            self.qa(body)
        mutator = ('from pathlib import Path; '
                   'Path("inputs", "config.txt").write_text("unexpected QA side effect")')
        with self.assertRaisesRegex(GATE_ERROR, 'QA command changed integrated source'):
            team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c', mutator])
        config.write_bytes(current)
        self.assertIsNone(team.current_receipt(self.project, self.state, 'check')['exit_code'])
        with self.assertRaisesRegex(GATE_ERROR, 'successful current integrated check'):
            self.qa(self.quality_body())
        self.assertEqual(self.check_cli_journey()['exit_code'], 0)
        self.qa(self.quality_body())
        team_v2.verify_structural(self.project, self.state, True)

    def test_review_loop_retains_findings_from_multiple_rounds_and_requires_new_recheck(self):
        self.quality_candidate()
        self.assertTrue(all(self.run_checks('option', 'trim', 'invalid').values()))
        first_observation = 'The finite QA command printed output but did not assert its exact JSON.'
        first = self.report_finding('output_oracle', 'functionality', 'UNVERIFIED', first_observation)
        second = self.report_finding('missing_boundary', 'preservation', 'UNVERIFIED',
                                     'The finite check did not observe the missing-input exit status.')
        body = self.quality_body()
        self.assertEqual(set(body['prior_findings']), {'output_oracle', 'missing_boundary'})
        body['resolutions'] = {'missing_boundary': {'check': '@integration', 'observations': 'Checked exit two.'}}
        with self.assertRaisesRegex(GATE_ERROR, 'Resolve every retained'):
            self.qa(body)
        body['resolutions']['output_oracle'] = {'check': '@integration', 'observations': 'Compared exact JSON.'}
        with self.assertRaisesRegex(GATE_ERROR, 'Rerun the integrated check'):
            self.qa(body)
        fresh = self.check_cli_journey()
        self.assertEqual(fresh['exit_code'], 0)
        body['check_sha256'] = fresh['sha256']
        qa = self.qa(body)
        team_v2.verify_structural(self.project, self.state, True)
        self.assertEqual(qa['integration'], second['integration'], 'Evidence-only findings need no product edit')
        archived = self.private / 'teams/mission/history'
        saved = archived / f'qa-{proof.digest(first)}.json'
        original = proof.load(saved)
        self.assertEqual(original['quality_findings']['output_oracle']['observations'], first_observation)

    def test_review_loop_routes_reported_code_defect_and_demands_changed_handoff(self):
        self.quality_candidate(adjacent_regression=True)
        self.assertEqual(self.run_checks('trim', 'option', 'invalid'), {'trim': True, 'option': False, 'invalid': True})
        observed = 'Ada --upper returns ada instead of the preserved uppercase ADA result.'
        failed = self.report_finding('upper_case', 'preservation', 'FAIL', observed, owner='component')
        raw = '.runtime-proof/teams/mission/independent-qa.json'
        alternate = self.private / 'teams/mission/unrelated.json'
        proof.save(alternate, {'observation': 'Unrelated observations do not route this issue.'})
        plan = 'Restore the original uppercase branch without changing normalization; replay trimmed and alternate labels.'
        with self.assertRaisesRegex(GATE_ERROR, 'retained failed QA'):
            team.repair(self.project, self.state, 'component', alternate.relative_to(self.project).as_posix(), plan)
        wrong = self.check_cli_journey()
        self.assertNotEqual(wrong['exit_code'], 0, 'The independent replay must actually detect the regression')
        started = team.repair(self.project, self.state, 'component', raw, plan)
        self.assertFalse(started['mission_complete'])
        self.active.refresh('Inspected the unchanged parser and confirmed the candidate changed the uppercase branch.')
        packet = team.ready_packets(self.project, self.state)[0]
        self.assertIn(plan, packet['message'])
        repair = team.current_receipt(self.project, self.state, 'repair-component')
        self.assertEqual(repair['qa'], failed['sha256'])
        self.assertEqual(repair['findings']['upper_case'], proof.digest(failed['quality_findings']['upper_case']))
        self.implementation_done()
        self.integrate_team()
        self.assertFalse(self.run_checks('option')['option'])
        noop = self.quality_body()
        noop['resolutions']['upper_case'] = {'check': '@integration', 'observations': 'Claimed, but not repaired.'}
        with self.assertRaisesRegex(GATE_ERROR, 'confirmed defect needs changed outputs'):
            self.qa(noop)
        self.report_finding('upper_case', 'preservation', 'FAIL', observed, owner='component')
        team.repair(self.project, self.state, 'component', raw, plan)
        self.active.refresh('Rechecked the uppercase branch and retained the same CLI regression assertion.')
        self.assertEqual(team.ready_packets(self.project, self.state)[0]['task_name'], 'component')
        self.candidate()
        self.implementation_done()
        self.integrate_team()
        self.assertTrue(all(self.run_checks('option', 'trim', 'invalid').values()))
        self.assertEqual(self.check_cli_journey()['exit_code'], 0)
        ready = self.quality_body()
        ready['resolutions']['upper_case'] = {
            'check': '@integration', 'observations': 'The fresh CLI replay observed ADA and kept the trimmed Ada result.',
        }
        qa = self.qa(ready)
        team_v2.verify_structural(self.project, self.state, True)
        self.assertTrue(self.active.verify(evidence_ref=qa['sha256'])['passed'])

    def test_review_loop_routes_glue_to_coordinator_not_an_implementation_worker(self):
        glue = self.project / 'glue.py'
        wrapper = (
            'import json, subprocess, sys\n'
            'data = json.loads(subprocess.check_output([sys.executable, "-B", "app.py", *sys.argv[1:]]))\n'
            'print(json.dumps(data))\n'
        )
        glue.write_text(wrapper, encoding='utf-8')
        self.sources.append('glue.py')
        self.prepare(register=False)
        self.draft['tasks'].append({
            'id': 'wire_label', 'owner': 'integration', 'requirement_id': 'R1', 'depends_on': ['trim'],
            'description': 'Keep the caller adapter wired to the normalized label result.',
            'done': 'The CLI adapter returns the label JSON without changing alternate casing.',
            'checks': ['runtime/trim', 'runtime/option'],
        })
        self.draft['features'][0]['related_paths'].append('glue.py')
        self.draft['features'][0]['tasks'].append('wire_label')
        self.plan['integration'].update(quality_review='review-loop-v1', outputs=['glue.py'])
        self.enroll()
        self.register_team()
        self.candidate()
        self.implementation_done()
        team.handoff(self.project, self.state, self.plan['tasks'][0])
        self.active.refresh('Read the current producer handoff and checked its label shape against the glue.')
        self.assertEqual(team_v2.integration_packet(self.project, self.state)['outputs'], ['glue.py'])
        glue.write_text(wrapper.replace('print(json.dumps(data))',
                                        'print(json.dumps({"label": data["label"].lower()}))'), encoding='utf-8')
        self.active.step('wire_label', 'IMPLEMENTED')
        team.integrate(self.project, self.state)
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))

        def check():
            command = ('import json, subprocess, sys; '
                       'output = subprocess.check_output([sys.executable, "-B", "glue.py", "Ada", "--upper"]); '
                       'assert json.loads(output) == {"label": "ADA"}')
            return team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c', command])

        self.assertNotEqual(check()['exit_code'], 0)
        observation = 'The candidate adapter lowercases the preserved uppercase response even though the producer is correct.'
        self.report_finding('glue_case', 'preservation', 'FAIL', observation, owner='integration')
        raw = '.runtime-proof/teams/mission/independent-qa.json'
        plan = 'Preserve producer casing at the adapter; replay the established uppercase CLI journey.'
        with self.assertRaisesRegex(GATE_ERROR, 'no code findings for component'):
            team.repair(self.project, self.state, 'component', raw, plan)
        self.active.refresh('Traced the incorrect conversion to the integration-owned glue, not the producer.')
        repair = team.repair(self.project, self.state, 'integration', raw, plan)
        self.assertEqual(repair['packet']['owner'], 'integration')
        self.assertIn(plan, repair['packet']['message'])
        glue.write_text(wrapper, encoding='utf-8')
        self.active.step('wire_label', 'IMPLEMENTED')
        integrated, _ = team.integrate(self.project, self.state)
        self.assertEqual(integrated['repair'], repair['repair'])
        self.assertTrue(all(self.run_checks('trim', 'option', 'invalid').values()))
        self.assertEqual(check()['exit_code'], 0)
        body = self.quality_body()
        body['resolutions']['glue_case'] = {
            'check': '@integration', 'observations': 'The adapter now returns the producer casing ADA unchanged.',
        }
        self.qa(body)
        team_v2.verify_structural(self.project, self.state, True)

    def test_quickstart_handoff_note_qa_submit_and_repair_refresh_e2e(self):
        below_threshold = self.private / 'direct-quickstart.json'
        proof.save(below_threshold, {
            'id': 'mission',
            'request': self.request,
            'threshold': {
                'task_signals': {'kind': 'data_or_script', 'estimated_write_files': 1},
            },
            'outputs': ['app.py'],
            'read_sources': ['legacy_test.py'],
            'baseline_check': {'command': ['{python}', '-B', 'legacy_test.py'], 'stdout_contains': 'ADA'},
            'acceptance_check': {'command': ['{python}', '-B', 'legacy_test.py'], 'stdout_contains': 'ADA'},
        })
        rejected_direct = self.cli('team.py', '--project', '.', 'quickstart', '--spec',
                                   '.runtime-proof/direct-quickstart.json', ok=False)
        self.assertIn('needs_subagents=false', rejected_direct.stdout)
        self.assertFalse((self.private / 'verify').exists())
        self.assertFalse((self.private / 'request-mission.txt').exists())

        invalid_split = self.private / 'invalid-split-quickstart.json'
        proof.save(invalid_split, {
            'id': 'mission',
            'request': self.request,
            'threshold': {
                'user_intent': {'requested_subagents': True},
                'task_signals': {
                    'kind': 'cross_cutting_change',
                    'estimated_write_files': 2,
                    'independent_deliverables': 2,
                    'disjoint_write_scopes': True,
                    'stable_interface': False,
                    'independent_checks': True,
                },
            },
            'tasks': [
                {'id': 'part_a', 'outputs': ['app.py']},
                {'id': 'part_b', 'outputs': ['new_test.py']},
            ],
            'read_sources': ['legacy_test.py'],
            'baseline_check': {'command': ['{python}', '-B', 'legacy_test.py'], 'stdout_contains': 'ADA'},
            'acceptance_check': {'command': ['{python}', '-B', 'legacy_test.py'], 'stdout_contains': 'ADA'},
        })
        rejected_split = self.cli('team.py', '--project', '.', 'quickstart', '--spec',
                                  '.runtime-proof/invalid-split-quickstart.json', ok=False)
        self.assertIn('stable_interface', rejected_split.stdout)
        self.assertFalse((self.private / 'verify').exists())

        bad_spec = self.private / 'bad-quickstart.json'
        proof.save(bad_spec, {
            'id': 'mission',
            'request': self.request,
            'outputs': ['app.py', 'new_test.py'],
            'read_sources': ['legacy_test.py', 'oracle.py'],
            'baseline_check': {'command': ['{python}', '-B', 'legacy_test.py'], 'stdout_contains': 'DOES_NOT_APPEAR'},
            'acceptance_check': {'command': ['{python}', '-B', 'new_test.py'], 'stdout_contains': 'ALL_OK'},
        })
        failed_boot = self.cli('team.py', '--project', '.', 'quickstart', '--spec', '.runtime-proof/bad-quickstart.json', ok=False)
        self.assertIn('Baseline check failed', failed_boot.stdout)
        self.assertFalse((self.private / 'verify').exists(), 'Failed quickstart must roll back proof dir cleanly')

        good_spec = self.private / 'quickstart.json'
        proof.save(good_spec, {
            'id': 'mission',
            'request': self.request,
            'contract': 'Preserve --upper and missing-arg exit 2 while trimming surrounding spaces.',
            'outputs': ['app.py', 'new_test.py'],
            'read_sources': ['legacy_test.py', 'oracle.py'],
            'baseline_check': {'command': ['{python}', '-B', 'oracle.py', 'option'], 'stdout_contains': 'ADA'},
            'acceptance_check': {'command': ['{python}', '-B', 'new_test.py'], 'stdout_contains': 'ALL_OK'},
            'preserved_behavior': {
                'path': 'app.py',
                'location': '--upper option',
                'behavior': 'Ada --upper outputs ADA and missing label exits 2.',
            },
        })
        boot = json.loads(self.cli('team.py', '--project', '.', 'quickstart', '--spec', '.runtime-proof/quickstart.json').stdout)
        self.assertTrue(boot['baseline_passed'])
        self.assertEqual(boot['ready'][0]['task_name'], 'impl')

        # Implement with an intentional regression (--upper broken) to test QA fail -> 1-command repair -> pass.
        self.candidate(adjacent_regression=True)
        (self.project / 'new_test.py').write_text(
            'import json, subprocess, sys\n'
            'r = subprocess.check_output([sys.executable, "-B", "app.py", "  Ada  "])\n'
            'assert json.loads(r)["label"] == "Ada"\n'
            'print("ALL_OK")\n',
            encoding='utf-8',
        )
        self.cli('team.py', '--project', '.', 'handoff', '--team', 'mission', '--task', 'impl',
                 '--note', 'Implemented whitespace trimming and added new_test.py.')
        self.cli('team.py', '--project', '.', 'integrate', '--team', 'mission')

        fail_summary = self.private / 'teams/mission/qa-summary.json'
        proof.save(fail_summary, {
            'reviewer': 'independent-qa',
            'quality_layers': {
                'functionality': {'verdict': 'PASS', 'observations': 'Trimming spaces around Ada returns Ada.'},
                'preservation': {'verdict': 'FAIL', 'observations': 'Ada --upper returned ada instead of ADA.'},
                'architecture': {'verdict': 'PASS', 'observations': 'Changes stayed within app.py and new_test.py.'},
                'security': {'verdict': 'NOT_APPLICABLE', 'observations': 'Pure in-memory string trimming CLI.'},
                'performance': {'verdict': 'NOT_APPLICABLE', 'observations': 'Single string strip has O(1) overhead.'},
                'resilience': {'verdict': 'NOT_APPLICABLE', 'observations': 'Stateless process with no file writes.'},
            },
            'findings': {
                'upper_broken': {
                    'owner': 'impl',
                    'layers': ['preservation'],
                    'observations': 'Expected ADA for --upper, observed lowercase ada.',
                }
            },
        })
        qa_fail = self.cli('team.py', '--project', '.', 'qa-submit', '--team', 'mission',
                           '--summary', '.runtime-proof/teams/mission/qa-summary.json',
                           '--verdict', 'fail', '--', sys.executable, '-B', 'legacy_test.py', ok=False)
        self.assertEqual(qa_fail.returncode, 1)
        self.assertIn('--refresh-note', qa_fail.stdout)

        repaired = json.loads(self.cli(
            'team.py', '--project', '.', 'repair', '--team', 'mission', '--task', 'impl',
            '--evidence', '.runtime-proof/teams/mission/qa-evidence.json',
            '--observation', 'Restore label.upper() on --upper and assert it in new_test.py.',
            '--refresh-note', 'Confirmed app.py replaced label.upper() with label.lower().',
        ).stdout)
        self.assertEqual(repaired['packet']['task_name'], 'impl')

        self.candidate(adjacent_regression=False)
        (self.project / 'new_test.py').write_text(
            'import json, subprocess, sys\n'
            'for args, exp in [(["  Ada  "], "Ada"), (["  Ada  ", "--upper"], "ADA")]:\n'
            '    r = subprocess.check_output([sys.executable, "-B", "app.py", *args])\n'
            '    assert json.loads(r)["label"] == exp\n'
            'print("ALL_OK")\n',
            encoding='utf-8',
        )
        self.cli('team.py', '--project', '.', 'handoff', '--team', 'mission', '--task', 'impl',
                 '--note', 'Restored uppercase branch and verified both trimmed and --upper modes.')
        self.cli('team.py', '--project', '.', 'integrate', '--team', 'mission')

        proof.save(fail_summary, {
            'reviewer': 'independent-qa',
            'quality_layers': {
                'functionality': {'verdict': 'PASS', 'observations': 'Trimming and --upper both return exact JSON.'},
                'preservation': {'verdict': 'PASS', 'observations': 'Existing --upper and missing-arg exit 2 preserved.'},
                'architecture': {'verdict': 'PASS', 'observations': 'Parser and output contract remain clean.'},
                'security': {'verdict': 'NOT_APPLICABLE', 'observations': 'Pure in-memory CLI argument formatting.'},
                'performance': {'verdict': 'NOT_APPLICABLE', 'observations': 'No measurable overhead on single argument.'},
                'resilience': {'verdict': 'NOT_APPLICABLE', 'observations': 'Stateless CLI with no I/O side effects.'},
            },
            'resolutions': {
                'upper_broken': 'Fresh integrated check verified Ada --upper outputs ADA alongside trimmed Ada.',
            },
        })
        qa_pass = self.cli('team.py', '--project', '.', 'qa-submit', '--team', 'mission',
                           '--summary', '.runtime-proof/teams/mission/qa-summary.json',
                           '--verdict', 'pass', '--', sys.executable, '-B', 'new_test.py')
        receipts = [line for line in qa_pass.stdout.splitlines() if line.startswith(team.RECEIPT)]
        self.assertEqual(len(receipts), 2, 'qa-submit must emit both check and qa receipt markers for native trace parsing')
        state = team.load_state(self.project, 'mission')
        team_v2.verify_structural(self.project, state, True)
        self.assertTrue(mission.open_mission(self.project, 'mission').verify(
            evidence_ref=team.current_receipt(self.project, state, 'qa')['sha256'])['passed'])

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
