"""Real subprocess evidence and adverse controls for corporate-v1.

The tiny measured resource is actual calculator calls, not a hardware benchmark.
Reviewer identities are cooperative fixture declarations, not authentication.
"""
import contextlib
import copy
from datetime import timedelta
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import corporate
import proof
import root_gate
import team
import team_v2


class CorporateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name).resolve()
        (self.project / 'src').mkdir()
        (self.project / 'checks').mkdir()
        self.source = self.project / 'src/calc.py'
        self.source.write_text('work = 0\ndef total(a, b):\n global work\n work += 1\n return a + b\n', encoding='utf-8')
        (self.project / 'checks/check.py').write_text(
            "import sys,json\nfrom pathlib import Path\n"
            "sys.path.insert(0,str(Path('src').resolve()))\nimport calc\n"
            "mode=sys.argv[1]\n"
            "if mode=='negative':\n"
            " try: calc.total('invalid', 2)\n"
            " except TypeError: print(json.dumps({'rejected':True}))\n"
            " else: print(json.dumps({'rejected':False}))\n"
            "else:\n"
            " result=calc.total(7) if mode=='change' else calc.total(7,5)\n"
            " samples=[]\n"
            " for sample in range(3):\n"
            "  calc.work=0\n"
            "  for i in range(100): calc.total(i,2)\n"
            "  samples.append(calc.work)\n"
            " print(json.dumps({'value':result,'legacy':calc.total(7,5),'samples':samples,'unit':'calls',"
            "'profile':{'inputs':'100 integer pairs','runtime':sys.version.split()[0]}}))\n",
            encoding='utf-8')
        self.task = self.project / '.runtime-proof/verify'
        self.task.mkdir(parents=True)
        child = proof.load(ROOT / 'examples/cli-contract.json')
        child['task_id'] = 'verify'
        child['source_paths'] = ['src', 'checks']
        child['checks'] = []
        for cid, mode, role, field, value in [('baseline', 'baseline', 'regression', 'value', 12),
                                              ('change', 'change', 'acceptance', 'value', 7),
                                              ('negative', 'negative', 'negative_control', 'rejected', True)]:
            check = {'id': cid, 'description': 'Exercise calculator behavior through the real process.',
                     'mode': 'live', 'role': role,
                     'command': ['{python}', '-B', 'checks/check.py', mode], 'timeout_seconds': 10,
                     'expected_exit_codes': [0], 'assertions': [
                         {'type': 'json', 'file': 'stdout.log', 'pointer': '/' + field, 'op': 'eq', 'value': value}],
                     'artifacts': []}
            if role == 'negative_control':
                check['fault'] = 'Passing a string as an arithmetic operand must be rejected.'
            elif cid == 'baseline':
                check['assertions'].append({'type': 'json', 'file': 'stdout.log', 'pointer': '/legacy', 'op': 'eq', 'value': 12})
            child['checks'].append(check)
        child['requirements'][0]['checks'] = ['change']
        child['requirements'][0]['negative_checks'] = ['negative']
        child['plan']['tasks'][0]['checks'] = ['baseline', 'change', 'negative']
        proof.validate_contract(child)
        proof.save(self.task / 'context.json', {'project': str(self.project)})
        proof.save(self.task / 'contract.json', child)
        proof.save(self.task / 'seal.json', {'contract_hash': proof.digest(child), 'engine_hash': proof.engine_hash(child)})
        baseline = self.run_check('baseline')
        self.goal = self.project / '.runtime-proof/root-goals/mission'
        self.goal.mkdir(parents=True)
        self.plan_path = self.project / '.runtime-proof/corporate-plan.json'
        self.report_path = self.project / '.runtime-proof/corporate-report.json'
        self.context = self.project / '.runtime-proof/design.txt'
        self.context.write_text('Architecture: retain the calculator module and its public total API.\n'
                                'Contract: preserve two-operand sums and reject malformed operands.\n'
                                'Verification: execute public arithmetic, invalid input and resource checks.\n', encoding='utf-8')
        request = 'Add an optional second operand while preserving two-operand arithmetic and malformed-input rejection.'
        (self.goal / 'original-request.txt').write_text(request, encoding='utf-8')
        self.root = {'schema': 4, 'protocol': 'corporate-v1', 'goal_id': 'mission',
                     'production_team': 'mission',
                     'request_sha256': proof.file_hash(self.goal / 'original-request.txt'),
                     'scope_statement': 'Deliver optional-operand arithmetic while preserving the old public calling convention.',
                     'coverage_review': {'method': 'fresh-context-agent',
                         'rationale': 'A separate reviewer compared the entire arithmetic request to the retained acceptance.',
                         'unmapped_segments': []},
                     'request_segments': [{'start': 0, 'end': len(request), 'kind': 'requirement', 'requirement_ids': ['R01']}],
                     'requirements': [{'id': 'R01', 'claim': 'Optional operand works and existing arithmetic remains correct.',
                         'oracle': 'Run actual one-operand and old two-operand calls and reject malformed input.',
                         'source': 'user_request', 'source_excerpt': request, 'evidence_mode': 'live',
                         'satisfiers': [{'task_id': 'verify', 'requirement_id': 'R01'}]}],
                     'integration': {'task_id': 'verify', 'requirement_id': 'R01',
                         'scope': 'The finished public calculator executes feature, old API and invalid-input checks.'},
                     'corporate': {'plan': '.runtime-proof/corporate-plan.json', 'report': '.runtime-proof/corporate-report.json'}}
        coverage = {'request_sha256': self.root['request_sha256'],
                    'segments_sha256': proof.digest(self.root['request_segments']),
                    'acceptance_sha256': proof.digest({'requirements': self.root['requirements'], 'integration': self.root['integration']}),
                    'method': 'fresh-context-agent', 'reviewer': 'coverage-reviewer', 'planner': 'calculator-owner',
                    'unresolved_findings': [], 'verdict': 'covered',
                    'observations': 'Compared the complete request to feature, compatibility and malformed-input requirements.'}
        proof.save(self.goal / 'coverage-review.json', coverage)
        self.root['coverage_challenge'] = {'file': 'coverage-review.json', 'sha256': proof.file_hash(self.goal / 'coverage-review.json')}
        context = []
        for i, role in enumerate(('architecture', 'contract', 'verification'), 1):
            context.append({'id': role, 'role': role, 'citation': {
                'path': '.runtime-proof/design.txt', 'sha256': proof.file_hash(self.context),
                'start_line': i, 'end_line': i, 'excerpt': self.context.read_text().splitlines()[i - 1]}})
        self.plan = {
            'schema': 1, 'request_sha256': self.root['request_sha256'], 'author': 'calculator-owner',
            'created_at': proof.now(), 'source_paths': ['src', 'checks'], 'context': context,
            'requirements': [{'id': 'R01', 'impacts': ['src/calc.py'], 'tasks': ['calculator']}],
            'tasks': [{'id': 'calculator', 'depends_on': [], 'outputs': ['src/calc.py']}],
            'decisions': [{'id': 'optional_operand', 'requirement_ids': ['R01'],
                           'choice': 'Keep the existing function and default its second operand to zero.',
                           'rationale': 'The established two-operand API and numeric sums remain unchanged.',
                           'evidence': ['architecture', 'contract']}],
            'edge_cases': [{'id': 'malformed_operand', 'requirement_ids': ['R01'],
                            'question': 'What should happen for a string in an arithmetic operand?',
                            'resolution': 'Preserve the existing rejection rather than coercing strings.',
                            'source': 'repository_contract', 'evidence': ['contract']}],
            'baseline': {'source': baseline['source_before'], 'checks': [self.ref(baseline)],
                         'captured_at': baseline['ended_at'], 'known_failures': []}, 'layers': []}
        for name in corporate.LAYERS:
            self.plan['layers'].append({'id': name, 'applicable': True,
                'rationale': 'This component changes callable arithmetic behavior and its public contract.',
                'evidence': ['architecture', 'contract', 'verification'],
                'criteria': [{'id': name + '_criterion', 'requirement_ids': ['R01'],
                    'claim': 'Optional operand works while existing sums and invalid input remain correct.',
                    'oracle': 'Seven alone yields seven; a string plus an integer is rejected.',
                    'counterexample': 'An implementation requiring two operands would fail the one-argument check.',
                    'check': {'task_id': 'verify', 'check_id': 'change'},
                    'negative_check': {'task_id': 'verify', 'check_id': 'negative'}}], 'metrics': []})
        self.plan['layers'][4]['metrics'] = [{'id': 'call_cost',
            'check': {'task_id': 'verify', 'check_id': 'change'},
            'baseline_check': {'task_id': 'verify', 'check_id': 'baseline'},
            'file': 'stdout.log', 'samples_pointer': '/samples', 'profile_pointer': '/profile',
            'unit_pointer': '/unit', 'unit': 'calls', 'direction': 'lower', 'minimum_samples': 3,
            'max_relative_regression': .05, 'max_relative_mad': .1, 'evidence': ['verification']}]
        self.plan['layers'][1]['criteria'][0]['baseline_check'] = {'task_id': 'verify', 'check_id': 'baseline'}
        self.plan['layers'][1]['criteria'][0]['check'] = {'task_id': 'verify', 'check_id': 'baseline'}
        self.save_plan()
        corporate.validate(self.project, self.goal, self.root)
        self.team_plan = {'schema': 2, 'id': 'mission', 'kind': 'change', 'request': request,
            'contract': 'Preserve total(a,b) sums and TypeError rejection; allow a missing second operand.',
            'outcomes': {'R01': 'Actual one-operand and two-operand calculator calls return seven and twelve.'},
            'tasks': [{'id': 'calculator', 'brief': 'Add the optional operand within the established calculator API.',
                       'outputs': ['src/calc.py'], 'depends_on': [], 'outcomes': ['R01']}],
            'integration': {'outputs': [], 'check': 'Exercise the real calculator interface, old sums and rejected malformed input.'},
            'host': {'kind': 'codex'}}
        team.init(self.project, self.team_plan)
        self.team_state = team.load_state(self.project, 'mission')
        proof.save(self.goal / 'root-contract.json', self.root)
        sealed = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'), 'seal', '--goal', str(self.goal)],
                                capture_output=True, text=True)
        self.assertEqual(sealed.returncode, 0, sealed.stderr + sealed.stdout)
        self.seal = proof.load(self.goal / 'root-seal.json')
        self.source.write_text(self.source.read_text().replace('total(a, b)', 'total(a, b=0)'), encoding='utf-8')
        self.finish()

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, cid):
        with contextlib.redirect_stdout(io.StringIO()):
            return proof.run_check(self.task, cid)

    def ref(self, receipt):
        location = self.task / 'runs' / receipt['check_id'] / receipt['run_id'] / 'receipt.json'
        return corporate.execution_reference(self.project, location.relative_to(self.project).as_posix())

    def save_plan(self):
        proof.save(self.plan_path, self.plan)

    def sign_review(self):
        review = {'method': 'fresh-context-agent', 'reviewer': 'independent-reviewer',
                  'source_digest': self.report['source']['digest'], 'plan_sha256': proof.file_hash(self.plan_path),
                  'report_sha256': proof.digest({k: v for k, v in self.report.items() if k != 'review'}),
                  'reviewed_at': proof.now(), 'layers': []}
        for section in ('decisions', 'edge_cases'):
            review[section] = [{'id': row['id'], 'verdict': 'PASS',
                               'observations': 'Compared the archived contract excerpt with actual invocation results.'}
                              for row in self.plan[section]]
        for row in self.plan['layers']:
            review['layers'].append({'id': row['id'],
                'verdict': 'PASS' if row['applicable'] else 'NOT_APPLICABLE',
                'observations': 'Opened the retained command output and compared its observations with the criterion.',
                'criteria': [{'id': item['id'], 'verdict': 'PASS',
                              'observations': 'Actual one-operand call returned seven; malformed argument was rejected.'}
                             for item in row['criteria']]})
        self.report['review'] = review
        proof.save(self.report_path, self.report)

    def finish(self):
        positive, negative, preserved = self.run_check('change'), self.run_check('negative'), self.run_check('baseline')
        self.report = {'schema': 1, 'plan_sha256': proof.file_hash(self.plan_path),
                       'source': corporate.source_snapshot(self.project, self.plan['source_paths']),
                       'executions': [self.ref(positive), self.ref(negative), self.ref(preserved)]}
        if all(row['passed'] for row in (positive, negative, preserved)):
            proof.update_step(self.task, 'T01', 'VERIFIED', 'Verified the actual new and preserved arithmetic with rejected malformed input.')
        self.sign_review()
        if not hasattr(self, 'native_team_initialized'):
            self.complete_controlled_team()

    def complete_controlled_team(self):
        """Synthetic native records test the adapter; actual product checks run.

        This fixture establishes protocol wiring only. It is explicitly not
        evidence that a live host, model or independent agent produced code.
        """
        owner = team.handoff(self.project, self.team_state, self.team_plan['tasks'][0])
        integrated, _ = team.integrate(self.project, self.team_state)
        command = [sys.executable, '-B', '-c',
                   "import sys;sys.path.insert(0,'src');from calc import total;"
                   "assert total(7)==7;assert total(7,5)==12"]
        checked = team.runtime_check(self.project, self.team_state, command)
        self.assertEqual(checked['exit_code'], 0)
        evidence = '.runtime-proof/teams/mission/controlled-review.txt'
        proof.save(self.project / evidence, {
            'classification': 'controlled native-format fixture; not live-host evidence',
            'observation': 'Actual subprocess imported the calculator and asserted new and preserved sums.'})
        reviewed = team.review(self.project, self.team_state, evidence, 'pass')
        parent = str(uuid4())
        sessions = self.project / 'controlled-native-sessions'
        logs = sessions / '2026/01/01'
        logs.mkdir(parents=True)
        epoch = team.instant(self.team_state['created'])
        gap = timedelta(microseconds=100)
        def native(role, start, end, writes, receipts):
            uid = parent if role == 'integration' else str(uuid4())
            origin = 'exec' if role == 'integration' else {'subagent': {'thread_spawn': {
                'parent_thread_id': parent, 'agent_path': '/root/' + role, 'depth': 1}}}
            def event(kind, when, payload):
                return {'type': kind, 'timestamp': when.isoformat(), 'payload': payload}
            rows = [event('session_meta', start, {'id': uid, 'source': origin, 'cwd': str(self.project),
                     'timestamp': start.isoformat()}),
                    event('turn_context', start, {'model': 'controlled-fixture', 'effort': 'low'}),
                    event('event_msg', start, {'type': 'task_started'})]
            for relative, when in writes:
                rows.append(event('event_msg', when, {'type': 'patch_apply_end', 'success': True,
                            'changes': {str(self.project / relative): {}}}))
            for index, receipt in enumerate(receipts):
                when = team.instant(receipt['at']) + gap
                rows.extend([event('response_item', when, {'type': 'custom_tool_call', 'name': 'exec',
                     'call_id': str(index), 'input': 'text(await tools.exec_command({"cmd":"python scripts/team.py handoff"}));'}),
                     event('response_item', when + gap, {'type': 'custom_tool_call_output', 'call_id': str(index),
                     'output': [{'text': 'Output:\n' + team.RECEIPT + receipt['sha256']}]})])
            if end is not None:
                rows.append(event('event_msg', end, {'type': 'task_complete'}))
            (logs / ('rollout-controlled-' + uid + '-' + role + '.jsonl')).write_text(
                ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        owner_at, integration_at = team.instant(owner['at']), team.instant(integrated['at'])
        native('calculator', epoch + gap, owner_at + gap * 3,
               [('src/calc.py', epoch + gap * 2)], [owner])
        native('integration', epoch - gap, None, [], [integrated])
        native('qa', integration_at + gap * 3, team.instant(reviewed['at']) + gap * 3, [], [checked, reviewed])
        proof.save(self.project / '.runtime-proof/teams/mission/host.json',
                   {'parent': parent, 'sessions': str(sessions)})
        result = team.verify_registered(self.project, 'mission')
        self.assertTrue(result['passed'], result)
        self.native_team_initialized = True

    def result(self):
        return corporate.check(self.project, self.goal, self.root)

    def test_actual_runtime_and_all_quality_rows_pass(self):
        result = self.result()
        self.assertTrue(result['passed'], result)
        self.assertEqual({row['status'] for row in result['layers'].values()}, {'PASS'})
        metric = result['layers']['performance']['metrics'][0]
        self.assertEqual(metric['candidate']['median'], 100)

    def test_preserves_real_baseline_and_independent_review(self):
        self.assertNotEqual(self.plan['baseline']['source']['files']['src/calc.py'], proof.file_hash(self.source))
        self.assertEqual(self.plan['baseline']['source']['digest'], self.seal['corporate']['baseline_digest'])
        self.report['review']['reviewer'] = self.plan['author']
        proof.save(self.report_path, self.report)
        self.assertFalse(self.result()['passed'])

    def test_missing_report_does_not_prevent_sealing_but_prevents_acceptance(self):
        self.report_path.unlink()
        corporate.validate(self.project, self.goal, self.root)
        self.assertEqual(self.result()['status'], 'UNVERIFIED')

    def test_untracked_input_and_configuration_changes_invalidate_evidence(self):
        (self.project / 'src/new_config.json').write_text('{"mode":"changed"}')
        self.assertIn('stale', self.result()['errors'][0])

    def test_declared_output_outside_source_scope_is_rejected_in_all_file_states(self):
        self.plan['tasks'][0]['outputs'].append('config/policy.json')
        self.save_plan()
        policy = self.project / 'config/policy.json'
        for state in ('absent', 'added', 'deleted'):
            with self.subTest(state=state):
                if state == 'added':
                    policy.parent.mkdir()
                    policy.write_text('{"authorization":"disabled"}')
                elif state == 'deleted':
                    policy.unlink()
                with self.assertRaisesRegex(ValueError, 'Declared implementation output lies outside'):
                    corporate.validate(self.project, self.goal, self.root)
                self.assertFalse(self.result()['passed'])

    def test_output_scope_cannot_be_broader_than_a_verification_root(self):
        self.plan['source_paths'] = ['src/calc.py', 'checks']
        self.plan['tasks'][0]['outputs'] = ['src']
        self.save_plan()
        with self.assertRaisesRegex(ValueError, 'Declared implementation output lies outside'):
            corporate.validate(self.project, self.goal, self.root)

    def test_impact_scope_cannot_be_broader_than_a_verification_root(self):
        self.plan['source_paths'] = ['src/calc.py', 'checks']
        self.plan['requirements'][0]['impacts'] = ['src']
        self.save_plan()
        with self.assertRaisesRegex(ValueError, 'Impacted source lies outside'):
            corporate.validate(self.project, self.goal, self.root)

    def test_declared_added_and_deleted_files_under_verified_root_invalidate_review(self):
        # The declaration is contained even while the new file is absent.
        self.plan['tasks'][0]['outputs'].append('src/policy.json')
        self.save_plan()
        corporate.validate(self.project, self.goal, self.root)
        self.seal['corporate'] = corporate.seal_binding(self.project, self.goal, self.root)
        proof.save(self.goal / 'root-seal.json', self.seal)
        self.finish()
        self.assertTrue(self.result()['passed'], self.result())
        policy = self.project / 'src/policy.json'
        policy.write_text('{"authorization":"required"}')
        self.assertFalse(self.result()['passed'])
        self.finish()
        self.assertTrue(self.result()['passed'], self.result())
        policy.unlink()
        self.assertFalse(self.result()['passed'])

    def test_deleted_source_invalidates_and_snapshot_records_absence(self):
        self.source.unlink()
        self.assertFalse(self.result()['passed'])
        snapshot = corporate.source_snapshot(self.project, ['src/calc.py', 'checks'])
        self.assertIsNone(snapshot['files']['src/calc.py'])

    def test_later_failed_attempt_prevents_reuse_of_previous_success(self):
        self.source.write_text(self.source.read_text().replace('return a + b', 'return 999'))
        self.run_check('change')
        self.source.write_text(self.source.read_text().replace('return 999', 'return a + b'))
        self.assertIn('superseded', self.result()['errors'][0])

    def test_failed_behavior_is_fail_not_pass(self):
        self.source.write_text(self.source.read_text().replace('return a + b', 'return 999'))
        self.finish()
        self.assertEqual(self.result()['status'], 'FAIL')

    def test_security_claim_cannot_hide_actual_function_failure(self):
        self.source.write_text(self.source.read_text().replace('return a + b', "return 7 if isinstance(a,str) else a+b"))
        self.finish()
        result = self.result()
        self.assertEqual(result['layers']['security']['status'], 'FAIL')

    def test_actual_resource_regression_cannot_be_waived_by_review(self):
        self.source.write_text(self.source.read_text().replace('work += 1', 'work += 2'))
        self.finish()
        result = self.result()
        self.assertEqual(result['layers']['performance']['status'], 'FAIL', result)
        self.assertEqual(result['layers']['performance']['metrics'][0]['candidate']['median'], 200)

    def test_changed_plan_and_thresholds_cannot_reseal_themselves(self):
        self.plan['layers'][4]['metrics'][0]['max_relative_regression'] = .9
        self.save_plan()
        self.assertIn('changed after root sealing', self.result()['errors'][0])

    def test_changed_architecture_citation_is_not_silent(self):
        self.context.write_text('Replaced architecture and verification requirements.')
        self.assertIn('Citation changed', self.result()['errors'][0])

    def test_forged_boolean_or_edited_output_rejected(self):
        ref = self.report['executions'][0]
        location = self.project / ref['receipt']
        (location.parent / 'stdout.log').write_text('{"value":7}')
        self.assertIn('artifacts', self.result()['errors'][0])

    def test_review_must_bind_actual_report_and_current_source(self):
        self.report['review']['report_sha256'] = '0' * 64
        proof.save(self.report_path, self.report)
        self.assertIn('different source', self.result()['errors'][0])

    def test_review_can_reject_semantically_weak_test_despite_passing_process(self):
        self.report['review']['layers'][3]['criteria'][0]['verdict'] = 'FAIL'
        self.report['review']['layers'][3]['criteria'][0]['observations'] = 'The arithmetic check does not establish authorization or tenant isolation.'
        proof.save(self.report_path, self.report)
        self.assertEqual(self.result()['layers']['security']['status'], 'FAIL')

    def test_unresolved_material_edge_case_cannot_be_accepted(self):
        self.plan['edge_cases'][0]['source'] = 'assumed'
        self.save_plan()
        self.assertIn('Resolve material unknowns', self.result()['errors'][0])

    def test_missing_layer_and_missing_counterexample_rejected(self):
        original = copy.deepcopy(self.plan)
        self.plan['layers'].pop()
        self.save_plan()
        self.assertIn('all six', self.result()['errors'][0])
        self.plan = original
        del self.plan['layers'][0]['criteria'][0]['negative_check']
        self.save_plan()
        self.assertFalse(self.result()['passed'])

    def test_optional_layer_needs_explicit_independent_not_applicable_review(self):
        # A newly sealed declaration is needed; mutating applicability is never a repair.
        (self.goal / 'root-seal.json').unlink()
        self.source.write_text(self.source.read_text().replace('b=0', 'b'))
        self.plan['layers'][5].update(applicable=False, criteria=[], metrics=[],
                                     rationale='No persistent data, cancellation or concurrent state is present in this calculator.')
        self.save_plan()
        corporate.validate(self.project, self.goal, self.root)
        self.seal['corporate'] = corporate.seal_binding(self.project, self.goal, self.root)
        self.seal['sealed_at'] = proof.now()
        proof.save(self.goal / 'root-seal.json', self.seal)
        self.source.write_text(self.source.read_text().replace('total(a, b)', 'total(a, b=0)'))
        self.finish()
        self.assertTrue(self.result()['passed'], self.result())
        self.assertEqual(self.result()['layers']['resilience']['status'], 'NOT_APPLICABLE')
        self.report['review']['layers'][5]['verdict'] = 'PASS'
        proof.save(self.report_path, self.report)
        self.assertFalse(self.result()['passed'])

    def test_core_preservation_layer_cannot_be_marked_not_applicable(self):
        self.plan['layers'][1].update(applicable=False, criteria=[])
        self.save_plan()
        self.assertIn('cannot be waived', self.result()['errors'][0])

    def test_unsupported_performance_sampling_unit_or_profile_is_unverified(self):
        # Direct metric boundary tests use retained execution outputs, not source edits.
        ref = self.report['executions'][0]
        current = corporate.execution(self.project, ref, self.report['source'], latest=True)
        before = corporate._baseline(self.project, self.plan)[('verify', 'baseline')]
        metric = copy.deepcopy(self.plan['layers'][4]['metrics'][0])
        metric['unit'] = 'ms'
        with self.assertRaisesRegex(ValueError, 'unit mismatch'):
            corporate._metric(metric, before, current)
        metric['unit'] = 'calls'
        metric['minimum_samples'] = 10
        with self.assertRaisesRegex(ValueError, 'repeated finite'):
            corporate._metric(metric, before, current)

    def test_baseline_cannot_be_captured_after_changes(self):
        (self.goal / 'root-seal.json').unlink()
        with self.assertRaisesRegex(ValueError, 'pre-change source'):
            corporate.validate(self.project, self.goal, self.root)

    def test_changing_oracle_and_child_seal_does_not_redefine_root_acceptance(self):
        child = proof.load(self.task / 'contract.json')
        child['checks'][1]['assertions'][0]['value'] = 999
        proof.save(self.task / 'contract.json', child)
        proof.save(self.task / 'seal.json', {'contract_hash': proof.digest(child), 'engine_hash': proof.engine_hash(child)})
        self.assertFalse(self.result()['passed'])

    def test_criterion_must_link_a_known_original_requirement(self):
        self.plan['layers'][0]['criteria'][0]['requirement_ids'] = ['invented']
        self.save_plan()
        self.assertIn('Criterion original requirements', self.result()['errors'][0])

    def test_old_api_break_is_rejected_when_new_optional_operand_still_works(self):
        self.source.write_text(self.source.read_text().replace('return a + b', 'return a'))
        self.finish()
        feature = proof.load(self.project / self.report['executions'][0]['receipt'])
        self.assertTrue(feature['passed'], 'The new feature alone still works in this counterexample')
        result = self.result()
        self.assertEqual(result['layers']['preservation']['status'], 'FAIL', result)

    def test_unverified_review_is_not_an_observed_product_failure(self):
        self.report['review']['layers'][3]['verdict'] = 'UNVERIFIED'
        proof.save(self.report_path, self.report)
        self.assertEqual(self.result()['status'], 'UNVERIFIED')

    def test_new_feature_check_cannot_replace_preservation_replay(self):
        self.plan['layers'][1]['criteria'][0]['check']['check_id'] = 'change'
        self.save_plan()
        # Deliberately construct a fresh seal to test semantics, not just stale-plan detection.
        self.seal['corporate'] = corporate.seal_binding(self.project, self.goal, self.root)
        proof.save(self.goal / 'root-seal.json', self.seal)
        self.finish()
        self.assertIn('replay the baseline', self.result()['errors'][0])

    def test_preservation_replays_same_oracle_across_normal_check_roles(self):
        before = corporate._baseline(self.project, self.plan)[('verify', 'baseline')]
        contract = proof.load(self.task / 'contract.json')
        replay = copy.deepcopy(before['check'])
        replay.update(id='legacy-replay', role='acceptance')
        contract['checks'].append(replay)
        contract['plan']['tasks'][0]['checks'].append(replay['id'])
        replay_task = self.project / '.runtime-proof/replay'
        replay_task.mkdir()
        contract['task_id'] = replay_task.name
        proof.validate_contract(contract)
        proof.save(replay_task / 'context.json', {'project': str(self.project)})
        proof.save(replay_task / 'contract.json', contract)
        proof.save(replay_task / 'seal.json', {'contract_hash': proof.digest(contract),
                                             'engine_hash': proof.engine_hash(contract)})
        self.plan['layers'][1]['criteria'][0]['check'] = {'task_id': 'replay', 'check_id': replay['id']}
        self.save_plan()
        self.seal['corporate'] = corporate.seal_binding(self.project, self.goal, self.root)
        proof.save(self.goal / 'root-seal.json', self.seal)
        with contextlib.redirect_stdout(io.StringIO()):
            receipt = proof.run_check(replay_task, replay['id'])
        old_ref = next(ref for ref in self.report['executions'] if '/baseline/' in ref['receipt'])
        self.report['executions'].remove(old_ref)
        path = replay_task / 'runs' / replay['id'] / receipt['run_id'] / 'receipt.json'
        self.report['executions'].append(corporate.execution_reference(self.project, path.relative_to(self.project).as_posix()))
        self.report['plan_sha256'] = proof.file_hash(self.plan_path)
        self.sign_review()
        self.assertTrue(self.result()['passed'], self.result())

    def test_schema4_root_cli_integrates_corporate_and_refuses_failed_layer(self):
        args = [sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'), 'verify', '--goal', str(self.goal)]
        result = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)['corporate']['passed'])
        self.report['review']['layers'][3]['verdict'] = 'FAIL'
        proof.save(self.report_path, self.report)
        rejected = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        self.assertFalse(json.loads(rejected.stdout)['root_goal_achieved'])

    def test_schema4_root_flags_unowned_source_even_after_current_checks_pass(self):
        unowned = self.project / 'src/new_policy.json'
        unowned.write_text('{"verify": false}', encoding='utf-8')
        self.finish()
        self.assertTrue(self.result()['passed'], self.result())
        args = [sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'), 'verify', '--goal', str(self.goal)]
        rejected = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        evidence = json.loads(rejected.stdout)
        self.assertTrue(evidence['corporate']['passed'])
        self.assertIn('Production team: Corporate source changed outside sealed Team ownership: src/new_policy.json',
                      evidence['errors'])

    def test_schema4_root_rejects_later_expansion_of_integration_ownership(self):
        extra = 'src/new_policy.json'
        team_plan = copy.deepcopy(self.team_plan)
        team_plan['integration']['outputs'].append(extra)
        state_path = team.team_path(self.project, 'mission')
        state_path.unlink()
        team.init(self.project, team_plan)
        (self.project / extra).write_text('{"enabled": true}', encoding='utf-8')
        self.finish()
        args = [sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'), 'verify', '--goal', str(self.goal)]
        rejected = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        evidence = json.loads(rejected.stdout)
        self.assertTrue(evidence['corporate']['passed'])
        self.assertIn('Production team: Corporate Team state differs from the root seal', evidence['errors'])

    def test_schema4_root_cannot_seal_mismatched_team_and_corporate_baselines(self):
        state_path = team.team_path(self.project, 'mission')
        state_path.unlink()
        team.init(self.project, self.team_plan)  # Captures the already changed implementation.
        content = self.source.read_text(encoding='utf-8')
        self.source.write_text(content.replace('total(a, b=0)', 'total(a, b)'), encoding='utf-8')
        (self.goal / 'root-seal.json').unlink()
        args = [sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'), 'seal', '--goal', str(self.goal)]
        rejected = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
        self.assertIn('Team output baseline differs from the Corporate baseline', rejected.stderr)
        self.assertFalse((self.goal / 'root-seal.json').exists())

    def copied_verifier(self):
        """Execute a real separate helper package without altering tracked code."""
        package = self.project / 'verifier-copy'
        scripts = package / 'scripts'
        scripts.mkdir(parents=True)
        for name in self.seal['corporate']['engine']['files']:
            shutil.copy2(ROOT / 'scripts' / name, scripts / name)
        shutil.copy2(ROOT / 'VERSION', package / 'VERSION')
        return scripts

    def test_changed_coverage_checker_invalidates_sealed_root_without_product_change(self):
        scripts = self.copied_verifier()
        args = [sys.executable, '-B', str(scripts / 'root_gate.py'), 'verify', '--goal', str(self.goal)]
        before = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(before.returncode, 0, before.stdout + before.stderr)
        product = corporate.source_snapshot(self.project, self.plan['source_paths'])
        checker = scripts / 'coverage.py'
        with checker.open('a', encoding='utf-8') as output:
            output.write('\ndef validate(*args, **kwargs):\n    return {"mode": "coverage-bypassed"}\n')
        rejected = subprocess.run(args, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
        outcome = json.loads(rejected.stdout)
        self.assertFalse(outcome['corporate']['passed'])
        self.assertTrue(any('verifier changed' in item for item in outcome['corporate']['errors']), outcome)
        self.assertEqual(product, corporate.source_snapshot(self.project, self.plan['source_paths']))

    def test_legacy_roots_do_not_retroactively_require_corporate_engine_binding(self):
        import root_gate
        for schema in (2, 3):
            with self.subTest(schema=schema):
                legacy = copy.deepcopy(self.root)
                legacy['schema'] = schema
                del legacy['protocol']
                del legacy['corporate']
                del legacy['production_team']
                proof.save(self.goal / 'root-contract.json', legacy)
                proof.save(self.goal / 'root-seal.json', {
                    'root_hash': proof.digest(legacy), 'request_sha256': legacy['request_sha256'],
                    'sealed_at': proof.now()})
                self.finish()
                result = root_gate.check_root(self.goal)
                self.assertTrue(result['root_goal_achieved'], result)
                self.assertNotIn('corporate', result)

    def test_schema4_without_bound_team_cannot_claim_root_completion(self):
        unbound = copy.deepcopy(self.root)
        del unbound['production_team']
        proof.save(self.goal / 'root-contract.json', unbound)
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'),
                                 'verify', '--goal', str(self.goal)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertFalse(outcome['root_goal_achieved'])
        self.assertIn('bound schema-2 production team', outcome['errors'][0])

    def test_schema4_missing_native_qa_never_accepts_only_structural_team_receipts(self):
        logs = list((self.project / 'controlled-native-sessions').rglob('*-qa.jsonl'))
        self.assertEqual(len(logs), 1)
        logs[0].unlink()
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'),
                                 'verify', '--goal', str(self.goal)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertTrue(outcome['corporate']['passed'], outcome)
        self.assertFalse(outcome['root_goal_achieved'])
        self.assertTrue(any('QA' in error for error in outcome['errors']), outcome)

    def test_reviewed_root_cannot_fall_back_to_a_legacy_team_plan(self):
        import root_gate

        contract = {**self.root, 'team_decomposition': 'reviewed-v1'}
        proof.save(self.goal / 'root-contract.json', contract)
        proof.save(self.goal / 'root-seal.json', {**self.seal, 'root_hash': proof.digest(contract)})
        outcome = root_gate.check_root(self.goal)
        self.assertFalse(outcome['root_goal_achieved'], outcome)
        self.assertTrue(any('reviewed-v1 decomposition' in error for error in outcome['errors']), outcome)

    def test_reviewed_root_binding_requires_and_retains_the_pre_edit_review(self):
        import root_gate
        import team_v2

        plan = copy.deepcopy(self.team_plan)
        plan.update(id='reviewed', decomposition='reviewed-v1',
                    scope_rationale='The calculator API and its optional operand share one function and one write scope.')
        plan['tasks'][0].update(responsibility='Implement the optional second operand in the calculator.',
                                interface='total(a, b) keeps existing calls and accepts an omitted operand.',
                                check='Invoke the calculator alone with one operand and expect seven.',
                                scope_evidence=['src/calc.py'])
        registration = team.init(self.project, plan)
        contract = {**self.root, 'production_team': 'reviewed', 'team_decomposition': 'reviewed-v1'}
        self.assertFalse(registration['ready'])
        with self.assertRaisesRegex(ValueError, 'plan review is required before dispatch'):
            root_gate.reviewed_team_binding(self.project, contract)
        state = team.load_state(self.project, 'reviewed')
        evidence = '.runtime-proof/teams/reviewed/plan-review.txt'
        (self.project / evidence).write_text('The shared total() implementation and its checked public inputs justify one owner.',
                                             encoding='utf-8')
        review = team_v2.review_plan(self.project, state, evidence, 'pass')
        self.assertEqual(root_gate.reviewed_team_binding(self.project, contract),
                         {'state_sha256': state['state_sha256'], 'review_sha256': review['sha256']})
        with self.assertRaisesRegex(proof.ProofError, 'differs from the Corporate root seal'):
            root_gate.check_production_team(self.project, contract, {'reviewed_team': {'state_sha256': state['state_sha256']}})

    def test_legacy_root_may_not_claim_reviewed_team_decomposition(self):
        import root_gate

        contract = {**self.root, 'schema': 3, 'team_decomposition': 'reviewed-v1'}
        del contract['protocol']
        del contract['corporate']
        with self.assertRaisesRegex(proof.ProofError, 'requires reviewed-v1 on a schema-4 root'):
            root_gate.validate(self.project, self.goal, contract)

    def test_explicit_file_rename_and_delete_proof_runs_preserve_absence_evidence(self):
        # Separate real subprocess proofs exercise the complete execution boundary
        # with explicit missing file roots on both sides of a rename and deletion.
        sources = ['src/calc.py', 'src/old_api.py', 'src/new_api.py', 'src/obsolete.py', 'checks']
        (self.project / 'src/old_api.py').write_text('legacy_value = 7\n')
        (self.project / 'src/obsolete.py').write_text('obsolete_value = 5\n')
        task = self.project / '.runtime-proof/file-change'
        task.mkdir()
        contract = proof.load(self.task / 'contract.json')
        contract['task_id'] = 'file-change'
        contract['source_paths'] = sources
        contract['absent_source_paths'] = ['src/old_api.py', 'src/new_api.py', 'src/obsolete.py']
        proof.save(task / 'context.json', {'project': str(self.project)})
        proof.save(task / 'contract.json', contract)
        proof.save(task / 'seal.json', {'contract_hash': proof.digest(contract), 'engine_hash': proof.engine_hash(contract)})
        def exercise():
            with contextlib.redirect_stdout(io.StringIO()):
                receipt = proof.run_check(task, 'baseline')
            self.assertTrue(receipt['passed'], receipt)
            location = task / 'runs/baseline' / receipt['run_id'] / 'receipt.json'
            reference = corporate.execution_reference(self.project, location.relative_to(self.project).as_posix())
            expected = corporate.source_snapshot(self.project, sources)
            self.assertEqual(receipt['source_before'], expected)
            actual = corporate.execution(self.project, reference, expected, latest=True)
            self.assertTrue(actual['passed'], actual)
            return reference, expected
        before_ref, before = exercise()
        self.assertIsNone(before['files']['src/new_api.py'])
        (self.project / 'src/old_api.py').rename(self.project / 'src/new_api.py')
        (self.project / 'src/obsolete.py').unlink()
        after_ref, after = exercise()
        self.assertIsNone(after['files']['src/old_api.py'])
        self.assertIsNone(after['files']['src/obsolete.py'])
        self.assertIsNotNone(after['files']['src/new_api.py'])
        with self.assertRaisesRegex(ValueError, 'source scope'):
            corporate.execution(self.project, before_ref, after)
        (self.project / 'src/obsolete.py').write_text('unexpected resurrection = 1\n')
        with self.assertRaisesRegex(ValueError, 'source scope'):
            corporate.execution(self.project, after_ref, corporate.source_snapshot(self.project, sources))

    def reviewed_draft(self):
        """Real baseline subprocess plus a distinct, unimplemented Team plan."""
        self.source.write_text(self.source.read_text().replace('total(a, b=0)', 'total(a, b)'), encoding='utf-8')
        baseline = self.run_check('baseline')
        goal = self.project / '.runtime-proof/root-goals/reviewed-change'
        goal.mkdir()
        shutil.copyfile(self.goal / 'original-request.txt', goal / 'original-request.txt')
        reviewed = copy.deepcopy(self.team_plan)
        reviewed.update(id=goal.name, decomposition='reviewed-v1', root_protocol='corporate-v1',
                        scope_rationale='One owner is necessary because the callable signature and default share a file.')
        reviewed['tasks'][0].update(responsibility='Preserve the existing calculator and add its default operand.',
            interface='The public total function accepts one or two operands and returns their integer sum.',
            check='Execute the actual calculator for both old and new call signatures.',
            scope_evidence=['src/calc.py'], dependency_rationale={})
        team.init(self.project, reviewed)
        state = team.load_state(self.project, goal.name)
        return goal, state, baseline

    def fill_reviewed_draft(self, goal, state):
        root_path = goal / 'root-contract.json'
        root = proof.load(root_path)
        for key in ('scope_statement', 'request_segments', 'requirements', 'integration'):
            root[key] = self.root[key]
        proof.save(root_path, root)
        plan_path = goal / 'corporate-plan.json'
        plan = proof.load(plan_path)
        for key in ('context', 'requirements', 'decisions', 'edge_cases', 'layers'):
            plan[key] = self.plan[key]
        proof.save(plan_path, plan)
        review = {**corporate.coverage_input(goal), 'method': 'fresh-context-agent',
                  'planner': plan['author'], 'reviewer': 'controlled-coverage-reviewer',
                  'unresolved_findings': [], 'verdict': 'covered',
                  'observations': 'Controlled review inspected the complete request and preserved arithmetic contract.'}
        proof.save(goal / 'coverage-review.json', review)
        bound = corporate.bind_coverage(goal)
        self.assertFalse(bound['root_sealed'])
        evidence = f'.runtime-proof/teams/{goal.name}/controlled-plan-review.txt'
        (self.project / evidence).write_text(
            'Controlled fixture reviewed the actual calculator file, its preserved signature and sole file ownership.',
            encoding='utf-8')
        team_v2.review_plan(self.project, state, evidence, 'pass')

    def test_scaffold_uses_real_baseline_and_requires_semantic_and_team_review_before_dispatch(self):
        goal, state, baseline = self.reviewed_draft()
        cmd = [sys.executable, '-B', str(ROOT / 'scripts/corporate.py'), 'scaffold',
               '--goal', str(goal), '--proof-task', 'verify', '--baseline-check', 'baseline',
               '--author', 'calculator-owner']
        report = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(report.returncode, 0, report.stderr + report.stdout)
        self.assertEqual(json.loads(report.stdout)['status'], 'DRAFT_UNVERIFIED')
        draft = proof.load(goal / 'corporate-plan.json')
        self.assertEqual(draft['baseline']['checks'], [self.ref(baseline)])
        self.assertEqual(draft['baseline']['source'], baseline['source_before'])
        self.assertEqual(draft['tasks'], [{'id': 'calculator', 'outputs': ['src/calc.py'], 'depends_on': []}])
        self.assertEqual({row['id'] for row in draft['layers']}, set(corporate.LAYERS))
        self.assertIsNone(draft['layers'][3]['applicable'])
        self.assertFalse((goal / 'root-seal.json').exists())
        self.assertFalse((goal / 'coverage-review.json').exists())
        with self.assertRaisesRegex(proof.ProofError, 'needs a sealed schema-4 root'):
            root_gate.require_corporate_dispatch(self.project, state, baseline_current=True)
        seal = [sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'), 'seal', '--goal', str(goal)]
        rejected = subprocess.run(seal, capture_output=True, text=True)
        self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
        repeated = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(repeated.returncode, 2, repeated.stdout + repeated.stderr)
        self.assertEqual(proof.load(goal / 'corporate-plan.json'), draft)
        self.fill_reviewed_draft(goal, state)
        accepted = subprocess.run(seal, capture_output=True, text=True)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        bound = root_gate.require_corporate_dispatch(self.project, state, baseline_current=True)
        self.assertEqual(bound['team_state_sha256'], state['state_sha256'])
        self.assertEqual(bound['sealed_at'], proof.load(goal / 'root-seal.json')['sealed_at'])
        # A later owner can use the frozen plan after another owner changed files.
        self.source.write_text(self.source.read_text().replace('total(a, b)', 'total(a, b=0)'), encoding='utf-8')
        self.assertEqual(root_gate.require_corporate_dispatch(self.project, state, baseline_current=False), bound)
        with self.assertRaisesRegex(proof.ProofError, 'Source changed before Corporate dispatch'):
            root_gate.require_corporate_dispatch(self.project, state, baseline_current=True)

    def test_report_scaffold_uses_exact_latest_candidate_executions_without_claiming_review(self):
        original = self.report_path.read_bytes()
        self.report_path.unlink()
        command = [sys.executable, '-B', str(ROOT / 'scripts/corporate.py'), 'report-scaffold',
                   '--goal', str(self.goal)]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        draft = proof.load(self.report_path)
        summary = json.loads(result.stdout)
        self.assertEqual(summary['status'], 'DRAFT_UNVERIFIED')
        self.assertNotIn('review', draft)
        expected = {key: value for key, value in json.loads(original).items() if key != 'review'}
        self.assertCountEqual(draft['executions'], expected['executions'])
        self.assertEqual(draft, {**expected, 'executions': draft['executions']})
        self.assertEqual(summary['review_binding']['report_sha256'], proof.digest(draft))
        self.assertEqual({row['status'] for row in summary['observed']}, {'PASS'})
        # A subsequent review and previous evidence survive retries. A
        # source change invalidates the current receipts and creates no report.
        self.report_path.write_bytes(original)
        repeat = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(repeat.returncode, 2, repeat.stdout + repeat.stderr)
        self.assertEqual(self.report_path.read_bytes(), original)
        self.report_path.unlink()
        with self.source.open('a', encoding='utf-8') as source:
            source.write('\nnew_source = True\n')
        stale = corporate.report_scaffold(self.goal)
        self.assertEqual(stale['status'], 'UNVERIFIED')
        self.assertEqual(len(stale['missing']), 3)
        self.assertFalse(self.report_path.exists())

    def test_report_scaffold_preserves_failed_check_execution(self):
        self.report_path.unlink()
        content = self.source.read_text(encoding='utf-8')
        self.source.write_text(content.replace('return a + b', 'return a + b + 1'), encoding='utf-8')
        for name in ('baseline', 'change', 'negative'):
            self.run_check(name)
        outcome = corporate.report_scaffold(self.goal)
        self.assertEqual(outcome['status'], 'DRAFT_UNVERIFIED')
        self.assertEqual({row['check']: row['status'] for row in outcome['observed']}, {
            'verify/baseline': 'FAIL', 'verify/change': 'FAIL', 'verify/negative': 'PASS'})
        draft = proof.load(self.report_path)
        self.assertNotIn('review', draft)
        self.assertEqual(len(draft['executions']), 3)

    def test_dispatch_refuses_changed_review_binding_and_changed_checker(self):
        goal, state, _ = self.reviewed_draft()
        corporate.scaffold(goal, 'verify', ['baseline'], 'calculator-owner')
        self.fill_reviewed_draft(goal, state)
        sealed = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'),
                                 'seal', '--goal', str(goal)], capture_output=True, text=True)
        self.assertEqual(sealed.returncode, 0, sealed.stdout + sealed.stderr)
        seal_path = goal / 'root-seal.json'
        original = proof.load(seal_path)
        tampered = copy.deepcopy(original)
        tampered['reviewed_team']['review_sha256'] = '0' * 64
        proof.save(seal_path, tampered)
        with self.assertRaisesRegex(proof.ProofError, 'review differs'):
            root_gate.require_corporate_dispatch(self.project, state, baseline_current=True)
        proof.save(seal_path, original)
        child = proof.load(self.task / 'contract.json')
        child['checks'][1]['assertions'][0]['value'] = 999
        proof.save(self.task / 'contract.json', child)
        proof.save(self.task / 'seal.json', {'contract_hash': proof.digest(child), 'engine_hash': proof.engine_hash(child)})
        with self.assertRaisesRegex(ValueError, 'Execution does not match sealed task/check'):
            root_gate.require_corporate_dispatch(self.project, state, baseline_current=True)

    def test_seal_refuses_mismatched_corporate_ownership_before_dispatch(self):
        goal, state, _ = self.reviewed_draft()
        corporate.scaffold(goal, 'verify', ['baseline'], 'calculator-owner')
        self.fill_reviewed_draft(goal, state)
        plan_path = goal / 'corporate-plan.json'
        plan = proof.load(plan_path)
        plan['tasks'][0]['outputs'].append('src/unowned.py')
        proof.save(plan_path, plan)
        sealed = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/root_gate.py'),
                                 'seal', '--goal', str(goal)], capture_output=True, text=True)
        self.assertEqual(sealed.returncode, 2, sealed.stdout + sealed.stderr)
        self.assertIn('ownership/dependencies differ', sealed.stderr)
        self.assertFalse((goal / 'root-seal.json').exists())


if __name__ == '__main__':
    unittest.main()
