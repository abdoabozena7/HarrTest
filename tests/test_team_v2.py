"""Existing-code Team2 behavior; native adapter fixtures are not live-model claims."""
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import corporate
import proof
import strict_io
import team
import team_v2


def reviewed_plan(plan):
    plan['decomposition'] = 'reviewed-v1'
    plan['scope_rationale'] = 'The existing calc.py module owns one public arithmetic responsibility.'
    plan['tasks'][0].update(
        responsibility='Repair arithmetic within the existing calc module.',
        interface='Keep calc.add(a, b) as the public signed-integer operation.',
        check='Import the original public calc.add and assert signed integer sums.',
        scope_evidence=['calc.py'],
    )


def corporate_seal(state, approval):
    return {'root_hash': 'a' * 64, 'seal_sha256': 'b' * 64, 'sealed_at': proof.now(),
            'team_state_sha256': state['state_sha256'], 'team_review_sha256': approval['sha256']}


class ExistingCodeTeam(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        self.write('calc.py', 'def add(a,b): return a-b\n')
        self.plan = {'schema': 2, 'id': 'fix', 'kind': 'change',
                     'request': 'Repair addition while preserving the existing public library interface.',
                     'contract': 'calc.add(a,b) accepts two integers and returns their arithmetic sum.',
                     'outcomes': {'sum': 'The public add function returns a true sum for positive and negative inputs.'},
                     'tasks': [{'id': 'arithmetic', 'brief': 'Repair the existing arithmetic implementation.',
                                'outputs': ['calc.py'], 'depends_on': [], 'outcomes': ['sum']}],
                     'integration': {'outputs': [], 'check': 'Import the real library and assert representative signed sums.'},
                     'host': {'kind': 'unverified'}}

    def write(self, path, body):
        target = self.project / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding='utf-8')

    def start(self):
        self.dispatch = team.init(self.project, self.plan)
        self.state = team.load_state(self.project, 'fix')
        return self.dispatch

    def implement(self):
        self.write('calc.py', 'def add(a,b): return a+b\n')
        return team.handoff(self.project, self.state, self.plan['tasks'][0])

    def complete(self):
        self.start()
        return self.deliver()

    def deliver(self):
        owner = self.implement()
        integrated, packet = team.integrate(self.project, self.state)
        check = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                                   'from calc import add; assert add(7,5)==12; assert add(-7,5)==-2'])
        self.assertEqual(check['exit_code'], 0)
        evidence = '.runtime-proof/teams/fix/qa.txt'
        self.write(evidence, 'Independently imported add and checked positive and signed arithmetic through the existing interface.')
        review = team.review(self.project, self.state, evidence, 'pass')
        return owner, integrated, check, review, packet

    def review_plan(self, verdict='pass'):
        evidence = '.runtime-proof/teams/fix/plan-review.txt'
        self.write(evidence, 'calc.py defines add and has one scope; the preserved public integer function is checked.')
        return team_v2.review_plan(self.project, self.state, evidence, verdict)

    def test_single_owner_real_check_without_invented_glue(self):
        owner, integrated, check, review, packet = self.complete()
        self.assertEqual(set(integrated['files']), {'calc.py'})
        self.assertEqual(integrated['inputs'], {'arithmetic': owner['sha256']})
        self.assertEqual(review['check'], check['sha256'])
        self.assertEqual(packet['task_name'], 'qa')
        self.assertNotIn('dispatch_note', packet)
        result = team.verify_registered(self.project, 'fix')
        self.assertTrue(result['structural_passed'])
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertFalse(result['passed'])
        self.assertEqual(list(self.project.glob('*.py')), [self.project / 'calc.py'])

    def test_copilot_name_alone_cannot_claim_native_identity(self):
        self.plan['host'] = {'kind': 'copilot'}
        self.complete()
        result = team.verify_registered(self.project, 'fix')
        self.assertFalse(result['passed'])
        self.assertEqual(result['host_assurance']['status'], 'UNVERIFIED')
        self.assertIn('copilot', result['errors'][0])

    def test_copilot_dispatch_guidance_preserves_reusable_owner_and_qa_ids(self):
        self.plan['host'] = {'kind': 'copilot'}
        _, _, _, _, qa_packet = self.complete()
        owner_packet = self.dispatch['ready'][0]
        for packet in (owner_packet, qa_packet):
            with self.subTest(task=packet['task_name']):
                note = packet['dispatch_note']
                self.assertIn('mode: background', note)
                self.assertIn('read_agent with wait: true', note)
                self.assertIn('write_agent to the original agent_id', note)
                self.assertNotIn('write_agent', packet['message'])

    def test_reviewed_plan_requires_source_bound_scope_and_dependencies(self):
        reviewed_plan(self.plan)
        self.plan.pop('scope_rationale')
        with self.assertRaisesRegex(proof.ProofError, 'one implementation responsibility'):
            self.start()
        reviewed_plan(self.plan)
        task = self.plan['tasks'][0]
        task['scope_evidence'] = ['elsewhere.md']
        with self.assertRaisesRegex(ValueError, 'cite distinct paths'):
            self.start()
        task['scope_evidence'] = ['planned.py']
        task['outputs'].append('planned.py')
        with self.assertRaisesRegex(ValueError, 'existing source file'):
            self.start()
        task['scope_evidence'] = ['calc.py']
        self.plan['tasks'].append(dict(task, id='consumer', outputs=['consumer.py'], depends_on=['arithmetic']))
        with self.assertRaisesRegex(ValueError, 'each declared predecessor'):
            self.start()
        self.plan['tasks'][1]['dependency_rationale'] = {
            'arithmetic': 'The consumer requires the corrected function result before its binding can be tested.'}
        self.assertEqual(self.start()['plan_review']['task_name'], 'plan_review')

    def test_reviewed_plan_uses_cli_receipt_to_unlock_owner_packets(self):
        reviewed_plan(self.plan)
        self.write('tests.py', 'from calc import add\nassert add(1, 0) == 1\n')
        self.plan['tasks'][0]['outputs'].append('tests.py')
        initial = self.start()
        self.assertEqual(initial['ready'], [])
        self.assertEqual(initial['plan_review']['task_name'], 'plan_review')
        self.assertIn(self.state['state_sha256'], initial['plan_review']['message'])
        self.assertIn('Actual owner overlap is verified after dispatch', initial['plan_review']['message'])
        self.assertIn('Serial independent work needs a documented host cap', initial['plan_review']['message'])
        self.assertEqual(team.ready_packets(self.project, self.state), [])
        evidence = '.runtime-proof/teams/fix/plan-review.txt'
        self.write(evidence, 'The source contract supports one implementation owner and a related test file.')
        result = subprocess.run([sys.executable, '-B', str(REPO / 'scripts/team.py'), '--project', str(self.project),
                                 'review-plan', '--team', 'fix', '--evidence', evidence, '--verdict', 'pass'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        approved = team_v2.current_receipt(self.project, self.state, 'plan_review')
        self.assertIn(team.RECEIPT + approved['sha256'], result.stdout)
        ready, = team.ready_packets(self.project, self.state)
        self.assertIn('Reviewed responsibility', ready['message'])
        handoff = self.implement()
        self.assertEqual(handoff['plan_review'], approved['sha256'])

    def test_corporate_root_admission_requires_original_source_once(self):
        self.plan['root_protocol'] = 'corporate-v1'
        with self.assertRaisesRegex(ValueError, 'requires reviewed-v1'):
            self.start()
        reviewed_plan(self.plan)
        self.start()
        approval = self.review_plan()
        binding = corporate_seal(self.state, approval)
        with self.assertRaisesRegex(proof.ProofError, 'sealed schema-4 root'):
            team.ready_packets(self.project, self.state)
        path = team.team_path(self.project, 'fix', 'corporate-dispatch.json', must_exist=False)
        self.assertFalse(path.exists())
        with self.assertRaisesRegex(ValueError, 'admit the sealed Corporate root'):
            team_v2.packet(self.project, self.state, self.plan['tasks'][0])

        def dispatch(project, state, *, baseline_current):
            if baseline_current and team.snapshot(project, state['baseline']) != state['baseline']:
                raise proof.ProofError('Source changed before Corporate dispatch')
            return binding

        path_to_source = self.project / 'calc.py'
        original = path_to_source.read_bytes()
        with patch('root_gate.require_corporate_dispatch', side_effect=dispatch) as root:
            self.write('calc.py', 'def add(a,b): return a+b\n')
            with self.assertRaisesRegex(proof.ProofError, 'Source changed before Corporate dispatch'):
                team.ready_packets(self.project, self.state)
            self.assertFalse(path.exists())
            path_to_source.write_bytes(original)
            ready, = team.ready_packets(self.project, self.state)
            self.assertIn(binding['seal_sha256'], ready['message'])
            retained = proof.load(path)
            self.write('calc.py', 'def add(a,b): return a+b\n')
            self.assertEqual(len(team.ready_packets(self.project, self.state)), 1)
            receipt = team.handoff(self.project, self.state, self.plan['tasks'][0])
            self.assertEqual(receipt['root_seal_sha256'], binding['seal_sha256'])
            integrated, _ = team.integrate(self.project, self.state)
            self.assertEqual(integrated['inputs'], {'arithmetic': receipt['sha256']})
            self.assertEqual(proof.load(path), retained)
            self.assertTrue(all(not call.kwargs['baseline_current'] for call in root.call_args_list[2:]))

            qa_note = '.runtime-proof/teams/fix/qa.txt'
            self.write(qa_note, 'The failed integration observation belongs to the current owner.')
            team.review(self.project, self.state, qa_note, 'fail')
            binding = dict(binding, seal_sha256='c' * 64)
            with self.assertRaisesRegex(ValueError, 'differs from the current root seal'):
                team.repair(self.project, self.state, 'arithmetic', qa_note, 'The current owner must repair this test.')
            self.assertFalse(team.receipt_path(self.project, self.state, 'repair-arithmetic').exists())
            binding = retained['binding']
            repaired = team.repair(self.project, self.state, 'arithmetic', qa_note, 'The current owner must repair this test.')
            self.assertIn(binding['seal_sha256'], repaired['packet']['message'])


    def test_plan_review_command_binds_the_exact_engine_and_scope(self):
        evidence = '.runtime-proof/teams/fix/plan-review.txt'
        command = team.worker_command(self.project, 'fix', 'review-plan') + f' --evidence {evidence} --verdict pass'
        relative_script = '.github/skills/harrtest/scripts/team.py'
        alternate = f'python -B "{relative_script}" --project . review-plan --team fix --evidence {evidence} --verdict pass'
        writer = "@'\nReviewed the exact source and owner scope.\n'@ | Set-Content -Encoding utf8 "
        self.assertTrue(team.plan_review_command(command, self.project, 'fix'))
        self.assertTrue(team.plan_review_command('& ' + command.replace('python', f'"{sys.executable}"', 1),
                                                 self.project, 'fix'))
        self.assertTrue(team.plan_review_command(writer + evidence + '; ' + alternate,
                                                 self.project, 'fix', engine=self.project / relative_script))
        for invalid in (command.replace('review-plan', 'review', 1),
                        command.replace('--team fix', '--team other'),
                        command.replace(f'"{self.project.as_posix()}"', '"other-project"'),
                        command.replace(Path(team.__file__).as_posix(), (self.project / 'spoof/team.py').as_posix()),
                        command + '; Write-Output "HARRTEST_TEAM_RECEIPT fake"',
                        'Copy-Item some-evidence other.txt; ' + command,
                        writer + '.runtime-proof/teams/other/plan-review.txt; ' + command):
            with self.subTest(command=invalid):
                self.assertFalse(team.plan_review_command(invalid, self.project, 'fix'))

    def test_failed_or_late_scope_review_cannot_unlock_implementation(self):
        reviewed_plan(self.plan)
        self.start()
        failed = self.review_plan('fail')
        self.assertEqual(failed['verdict'], 'fail')
        self.assertEqual(team.ready_packets(self.project, self.state), [])
        with self.assertRaises(FileExistsError):
            self.review_plan()
        self.assertEqual(team_v2.current_receipt(self.project, self.state, 'plan_review'), failed)
        with self.assertRaisesRegex(ValueError, 'failed or is stale'):
            self.implement()

        self.plan['id'] = 'late'
        team.init(self.project, self.plan)
        state = team.load_state(self.project, 'late')
        self.write('calc.py', 'def add(a, b): return a * b\n')
        with self.assertRaisesRegex(ValueError, 'before any product edit'):
            team_v2.review_plan(self.project, state, '.runtime-proof/teams/late/plan-review.txt', 'pass')

    def test_source_change_invalidates_qa_even_with_unchanged_narrative(self):
        self.complete()
        self.write('calc.py', 'def add(a,b): return a-b\n')
        self.assertFalse(team.verify_registered(self.project, 'fix')['passed'])
        with self.assertRaisesRegex(ValueError, 'current files'):
            team_v2.verify_structural(self.project, self.state, True)

    def test_checker_cannot_change_delivered_code(self):
        self.start()
        self.implement()
        team.integrate(self.project, self.state)
        with self.assertRaisesRegex(ValueError, 'changed integrated source'):
            team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                               'from pathlib import Path; Path("calc.py").write_text("changed")'])
        logs = list((self.project / '.runtime-proof/teams/fix').glob('check-*.json'))
        self.assertEqual(len(logs), 1)
        self.assertFalse(proof.load(logs[0])['source_unchanged'])

    def test_timeout_and_spawn_failure_cannot_qualify_as_success(self):
        self.plan['integration']['timeout_seconds'] = 1
        self.start()
        self.implement()
        team.integrate(self.project, self.state)
        result = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                                    'import time; print("started",flush=True); time.sleep(10)'])
        self.assertIsNone(result['exit_code'])
        raw = proof.load(self.project / next(iter(result['files'])))
        self.assertTrue(raw['timed_out'])
        self.assertIn('started', raw['stdout'])
        failed = team.runtime_check(self.project, self.state, ['nonexistent-harrtest-command-84562'])
        self.assertIsNone(failed['exit_code'])
        self.assertTrue(proof.load(self.project / next(iter(failed['files'])))['spawn_error'])

    def test_overflow_retains_bounded_output_and_never_passes(self):
        self.start()
        self.implement()
        team.integrate(self.project, self.state)
        with patch.object(proof, 'MAX_LOG_BYTES', 1024):
            result = team.runtime_check(self.project, self.state,
                                        [sys.executable, '-B', '-c', 'print("x"*2048)'])
        self.assertIsNone(result['exit_code'])
        raw = proof.load(self.project / next(iter(result['files'])))
        self.assertTrue(raw['overflow'])
        self.assertEqual(len(raw['stdout']), 1024)

    def test_modified_baseline_cannot_redefine_the_original_change(self):
        self.start()
        path = self.project / '.runtime-proof/teams/fix/state.json'
        tampered = proof.load(path)
        tampered['baseline']['calc.py'] = '0' * 64
        proof.save(path, tampered)
        with self.assertRaisesRegex(ValueError, 'baseline/state changed'):
            team.load_state(self.project, 'fix')

    def test_failed_real_process_cannot_receive_passing_review(self):
        self.start()
        self.implement()
        team.integrate(self.project, self.state)
        checked = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                                     'from calc import add; assert add(3,4)==999'])
        self.assertNotEqual(checked['exit_code'], 0)
        evidence = '.runtime-proof/teams/fix/qa.txt'
        self.write(evidence, 'The signed arithmetic oracle assertion failed in the real process.')
        with self.assertRaisesRegex(ValueError, 'successful current subprocess'):
            team.review(self.project, self.state, evidence, 'pass')
        team.review(self.project, self.state, evidence, 'fail')

    def test_failed_check_returns_to_owner_and_requires_fresh_integration_and_qa(self):
        self.start()
        self.write('calc.py', 'def add(a,b): return abs(a)+abs(b)\n')
        team.handoff(self.project, self.state, self.plan['tasks'][0])
        team.integrate(self.project, self.state)
        command = [sys.executable, '-B', '-c', 'from calc import add; assert add(-7,5)==-2']
        failed = team.runtime_check(self.project, self.state, command)
        self.assertNotEqual(failed['exit_code'], 0)
        evidence = '.runtime-proof/teams/fix/qa.txt'
        self.write(evidence, 'Actual add(-7,5) returned12, violating the independent signed-sum oracle of minus two.')
        team.review(self.project, self.state, evidence, 'fail')
        repair = team.repair(self.project, self.state, 'arithmetic', evidence,
                             'Negative operands lost their signs; inspect add(-7,5) and preserve signed sums.')
        self.assertEqual(repair['owner'], 'arithmetic')
        with self.assertRaisesRegex(ValueError, 'owner repair'):
            team.integrate(self.project, self.state)
        current = self.implement()
        self.assertEqual(current['repair'], repair['repair'])
        team.integrate(self.project, self.state)
        with self.assertRaises(ValueError):
            team_v2.verify_structural(self.project, self.state, True)
        checked = team.runtime_check(self.project, self.state, command)
        self.assertEqual(checked['exit_code'], 0)
        self.write(evidence, 'Repeated actual signed-sum oracle after owner repair; observed minus two and successful assertion.')
        team.review(self.project, self.state, evidence, 'pass')
        self.assertEqual(set(team_v2.verify_structural(self.project, self.state, True)), {'arithmetic'})

    def test_qa_narrative_is_preserved_immutably(self):
        _, _, _, review, _ = self.complete()
        retained = next(iter(review['files']))
        before = (self.project / retained).read_bytes()
        self.write('.runtime-proof/teams/fix/qa.txt', 'Another review may not overwrite the original immutable observed evidence.')
        self.assertEqual((self.project / retained).read_bytes(), before)
        self.assertEqual(team.current_receipt(self.project, self.state, 'qa')['sha256'], review['sha256'])

    def test_declared_rename_and_delete_keep_absence_in_current_manifest(self):
        self.write('old.py', 'legacy_value=7\n')
        self.write('obsolete.py', 'obsolete_value=5\n')
        row = self.plan['tasks'][0]
        row['outputs'] += ['old.py', 'new.py', 'obsolete.py']
        row['renames'] = [{'from': 'old.py', 'to': 'new.py'}]
        row['deletions'] = ['obsolete.py']
        self.start()
        (self.project / 'old.py').rename(self.project / 'new.py')
        (self.project / 'obsolete.py').unlink()
        owner = self.implement()
        self.assertIsNone(owner['files']['old.py'])
        self.assertIsNone(owner['files']['obsolete.py'])
        integrated, _ = team.integrate(self.project, self.state)
        self.assertIsNone(integrated['files']['old.py'])
        self.write('old.py', 'unexpected resurrection\n')
        with self.assertRaises(ValueError):
            team.current_receipt(self.project, self.state, 'integration')

    def test_undeclared_deletion_and_noop_handoff_are_rejected(self):
        self.start()
        with self.assertRaisesRegex(ValueError, 'actual change'):
            team.handoff(self.project, self.state, self.plan['tasks'][0])
        (self.project / 'calc.py').unlink()
        with self.assertRaisesRegex(ValueError, 'declared deletions'):
            team.handoff(self.project, self.state, self.plan['tasks'][0])

    def test_rename_cannot_overwrite_an_existing_unowned_destination(self):
        self.write('occupied.py', 'value=10\n')
        row = self.plan['tasks'][0]
        row['outputs'].append('occupied.py')
        row['renames'] = [{'from': 'calc.py', 'to': 'occupied.py'}]
        with self.assertRaisesRegex(ValueError, 'destination must be absent'):
            self.start()

    def sequential(self):
        self.write('consumer.py', 'from calc import add\nresult=add(1,2)\n')
        self.plan['tasks'].append({'id': 'consumer', 'brief': 'Update the existing consumer after arithmetic handoff.',
                                   'outputs': ['consumer.py'], 'depends_on': ['arithmetic'], 'outcomes': ['sum']})
        result = self.start()
        self.assertEqual([x['task_name'] for x in result['ready']], ['arithmetic'])
        self.implement()
        self.assertEqual([x['task_name'] for x in team.ready_packets(self.project, self.state)], ['consumer'])
        self.write('consumer.py', 'from calc import add\nresult=add(2,3)\n')
        return team.handoff(self.project, self.state, self.plan['tasks'][1])

    def test_sequential_dependencies_are_valid_and_refresh_when_input_changes(self):
        self.sequential()
        self.assertEqual(team.ready_packets(self.project, self.state), [])
        self.write('calc.py', 'def add(a,b): return int(a)+int(b)\n')
        self.implement()  # Restores same source and idempotent receipt.
        self.write('calc.py', 'def add(a,b): return int(a)+int(b)\n')
        team.handoff(self.project, self.state, self.plan['tasks'][0])
        with self.assertRaisesRegex(ValueError, 'stale prerequisite'):
            team.integrate(self.project, self.state)

    def test_owner_overlap_and_cycles_rejected(self):
        self.plan['tasks'].append(dict(self.plan['tasks'][0], id='other'))
        with self.assertRaisesRegex(ValueError, 'exactly one owner'):
            self.start()
        self.plan['tasks'][1]['outputs'] = ['other.py']
        self.plan['tasks'][0]['depends_on'] = ['other']
        self.plan['tasks'][1]['depends_on'] = ['arithmetic']
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.start()

    def test_current_validation_contract_changes_invalidate_packets(self):
        self.write('rules.txt', 'Signed arithmetic semantics must be preserved.\n')
        self.plan['validation_context'] = ['rules.txt']
        owner = self.start()['ready'][0]
        self.assertIn('Sealed read-only validation context', owner['message'])
        self.write('rules.txt', 'Different semantics cannot reuse the prior sealed attempt.\n')
        with self.assertRaisesRegex(ValueError, r'context changed: rules\.txt'):
            team.ready_packets(self.project, self.state)

    def test_init_rejects_validation_context_owned_by_worker_or_coordinator(self):
        self.write('check_existing.py', 'from calc import add\nassert add(1, 1) == 0\n')
        self.plan['validation_context'] = ['check_existing.py']
        command = [sys.executable, '-B', str(REPO / 'scripts/team.py'),
                   '--project', str(self.project), 'init', '--plan', 'plan.json']
        for scope in (self.plan['tasks'][0], self.plan['integration']):
            with self.subTest(scope=scope):
                scope['outputs'].append('check_existing.py')
                self.write('plan.json', json.dumps(self.plan))
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn('validation_context file check_existing.py overlaps owned output check_existing.py',
                              result.stdout)
                self.assertIn('separate evidence', result.stdout)
                self.assertFalse(team.team_path(self.project, 'fix', must_exist=False).exists())
                scope['outputs'].pop()

    def test_editable_checker_and_sealed_context_complete_finite_schema_two_check(self):
        checker = 'check_existing.py'
        retained = '.runtime-proof/baseline-check_existing.py'
        original = 'from calc import add\nassert add(1, 0) == 1\n'
        self.write(checker, original)
        self.write(retained, original)
        self.plan['validation_context'] = [retained]
        self.plan['tasks'][0]['outputs'].append(checker)
        ready = self.start()['ready'][0]
        self.write(checker, original + 'assert add(1, 1) == 2\n')
        self.implement()
        _, qa = team.integrate(self.project, self.state)
        result = team.runtime_check(self.project, self.state, [sys.executable, '-B', checker])
        self.assertEqual(result['exit_code'], 0)
        capture = proof.load(self.project / next(iter(result['files'])))
        self.assertTrue(capture['source_unchanged'])
        for packet in (ready, qa):
            self.assertIn(retained, packet['message'])
            self.assertNotIn('Coordinate exclusive runtime ownership', packet['message'])
        self.assertIn('Sealed implementation and integration paths: calc.py, check_existing.py.', qa['message'])
        self.assertEqual(self.state['baseline'][checker], self.state['validation_inputs'][retained])
        self.assertNotEqual(self.state['baseline'][checker], proof.file_hash(self.project / checker))

    def test_preexisting_schema_two_state_does_not_apply_the_new_init_guard(self):
        self.plan['validation_context'] = ['calc.py']
        original = {'calc.py': proof.file_hash(self.project / 'calc.py')}
        state = {'plan': self.plan, 'plan_sha256': team.strict_io.digest(self.plan),
                 'baseline': original, 'created': proof.now(), 'validation_inputs': original}
        state['state_sha256'] = team.strict_io.digest(state)
        path = team.team_path(self.project, 'fix', must_exist=False)
        proof.save(path, state, exclusive=True)
        self.assertEqual(team.load_state(self.project, 'fix'), state)

    def test_cli_dispatch_supports_schema_two(self):
        self.write('plan.json', json.dumps(self.plan))
        command = [sys.executable, '-B', str(REPO / 'scripts/team.py'), '--project', str(self.project)]
        result = subprocess.run([*command, 'init', '--plan', 'plan.json'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)['schema'], 2)
        self.write('calc.py', 'def add(a,b): return a+b\n')
        result = subprocess.run([*command, 'handoff', '--team', 'fix', '--task', 'arithmetic'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        result = subprocess.run([*command, 'integrate', '--team', 'fix'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('independent QA', result.stdout)

    def test_request_binding_covers_all_source_paths(self):
        self.start()
        digest = hashlib.sha256(self.plan['request'].encode()).hexdigest()
        self.assertEqual(team.binding(self.project, 'fix', digest)['integration_outputs'], ['calc.py'])
        with self.assertRaisesRegex(ValueError, 'another request'):
            team.binding(self.project, 'fix', '0' * 64)

    def root_request_fixture(self):
        reviewed_plan(self.plan)
        self.plan['root_protocol'] = 'corporate-v1'
        self.plan.pop('request')
        goal = self.project / '.runtime-proof/root-goals/fix'
        goal.mkdir(parents=True)
        original = goal / 'original-request.txt'
        original.write_bytes('Repair addition while preserving the existing signed integer interface.\r\n'
                             'Report the café example and preserve whitespace.\r\n'.encode('utf-8'))
        return original

    def cli_init(self, *, from_root, enrolled_goal=None):
        draft = self.project / '.runtime-proof/team-plan.json'
        proof.save(draft, self.plan)
        command = [sys.executable, '-B', str(REPO / 'scripts/team.py'), '--project', str(self.project),
                   'init', '--plan', draft.relative_to(self.project).as_posix()]
        if from_root:
            command.append('--request-from-root')
        environment = os.environ.copy()
        environment.pop('HARRTEST_CORPORATE_GOAL', None)
        if enrolled_goal:
            environment['HARRTEST_CORPORATE_GOAL'] = enrolled_goal
        result = subprocess.run(command, capture_output=True, encoding='utf-8', env=environment)
        return result, draft

    def test_enrolled_goal_cannot_register_a_manually_reconstructed_request(self):
        original = self.root_request_fixture()
        self.plan['request'] = original.read_text(encoding='utf-8').rstrip()
        rejected, _ = self.cli_init(from_root=False, enrolled_goal='fix')
        self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
        self.assertIn('differs from the saved original request', rejected.stdout)
        self.assertFalse(team.team_path(self.project, 'fix', must_exist=False).exists())
        del self.plan['request']
        accepted, _ = self.cli_init(from_root=False, enrolled_goal='fix')
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertEqual(team.load_state(self.project, 'fix')['plan']['request'].encode('utf-8'),
                         original.read_bytes())

    def test_root_request_option_preserves_the_exact_saved_request_and_binding(self):
        original = self.root_request_fixture()
        saved = original.read_bytes()
        run, draft = self.cli_init(from_root=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        packets = json.loads(run.stdout)
        state = team.load_state(self.project, 'fix')
        self.assertEqual(state['plan']['request'].encode('utf-8'), saved)
        self.assertEqual(original.read_bytes(), saved)
        self.assertNotIn('request', proof.load(draft))
        self.assertEqual(packets['plan_review'], team_v2.plan_review_packet(self.project, state))
        self.assertEqual(packets['ready'], [])
        self.assertEqual(team.binding(self.project, 'fix', proof.file_hash(original))['plan_sha256'],
                         state['plan_sha256'])
        with self.assertRaisesRegex(ValueError, 'another request'):
            team.binding(self.project, 'fix', hashlib.sha256(saved.rstrip()).hexdigest())

    def test_root_request_option_refuses_trim_equivalent_but_conflicting_text(self):
        original = self.root_request_fixture()
        self.plan['request'] = original.read_bytes().decode('utf-8').rstrip()
        run, draft = self.cli_init(from_root=True)
        self.assertEqual(run.returncode, 2, run.stdout + run.stderr)
        self.assertIn('differs from the saved original request', run.stdout)
        self.assertEqual(proof.load(draft), self.plan)
        self.assertFalse(team.team_path(self.project, 'fix', must_exist=False).exists())

    def test_root_request_option_requires_the_same_goal_and_an_unsealed_attempt(self):
        original = self.root_request_fixture()
        self.plan['id'] = 'other-goal'
        missing, _ = self.cli_init(from_root=True)
        self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
        self.assertFalse(team.team_path(self.project, 'other-goal', must_exist=False).exists())
        self.plan['id'] = 'fix'
        seal = original.parent / 'root-seal.json'
        proof.save(seal, {'root_hash': 'a' * 64})
        sealed, _ = self.cli_init(from_root=True)
        self.assertEqual(sealed.returncode, 2, sealed.stdout + sealed.stderr)
        self.assertIn('already sealed', sealed.stdout)
        self.assertFalse(team.team_path(self.project, 'fix', must_exist=False).exists())
        seal.unlink()
        initial, _ = self.cli_init(from_root=True)
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        state_path = team.team_path(self.project, 'fix')
        state = state_path.read_bytes()
        duplicate, _ = self.cli_init(from_root=True)
        self.assertEqual(duplicate.returncode, 2, duplicate.stdout + duplicate.stderr)
        self.assertIn('already registered', duplicate.stdout)
        self.assertEqual(state_path.read_bytes(), state)

    def test_explicit_team_request_works_without_a_root_and_option_is_corporate_only(self):
        rejected, _ = self.cli_init(from_root=True)
        self.assertEqual(rejected.returncode, 2, rejected.stdout + rejected.stderr)
        self.assertIn('requires a reviewed Corporate Team schema 2 plan', rejected.stdout)
        explicit, _ = self.cli_init(from_root=False)
        self.assertEqual(explicit.returncode, 0, explicit.stdout + explicit.stderr)
        state = team.load_state(self.project, 'fix')
        self.assertEqual(state['plan']['request'], self.plan['request'])


class CodexAdapter(unittest.TestCase):
    """Controlled durable host format tests on top of real subprocess checks."""
    def setUp(self):
        ExistingCodeTeam.setUp(self)
        self.plan['host'] = {'kind': 'codex'}
        self.parent = str(uuid4())
        self.sessions = self.project / 'sessions'
        self.logs = self.sessions / '2026/01/01'
        self.logs.mkdir(parents=True)

    write = ExistingCodeTeam.write
    start = ExistingCodeTeam.start
    implement = ExistingCodeTeam.implement
    complete = ExistingCodeTeam.complete
    deliver = ExistingCodeTeam.deliver
    review_plan = ExistingCodeTeam.review_plan

    def native(self, role, start, end, writes, receipts, uid=None, *, action='handoff'):
        uid = uid or (self.parent if role == 'integration' else str(uuid4()))
        origin = 'exec' if role == 'integration' else {'subagent': {'thread_spawn': {
            'parent_thread_id': self.parent, 'agent_path': '/root/' + role, 'depth': 1}}}
        epoch = team.instant(self.state['created'])
        def event(kind, sec, data):
            return {'type': kind, 'timestamp': (epoch + timedelta(seconds=sec)).isoformat(), 'payload': data}
        rows = [event('session_meta', start, {'id': uid, 'source': origin, 'cwd': str(self.project),
                                            'timestamp': (epoch + timedelta(seconds=start)).isoformat()}),
                event('turn_context', start, {'model': 'controlled-fixture', 'effort': 'low'}),
                event('event_msg', start, {'type': 'task_started'})]
        for path, sec in writes:
            rows.append(event('event_msg', sec, {'type': 'patch_apply_end', 'success': True,
                                                'changes': {str(self.project / path): {}}}))
        for i, (receipt, sec) in enumerate(receipts):
            command = f'python scripts/team.py {action}'
            output = 'Output:\n' + team.RECEIPT + receipt['sha256']
            if action == 'review-plan':
                command = team.worker_command(self.project, 'fix', action) + (
                    ' --evidence .runtime-proof/teams/fix/plan-review.txt --verdict pass')
                output = json.dumps({'chunk_id': 'fixture', 'wall_time_seconds': 0.01,
                                     'output': output, 'exit_code': 0})
            rows.extend([event('response_item', sec, {'type': 'custom_tool_call', 'name': 'exec',
                         'call_id': str(i), 'input': 'text(await tools.exec_command(' + json.dumps({'cmd': command}) + '));'}),
                         event('response_item', sec + .01, {'type': 'custom_tool_call_output', 'call_id': str(i),
                         'output': [{'text': output}]})])
        if end is not None:
            rows.append(event('event_msg', end, {'type': 'task_complete'}))
        path = self.logs / ('rollout-controlled-' + uid + '-' + role + '.jsonl')
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        return path

    def test_single_actual_owner_and_validation_only_integration_native_fixture(self):
        owner, integrated, check, qa, _ = self.complete()
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(owner, 4)])
        self.native('integration', -1, None, [], [(integrated, 7)])
        self.native('qa', 8, 12, [], [(check, 9), (qa, 11)])
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['host_assurance']['overlap'], [])

    def test_reviewed_decomposition_native_parallel_pair(self):
        reviewed_plan(self.plan)
        self.plan['max_parallel_workers'] = 2
        self.write('consumer.py', 'LABEL = "before"\n')
        self.plan['tasks'].append({
            'id': 'consumer', 'brief': 'Implement output labeling at the existing reader boundary.',
            'outputs': ['consumer.py'], 'depends_on': [], 'outcomes': ['sum'],
            'responsibility': 'Present the caller labels within the existing adapter.',
            'interface': 'Keep the existing public LABEL used by the adapter.',
            'check': 'Import consumer and assert the new presentation label.',
            'scope_evidence': ['consumer.py'],
        })
        self.start()
        approval = self.review_plan()
        self.assertEqual({p['task_name'] for p in team.ready_packets(self.project, self.state)}, {'arithmetic', 'consumer'})
        self.write('consumer.py', 'LABEL = "after"\n')
        second = team.handoff(self.project, self.state, self.plan['tasks'][1])
        owner, integrated, check, qa, _ = self.deliver()
        self.native('plan_review', 1, 3, [], [(approval, 2)], action='review-plan')
        self.native('arithmetic', 4, 8, [('calc.py', 5)], [(owner, 6)])
        consumer_uid = str(uuid4())
        self.native('consumer', 6, 11, [('consumer.py', 9)], [(second, 10)], uid=consumer_uid)
        self.native('integration', -1, None, [], [(integrated, 12)])
        self.native('qa', 13, 17, [], [(check, 14), (qa, 16)])
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['host_assurance']['overlap'], [['arithmetic', 'consumer']])
        self.native('consumer', 9, 11, [('consumer.py', 9.5)], [(second, 10)], uid=consumer_uid)
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertIn('parallel workers', result['errors'][0])

    def test_large_preplan_history_keeps_current_native_proof_and_legacy_limit(self):
        owner, integrated, check, qa, _ = self.complete()
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(owner, 4)])
        path = self.native('integration', -1, None, [], [(integrated, 7)])
        self.native('qa', 8, 12, [], [(check, 9), (qa, 11)])
        add_preplan_history(path, self.state['created'], 'codex')
        self.assertGreater(path.stat().st_size, team.MAX_ROLLOUT_BYTES)
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertTrue(result['passed'], result)
        meta = team.log_meta(path)
        with self.assertRaisesRegex(ValueError, 'rollout exceeds'):
            team.read_trace(self.project, meta, path, team.instant(self.state['created']))

    def test_preseal_model_context_is_retained_and_pending_calls_are_bounded(self):
        owner, integrated, check, qa, _ = self.complete()
        self.plan['model'] = 'different-model'
        # Change only the test observation pin passed to the adapter, not sealed state.
        state = dict(self.state, plan=dict(self.state['plan'], model='different-model'))
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(owner, 4)])
        path = self.native('integration', -1, None, [], [(integrated, 7)])
        self.native('qa', 8, 12, [], [(check, 9), (qa, 11)])
        with self.assertRaisesRegex(ValueError, 'model differs'):
            team_v2.codex_adapter(self.project, state, self.parent, self.sessions, True)
        events = [json.loads(line) for line in path.read_text().splitlines()]
        for i in range(3):
            events.append({'type': 'response_item', 'timestamp': (team.instant(self.state['created']) + timedelta(seconds=15 + i)).isoformat(),
                           'payload': {'type': 'function_call', 'name': 'exec_command', 'call_id': 'unclosed' + str(i),
                                       'arguments': '{}'}})
        path.write_text(''.join(json.dumps(x) + '\n' for x in events), encoding='utf-8')
        with patch.object(team_v2, 'MAX_NATIVE_PENDING_CALLS', 2):
            result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertIn('pending lifecycle', result['errors'][0])

    def test_qa_edit_is_rejected(self):
        owner, integrated, check, qa, _ = self.complete()
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(owner, 4)])
        self.native('integration', -1, None, [], [(integrated, 7)])
        self.native('qa', 8, 12, [('calc.py', 10)], [(check, 9), (qa, 11)])
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertFalse(result['passed'])
        self.assertIn('QA edited product', result['errors'][0])

    def test_reused_implementation_identity_cannot_be_independent_qa(self):
        owner, integrated, check, qa, _ = self.complete()
        worker = str(uuid4())
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(owner, 4)], uid=worker)
        self.native('integration', -1, None, [], [(integrated, 7)])
        self.native('qa', 8, 12, [], [(check, 9), (qa, 11)], uid=worker)
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertFalse(result['passed'])
        self.assertIn('QA is not independent', result['errors'][0])

    def test_sequential_graph_does_not_require_false_parallelism(self):
        self.plan['max_parallel_workers'] = 4
        self.plan['tasks'].append({'id': 'consumer', 'brief': 'Consume the corrected arithmetic result.',
                                   'outputs': ['consumer.py'], 'depends_on': ['arithmetic'], 'outcomes': ['sum']})
        self.write('consumer.py', 'from calc import add\nresult=add(1,2)\n')
        self.start()
        first = self.implement()
        self.write('consumer.py', 'from calc import add\nresult=add(2,3)\n')
        second = team.handoff(self.project, self.state, self.plan['tasks'][1])
        integrated, _ = team.integrate(self.project, self.state)
        check = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                                   'import consumer; assert consumer.result==5'])
        evidence = '.runtime-proof/teams/fix/qa.txt'
        self.write(evidence, 'Imported actual consumer and verified the composed arithmetic result is five.')
        qa = team.review(self.project, self.state, evidence, 'pass')
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(first, 4)])
        consumer_uid = str(uuid4())
        self.native('consumer', 6, 10, [('consumer.py', 7)], [(second, 9)], uid=consumer_uid)
        self.native('integration', -1, None, [], [(integrated, 12)])
        self.native('qa', 13, 17, [], [(check, 14), (qa, 16)])
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['host_assurance']['overlap'], [])
        self.native('consumer', 2, 10, [('consumer.py', 7)], [(second, 9)], uid=consumer_uid)
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertFalse(result['passed'])
        self.assertIn('before prerequisite', result['errors'][0])

    def test_available_independent_workers_need_observed_overlap(self):
        self.plan['max_parallel_workers'] = 2
        self.plan['tasks'].append({'id': 'consumer', 'brief': 'Implement the independently specified consumer.',
                                   'outputs': ['consumer.py'], 'depends_on': [], 'outcomes': ['sum']})
        self.write('consumer.py', 'def consume(): return 0\n')
        result = self.start()
        self.assertEqual({x['task_name'] for x in result['ready']}, {'arithmetic', 'consumer'})
        first = self.implement()
        self.write('consumer.py', 'def consume(): return 5\n')
        second = team.handoff(self.project, self.state, self.plan['tasks'][1])
        integrated, _ = team.integrate(self.project, self.state)
        check = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                                   'from calc import add; from consumer import consume; assert consume()==add(2,3)'])
        evidence = '.runtime-proof/teams/fix/qa.txt'
        self.write(evidence, 'Executed both actual independently assigned components and verified their composed result.')
        qa = team.review(self.project, self.state, evidence, 'pass')
        self.native('arithmetic', 1, 5, [('calc.py', 2)], [(first, 4)])
        consumer_uid = str(uuid4())
        self.native('consumer', 6, 10, [('consumer.py', 7)], [(second, 9)], uid=consumer_uid)
        self.native('integration', -1, None, [], [(integrated, 12)])
        self.native('qa', 13, 17, [], [(check, 14), (qa, 16)])
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertFalse(result['passed'])
        self.assertIn('parallel workers', result['errors'][0])
        self.native('consumer', 2, 10, [('consumer.py', 7)], [(second, 9)], uid=consumer_uid)
        result = team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['host_assurance']['overlap'], [['arithmetic', 'consumer']])


class CopilotAdapter(unittest.TestCase):
    """Portable fixtures use field shapes inspected in actual CLI1.0.104 sessions."""
    write = ExistingCodeTeam.write
    start = ExistingCodeTeam.start
    implement = ExistingCodeTeam.implement
    complete = ExistingCodeTeam.complete
    deliver = ExistingCodeTeam.deliver
    review_plan = ExistingCodeTeam.review_plan

    def setUp(self):
        ExistingCodeTeam.setUp(self)
        self.plan['host'] = {'kind': 'copilot'}
        self.plan['model'], self.plan['reasoning_effort'] = 'fixture-model', 'low'
        self.parent = str(uuid4())
        self.sessions = self.project / 'native'
        self.path = self.sessions / self.parent / 'events.jsonl'
        self.path.parent.mkdir(parents=True)

    def event(self, kind, sec, data, agent=None):
        value = {'type': kind, 'data': data, 'id': str(uuid4()),
                 'timestamp': (team.instant(self.state['created']) + timedelta(seconds=sec)).isoformat(),
                 'parentId': None}
        if agent:
            value['agentId'] = agent
        return value

    def trace(self, owner, integrated, check, qa, *, plan_review=None, review_end=5):
        rows = [self.event('session.start', -1, {
            'sessionId': self.parent, 'version': 1, 'producer': 'copilot-agent',
            'copilotVersion': '1.0.104', 'selectedModel': 'fixture-model', 'reasoningEffort': 'low',
            'startTime': (team.instant(self.state['created']) - timedelta(seconds=1)).isoformat(),
            'context': {'cwd': str(self.project)}})]
        timeline = [
                ('arithmetic', 1, 5, ['calc.py'], [(owner, 4)]),
                ('integration', -1, None, [], [(integrated, 7)]),
                ('qa', 8, 12, [], [(check, 9), (qa, 11)])]
        if plan_review:
            timeline = [('plan_review', 1, review_end, [], [(plan_review, 3)])] + [
                (role, start + 10, finish + 10 if finish else None, writes,
                 [(receipt, sec + 10) for receipt, sec in receipts])
                for role, start, finish, writes, receipts in timeline]
        for role, start, finish, writes, receipts in timeline:
            agent, dispatch = (str(uuid4()), 'dispatch-' + role) if role != 'integration' else (None, None)
            if agent:
                rows.append(self.event('tool.execution_start', start, {'toolCallId': dispatch,
                            'toolName': 'task', 'arguments': {'name': role}, 'model': 'fixture-model'}))
                rows.append(self.event('subagent.started', start + .01, {'toolCallId': dispatch,
                            'agentDisplayName': role, 'model': 'fixture-model'}, agent))
                rows.append(self.event('subagent.configured', start + .02,
                            {'model': 'fixture-model', 'reasoningEffort': 'low'}, agent))
            for rel in writes:
                call = 'edit-' + role
                rows.append(self.event('tool.execution_start', start + .2,
                            {'toolCallId': call, 'toolName': 'apply_patch', 'arguments': 'patch',
                             'model': 'fixture-model', 'parentToolCallId': dispatch}, agent))
                rows.append(self.event('tool.execution_complete', start + .3,
                            {'toolCallId': call, 'success': True, 'parentToolCallId': dispatch,
                             'fileEdits': [{'path': str(self.project / rel), 'kind': 'edit'}]}, agent))
            for receipt, sec in receipts:
                call = receipt['sha256']
                command = 'python scripts/team.py handoff'
                if role == 'plan_review':
                    command = team.worker_command(self.project, 'fix', 'review-plan') + (
                        ' --evidence .runtime-proof/teams/fix/plan-review.txt --verdict pass')
                payload = {'toolCallId': call, 'toolName': 'powershell', 'model': 'fixture-model',
                           'arguments': {'command': command}, 'parentToolCallId': dispatch}
                rows.append(self.event('tool.execution_start', sec, payload, agent))
                rows.append(self.event('tool.execution_complete', sec + .01,
                            {'toolCallId': call, 'success': True, 'parentToolCallId': dispatch,
                             'shellExecution': {'exitCode': 0},
                             'result': {'content': team.RECEIPT + receipt['sha256']}}, agent))
            if agent:
                rows.append(self.event('subagent.completed', finish, {'toolCallId': dispatch}, agent))
        rows.sort(key=lambda x: x['timestamp'])
        self.save(rows)
        return rows

    def save(self, rows):
        self.path.write_text(''.join(json.dumps(x) + '\n' for x in rows), encoding='utf-8')

    def verify(self):
        return team.verify_registered(self.project, 'fix', parent=self.parent, sessions=self.sessions)

    def coverage_events(self, sec, revision, *, edit=None, changes=None):
        goal = self.project / '.runtime-proof/root-goals/fix'
        request = self.plan['request']
        bindings = {'request_sha256': hashlib.sha256(request.encode()).hexdigest(),
                    'segments_sha256': proof.digest(['spans', revision]),
                    'acceptance_sha256': proof.digest(['acceptance', revision])}
        prompt = corporate.coverage_review_message(goal, bindings, 'Coordinator "fixture" with café identity')
        args = {'name': 'coverage_review', 'agent_type': 'general-purpose', 'mode': 'background',
                'prompt': prompt, **(changes or {})}
        dispatch, actor = str(uuid4()), str(uuid4())
        events = [self.event('tool.execution_start', sec, {'toolName': 'task', 'toolCallId': dispatch,
                  'arguments': args}), self.event('subagent.started', sec + .01,
                  {'toolCallId': dispatch, 'agentDisplayName': 'coverage_review', 'model': 'fixture-model'}, actor),
                  self.event('subagent.configured', sec + .02,
                  {'model': 'fixture-model', 'reasoningEffort': 'low'}, actor)]
        if edit:
            call = str(uuid4())
            events.extend([self.event('tool.execution_start', sec + .03,
                           {'toolCallId': call, 'toolName': 'apply_patch', 'parentToolCallId': dispatch}, actor),
                           self.event('tool.execution_complete', sec + .04, {'toolCallId': call, 'success': True,
                           'parentToolCallId': dispatch, 'fileEdits': [{'path': str(self.project / edit),
                                                                       'kind': 'edit'}]}, actor)])
        events.append(self.event('subagent.completed', sec + .05, {'toolCallId': dispatch}, actor))
        return events

    def nested_task(self, parent_start, *, label='coverage-review', edit=None, success=True):
        actor, call, edit_call = str(uuid4()), str(uuid4()), str(uuid4())
        parent = parent_start['agentId']
        parent_call = parent_start['data']['toolCallId']
        return [
            self.event('tool.execution_start', 6.025, {'toolCallId': call, 'toolName': 'task',
                       'arguments': {'name': label, 'agent_type': 'general-purpose',
                                     'description': 'Inspect inputs', 'prompt': 'Read the evidence.'},
                       'parentToolCallId': parent_call, 'turnId': '1', 'model': 'fixture-model'}, parent),
            self.event('subagent.started', 6.027, {'toolCallId': call, 'agentDisplayName': label,
                       'agentName': 'general-purpose', 'agentType': 'general-purpose',
                       'executionMode': 'sync', 'parentId': parent, 'model': 'fixture-model'}, actor),
            self.event('subagent.configured', 6.028, {'model': 'fixture-model', 'reasoningEffort': 'low'}, actor),
            self.event('tool.execution_start', 6.03, {'toolCallId': edit_call,
                       'toolName': 'apply_patch' if edit else 'view',
                       'parentToolCallId': call, 'turnId': '1', 'model': 'fixture-model'}, actor),
            self.event('tool.execution_complete', 6.035, {'toolCallId': edit_call,
                       'success': success, 'parentToolCallId': call, 'turnId': '1',
                       'fileEdits': [{'kind': 'edit', 'path': str(self.project / edit)}] if edit else []}, actor),
            self.event('subagent.completed', 6.04, {'toolCallId': call}, actor),
            self.event('tool.execution_complete', 6.045, {'toolCallId': call, 'success': True,
                       'parentToolCallId': parent_call, 'turnId': '1'}, parent),
        ]

    def test_corporate_nested_tasks_are_auxiliary_and_retain_private_writes(self):
        reviewed_plan(self.plan)
        self.plan['root_protocol'] = 'corporate-v1'
        self.start()
        approval = self.review_plan()
        begin = team.instant(self.state['created'])
        binding = {**corporate_seal(self.state, approval), 'sealed_at': (begin + timedelta(seconds=9)).isoformat()}
        with patch('root_gate.require_corporate_dispatch', return_value=binding):
            with patch.object(proof, 'now', return_value=(begin + timedelta(seconds=10)).isoformat()):
                team.ready_packets(self.project, self.state)
            owner, integrated, check, qa, _ = self.deliver()
            direct = self.trace(owner, integrated, check, qa, plan_review=approval)
            coverage = self.coverage_events(6, 1)
            for label in ('coverage-review', 'arithmetic', 'qa', 'plan_review'):
                with self.subTest(label=label):
                    private = '.runtime-proof/private-observation.txt'
                    nested = self.nested_task(coverage[1], label=label, edit=private)
                    self.save(sorted(direct + coverage + nested, key=lambda event: event['timestamp']))
                    result = self.verify()
                    self.assertTrue(result['passed'], result)
                    self.assertEqual(set(result['host_assurance']['workers']), {'arithmetic'})
                    self.assertNotEqual(result['host_assurance']['workers']['arithmetic']['id'], nested[1]['agentId'])
                    rows = team_v2.read_copilot_traces(self.project, self.parent, self.sessions, begin,
                                                       review_team='fix', corporate_request=self.plan['request'])
                    auxiliary = rows['auxiliary:' + nested[1]['agentId']]
                    self.assertEqual([path for _, path in auxiliary['writes']], [private])
                    self.assertEqual(auxiliary['markers'], {})

            with self.assertRaisesRegex(ValueError, 'unique originating named task'):
                team_v2.read_copilot_traces(self.project, self.parent, self.sessions, begin, review_team='fix')

            self.save(sorted(direct + coverage[:-1] + nested[:-1], key=lambda event: event['timestamp']))
            self.assertEqual(self.verify()['status'], 'pending-native-turn')
            self.save(sorted(direct + coverage + nested[:-1], key=lambda event: event['timestamp']))
            self.assertIn('nested task lifecycle did not complete', self.verify()['errors'][0])

    def test_corporate_nested_tasks_reject_product_writes_and_wrong_lifecycles(self):
        reviewed_plan(self.plan)
        self.plan['root_protocol'] = 'corporate-v1'
        self.start()
        created = team.instant(self.state['created'])
        header = self.event('session.start', -1, {
            'sessionId': self.parent, 'version': 1, 'producer': 'copilot-agent',
            'selectedModel': 'fixture-model', 'reasoningEffort': 'low',
            'startTime': (created - timedelta(seconds=1)).isoformat(), 'context': {'cwd': str(self.project)}})
        coverage = self.coverage_events(6, 1)
        for changed, expected in (
            ('foreign-parent', 'Invalid nested Copilot task dispatch'),
            ('foreign-call', 'unique originating named task'),
            ('wrong-enclosing-call', 'Invalid nested Copilot task dispatch'),
            ('closed-parent', 'Invalid nested Copilot task dispatch'),
            ('background', 'Invalid nested Copilot task dispatch'),
            ('parent-tool-early', 'Copilot nested task lifecycle did not complete'),
            ('parent-tool-malformed', 'Copilot nested task lifecycle did not complete'),
            ('product-write', 'unassigned agent wrote product files'),
            ('failed-tool-product-write', 'unassigned agent wrote product files'),
        ):
            with self.subTest(changed=changed):
                edit = 'calc.py' if 'product-write' in changed else None
                nested = self.nested_task(coverage[1], edit=edit, success=changed != 'failed-tool-product-write')
                events = [header, *coverage]
                if changed == 'foreign-parent':
                    nested[1]['data']['parentId'] = str(uuid4())
                elif changed == 'foreign-call':
                    nested[1]['data']['toolCallId'] = str(uuid4())
                elif changed == 'wrong-enclosing-call':
                    nested[0]['data']['parentToolCallId'] = str(uuid4())
                elif changed == 'closed-parent':
                    events[-1] = self.event('subagent.completed', 6.026, coverage[-1]['data'], coverage[-1]['agentId'])
                elif changed == 'background':
                    nested[1]['data']['executionMode'] = 'background'
                elif changed == 'parent-tool-early':
                    nested[-1]['timestamp'] = nested[4]['timestamp']
                elif changed == 'parent-tool-malformed':
                    nested[-1]['data'].pop('success')
                self.save(sorted(events + nested, key=lambda event: event['timestamp']))
                with self.assertRaisesRegex(ValueError, expected):
                    rows = team_v2.read_copilot_traces(
                        self.project, self.parent, self.sessions, created,
                        review_team='fix', corporate_request=self.plan['request'])
                    if edit:
                        team_v2.verify_native_rows(self.project, self.state, self.parent, rows,
                                                   False, 'copilot-session-events-v1')

    def test_corporate_coverage_review_revisions_keep_team_identity_and_writes(self):
        reviewed_plan(self.plan)
        self.plan['root_protocol'] = 'corporate-v1'
        self.start()
        approval = self.review_plan()
        begin = team.instant(self.state['created'])
        binding = {**corporate_seal(self.state, approval), 'sealed_at': (begin + timedelta(seconds=9)).isoformat()}
        with patch('root_gate.require_corporate_dispatch', return_value=binding):
            with patch.object(proof, 'now', return_value=(begin + timedelta(seconds=10)).isoformat()):
                team.ready_packets(self.project, self.state)
            owner, integrated, check, qa, _ = self.deliver()
            valid = self.trace(owner, integrated, check, qa, plan_review=approval)
            first, second = self.coverage_events(6, 1), self.coverage_events(7, 2)
            self.save(sorted(valid + first + second, key=lambda e: e['timestamp']))
            result = self.verify()
            self.assertTrue(result['passed'], result)
            self.assertEqual(set(result['host_assurance']['workers']), {'arithmetic'})

            reviewer_edit = self.coverage_events(7, 2, edit='calc.py')
            self.save(sorted(valid + first + reviewer_edit, key=lambda e: e['timestamp']))
            self.assertIn('unassigned agent wrote product files', self.verify()['errors'][0])

            late = self.coverage_events(9.5, 2)
            self.save(sorted(valid + first + late, key=lambda e: e['timestamp']))
            self.assertIn('coverage reviewer started after Corporate root sealing', self.verify()['errors'][0])

            prompt = second[0]['data']['arguments']['prompt']
            request_hash = hashlib.sha256(self.plan['request'].encode()).hexdigest()
            for changes in ({'prompt': prompt + '\n'}, {'prompt': prompt.replace(request_hash, 'b' * 64)},
                            {'agent_type': 'explore'}, {'mode': 'resume'}):
                with self.subTest(changes=changes.keys()):
                    first_invalid = self.coverage_events(6, 1, changes=changes)
                    second_invalid = self.coverage_events(7, 2, changes=changes)
                    self.save(sorted(valid + first_invalid + second_invalid, key=lambda e: e['timestamp']))
                    self.assertIn('unique originating named task', self.verify()['errors'][0])

    def test_new_corporate_plan_reserves_coverage_name_without_rejecting_legacy_owner(self):
        reviewed_plan(self.plan)
        self.plan['root_protocol'] = 'corporate-v1'
        self.plan['tasks'][0]['id'] = 'coverage_review'
        with self.assertRaisesRegex(ValueError, 'Reserved Corporate coverage reviewer name'):
            self.start()

        self.state = {'plan': self.plan, 'plan_sha256': strict_io.digest(self.plan),
                      'baseline': team.snapshot(self.project, ['calc.py']),
                      'validation_inputs': {}, 'created': proof.now()}
        self.state['state_sha256'] = strict_io.digest(self.state)
        proof.save(team.team_path(self.project, 'fix', must_exist=False), self.state)
        self.assertEqual(team.load_state(self.project, 'fix'), self.state)
        approval = self.review_plan()
        begin = team.instant(self.state['created'])
        binding = {**corporate_seal(self.state, approval), 'sealed_at': (begin + timedelta(seconds=9)).isoformat()}
        with patch('root_gate.require_corporate_dispatch', return_value=binding):
            with patch.object(proof, 'now', return_value=(begin + timedelta(seconds=10)).isoformat()):
                team.ready_packets(self.project, self.state)
            owner, integration, check, qa, _ = self.deliver()
            rows = self.trace(owner, integration, check, qa, plan_review=approval)
            for event in rows:
                data = event['data']
                args = data.get('arguments')
                if isinstance(args, dict) and args.get('name') == 'arithmetic':
                    args['name'] = 'coverage_review'
                if data.get('agentDisplayName') == 'arithmetic':
                    data['agentDisplayName'] = 'coverage_review'
            valid = rows + self.coverage_events(6, 1)
            self.save(sorted(valid, key=lambda e: e['timestamp']))
            result = self.verify()
            self.assertTrue(result['passed'], result)
            self.assertEqual(set(result['host_assurance']['workers']), {'coverage_review'})

            duplicate_owner = self.coverage_events(13, 2, changes={'prompt': 'Second owner with legacy label.'})
            self.save(sorted(valid + duplicate_owner, key=lambda e: e['timestamp']))
            self.assertIn('unique originating named task', self.verify()['errors'][0])

    def test_reviewed_decomposition_requires_early_native_plan_reviewer_command(self):
        reviewed_plan(self.plan)
        packet = self.start()['plan_review']
        self.assertIn('general-purpose agent', packet['dispatch_note'])
        self.assertIn('--evidence .runtime-proof/teams/fix/plan-review.txt', packet['message'])
        approval = self.review_plan()
        owner, integrated, check, qa, _ = self.deliver()
        self.trace(owner, integrated, check, qa)
        rejected = self.verify()
        self.assertIn('Missing native plan_review worker', rejected['errors'][0])

        valid = self.trace(owner, integrated, check, qa, plan_review=approval)
        result = self.verify()
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['host_assurance']['plan_review']['receipt'], approval['sha256'])
        self.assertNotEqual(result['host_assurance']['plan_review']['actor'],
                            result['host_assurance']['workers']['arithmetic']['id'])

        wrong = deepcopy(valid)
        for event in wrong:
            if (event['type'] == 'tool.execution_start'
                    and event['data'].get('toolCallId') == approval['sha256']):
                event['data']['arguments']['command'] = 'python scripts/team.py review --evidence plan-review.txt'
        self.save(wrong)
        rejected = self.verify()
        self.assertIn('missing native tool receipt', rejected['errors'][0])

        failed = deepcopy(valid)
        for event in failed:
            if (event['type'] == 'tool.execution_complete'
                    and event['data'].get('toolCallId') == approval['sha256']):
                event['data']['shellExecution']['exitCode'] = 1
        self.save(failed)
        rejected = self.verify()
        self.assertIn('missing native tool receipt', rejected['errors'][0])

        self.trace(owner, integrated, check, qa, plan_review=approval, review_end=12)
        rejected = self.verify()
        self.assertIn('owner started before plan review completed', rejected['errors'][0])

    def test_corporate_native_receipts_cannot_accept_a_pre_admission_start_or_write(self):
        reviewed_plan(self.plan)
        self.plan['root_protocol'] = 'corporate-v1'
        self.plan['integration']['outputs'] = ['glue.py']
        self.write('glue.py', '# existing integration scope\n')
        self.start()
        approval = self.review_plan()
        begin = team.instant(self.state['created'])
        binding = {**corporate_seal(self.state, approval), 'sealed_at': (begin + timedelta(seconds=9)).isoformat()}
        with patch('root_gate.require_corporate_dispatch', return_value=binding):
            with patch.object(proof, 'now', return_value=(begin + timedelta(seconds=10)).isoformat()):
                team.ready_packets(self.project, self.state)
            owner, integrated, check, qa, _ = self.deliver()
            valid = self.trace(owner, integrated, check, qa, plan_review=approval)
            result = self.verify()
            self.assertTrue(result['passed'], result)
            self.assertEqual(result['host_assurance']['corporate_dispatch']['binding'], binding)

            early = deepcopy(valid)
            for event in early:
                if (event['data'].get('toolCallId') == 'dispatch-arithmetic'
                        and event['type'] in {'tool.execution_start', 'subagent.started'}):
                    event['timestamp'] = (team.instant(event['timestamp']) - timedelta(seconds=2)).isoformat()
            self.save(sorted(early, key=lambda e: e['timestamp']))
            self.assertIn('owner started before Corporate root admission', self.verify()['errors'][0])

            early_write = [
                self.event('tool.execution_start', 8, {'toolCallId': 'glue-before-seal', 'toolName': 'apply_patch',
                                'arguments': 'patch', 'model': 'fixture-model'}),
                self.event('tool.execution_complete', 8.1, {'toolCallId': 'glue-before-seal', 'success': True,
                                'fileEdits': [{'path': str(self.project / 'glue.py'), 'kind': 'edit'}]}),
            ]
            self.save(sorted(valid + early_write, key=lambda e: e['timestamp']))
            self.assertIn('Native product write preceded Corporate root admission', self.verify()['errors'][0])

    def test_correlated_native_subagent_file_edit_and_finite_qa_receipts_pass(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        commands = {
            owner['sha256']: "& 'C:\\Python313\\python.exe' '.github\\skills\\harrtest\\scripts\\team.py' --project . handoff --team fix --task arithmetic",
            integrated['sha256']: "& 'C:\\Python313\\python.exe' '.github\\skills\\harrtest\\scripts\\team.py' --project . integrate --team fix",
            check['sha256']: "& 'C:\\Python313\\python.exe' .github\\skills\\harrtest\\scripts\\team.py --project . check --team fix -- cmd.exe /c \"python public_check.py && echo verified\"",
            qa['sha256']: "& 'C:\\Python313\\python.exe' .github\\skills\\harrtest\\scripts\\team.py --project . review --team fix --evidence .runtime-proof/teams/fix/qa.txt --verdict pass",
        }
        for r in rows:
            data = r['data']
            command = commands.get(data.get('toolCallId'))
            if r['type'] == 'tool.execution_start' and command is not None:
                if data['toolCallId'] in {check['sha256'], qa['sha256']}:
                    command = "@'\nActual observations: public fixture's expected output.\n'@ | Set-Content -Encoding utf8 .runtime-proof\\teams\\fix\\qa.txt\n" + command
                data['arguments']['command'] = command
        self.save(rows)
        result = self.verify()
        self.assertTrue(result['passed'], result)
        self.assertEqual(result['host_assurance']['adapter'], 'copilot-session-events-v1')
        self.assertEqual(result['host_assurance']['workers']['arithmetic']['model'], 'fixture-model')

    def followup_trace(self, *, coordinator_check=False):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        original = next(r for r in rows if r['type'] == 'subagent.started'
                        and r['data']['agentDisplayName'] == 'qa')
        worker, dispatch = original['agentId'], original['data']['toolCallId']
        interaction = str(uuid4())
        message = 'Check the current observed source again after the retained failed review.'
        resume_rows = {
            'write_start': self.event('tool.execution_start', 13, {
                'toolCallId': 'escalated-write', 'toolName': 'write_agent',
                'arguments': {'agent_id': worker, 'message': message}}),
            'write_done': self.event('tool.execution_complete', 13.1, {
                'toolCallId': 'escalated-write', 'success': True,
                'toolTelemetry': {'properties': {'agent_id': worker}}}),
            'message': self.event('user.message', 13.2, {
                'source': 'agent-' + self.parent, 'content': message, 'delivery': 'idle',
                'interactionId': interaction, 'turnId': '0',
                'responsesReasoning': {'model': 'fixture-model', 'effort': 'low', 'initialEffort': 'low'}}, worker),
            'turn_start': self.event('assistant.turn_start', 13.3, {
                'interactionId': interaction, 'turnId': '0', 'parentToolCallId': dispatch}, worker),
            'read_start': self.event('tool.execution_start', 13.4, {
                'toolCallId': 'wait-for-worker', 'toolName': 'read_agent',
                'arguments': {'agent_id': worker, 'wait': True}}),
            'turn_end': self.event('assistant.turn_end', 15, {
                'turnId': '0', 'parentToolCallId': dispatch}, worker),
            'next_turn_start': self.event('assistant.turn_start', 15.1, {
                'interactionId': interaction, 'turnId': '1', 'parentToolCallId': dispatch}, worker),
            'next_turn_end': self.event('assistant.turn_end', 17, {
                'turnId': '1', 'parentToolCallId': dispatch}, worker),
            'read_done': self.event('tool.execution_complete', 18, {
                'toolCallId': 'wait-for-worker', 'success': True, 'toolTelemetry': {
                    'properties': {'agent_id': worker, 'status': 'idle'},
                    'metrics': {'queue_depth': 0, 'total_turns': 2}}}),
        }
        for r in rows:
            data = r['data']
            digest = data.get('toolCallId')
            if digest not in {check['sha256'], qa['sha256']}:
                continue
            section = 0 if digest == check['sha256'] else 1
            r['timestamp'] = self.event('time', 14 + 2 * section + (0.01 if r['type'].endswith('complete') else 0), {})['timestamp']
            if coordinator_check and section == 0:
                del r['agentId']
                del data['parentToolCallId']
            else:
                data.update(turnId=str(section), interactionId=interaction)
        return rows, resume_rows

    def save_followup(self, rows, resume):
        self.save(sorted(rows + list(resume.values()), key=lambda r: r['timestamp']))

    def test_same_worker_followup_preserves_original_and_resumed_intervals(self):
        rows, resume = self.followup_trace()
        self.save_followup(rows, resume)
        result = self.verify()
        self.assertTrue(result['passed'], result)
        observed = team_v2.read_copilot_traces(self.project, self.parent, self.sessions,
                                               team.instant(self.state['created']))['qa']
        self.assertEqual(len(observed['intervals']), 2)
        self.assertLess(observed['intervals'][0][1], observed['intervals'][1][0])
        self.assertEqual(observed['intervals'][1], (team.instant(resume['turn_start']['timestamp']),
                                                    team.instant(resume['next_turn_end']['timestamp'])))

    def steering_trace(self):
        rows, resume = self.followup_trace()
        worker = resume['message']['agentId']
        message = 'Also verify the unchanged output for an empty request.'
        resume.update(
            steer_start=self.event('tool.execution_start', 14.5, {
                'toolCallId': 'steer', 'toolName': 'write_agent',
                'arguments': {'agent_id': worker, 'message': message}}),
            steer_done=self.event('tool.execution_complete', 14.6, {
                'toolCallId': 'steer', 'success': True,
                'toolTelemetry': {'properties': {'agent_id': worker}}}),
            steer_message=self.event('user.message', 15.11, {
                'source': 'agent-' + self.parent, 'content': message, 'delivery': 'steering',
                'interactionId': resume['message']['data']['interactionId'], 'turnId': '1'}, worker),
        )
        return rows, resume

    def test_steering_during_resume_stays_in_the_original_interaction(self):
        rows, resume = self.steering_trace()
        self.save_followup(rows, resume)
        result = self.verify()
        self.assertTrue(result['passed'], result)
        qa = team_v2.read_copilot_traces(self.project, self.parent, self.sessions,
                                         team.instant(self.state['created']))['qa']
        self.assertEqual(len(qa['intervals']), 2)
        self.assertIsNone(qa.get('resume'))

    def test_steering_requires_a_paired_send_and_current_delivery(self):
        rows, resume = self.steering_trace()
        for case in ('no_delivery', 'failed_send', 'different_message', 'different_interaction', 'wrong_turn', 'after_tools'):
            with self.subTest(case=case):
                altered = deepcopy(resume)
                delivery = altered['steer_message']
                if case == 'no_delivery':
                    del altered['steer_message']
                elif case == 'failed_send':
                    altered['steer_done']['data']['success'] = False
                elif case == 'different_message':
                    delivery['data']['content'] += ' Changed.'
                elif case == 'different_interaction':
                    delivery['data']['interactionId'] = 'another interaction'
                elif case == 'wrong_turn':
                    delivery['data']['turnId'] = '0'
                else:
                    delivery['timestamp'] = self.event('time', 16.5, {})['timestamp']
                self.save_followup(rows, altered)
                self.assertFalse(self.verify()['passed'])

    def test_idle_read_after_turn_closes_resume_for_next_delivery(self):
        rows, first = self.followup_trace()
        second = deepcopy(first)
        interaction = str(uuid4())
        for event in second.values():
            event['id'] = str(uuid4())
            event['timestamp'] = (team.instant(event['timestamp']) + timedelta(seconds=8)).isoformat()
            payload = event['data']
            if 'toolCallId' in payload:
                payload['toolCallId'] += '-next'
            if 'interactionId' in payload:
                payload['interactionId'] = interaction
        message = 'Follow up again after the host confirmed the worker was idle.'
        second['message']['data']['content'] = message
        second['write_start']['data']['arguments']['message'] = message
        second['read_done']['data']['toolTelemetry']['metrics']['total_turns'] = 3
        for wait in (None, False):
            with self.subTest(wait=wait):
                args = first['read_start']['data']['arguments']
                if wait is None:
                    del args['wait']
                else:
                    args['wait'] = wait
                first['read_start']['timestamp'] = self.event('time', 17.1, {})['timestamp']
                self.save_followup(rows + list(first.values()), second)
                result = self.verify()
                self.assertTrue(result['passed'], result)
                qa = team_v2.read_copilot_traces(self.project, self.parent, self.sessions,
                                                 team.instant(self.state['created']))['qa']
                self.assertEqual(len(qa['intervals']), 3)

    def test_followup_never_attributes_coordinator_check_to_qa(self):
        rows, resume = self.followup_trace(coordinator_check=True)
        self.save_followup(rows, resume)
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertIn('QA check: missing native tool receipt', result['errors'][0])

    def test_wrong_or_failed_followup_delivery_cannot_authorize_child_tools(self):
        rows, resume = self.followup_trace()
        missing = {key: event for key, event in resume.items() if key != 'message'}
        self.save_followup(rows, missing)
        self.assertIn('follow-up turn lacks its original task identity', self.verify()['errors'][0])
        for record, field, wrong in [('write_done', 'success', False), ('message', 'source', 'unknown'),
                                     ('message', 'content', 'different message'),
                                     ('turn_start', 'interactionId', 'another interaction'),
                                     ('turn_start', 'parentToolCallId', 'different dispatch')]:
            with self.subTest(record=record, field=field):
                altered = deepcopy(resume)
                altered[record]['data'][field] = wrong
                self.save_followup(rows, altered)
                self.assertFalse(self.verify()['passed'])

    def test_followup_requires_confirmed_idle_with_closed_turns(self):
        rows, resume = self.followup_trace()
        for cause in ['missing_read', 'failed_read', 'prose_only', 'busy', 'queued', 'stale_counter', 'open_turn',
                      'early_nonwaiting_read', 'abort']:
            with self.subTest(cause=cause):
                altered = deepcopy(resume)
                if cause == 'missing_read':
                    del altered['read_done']
                elif cause == 'failed_read':
                    altered['read_done']['data']['success'] = False
                elif cause == 'prose_only':
                    del altered['read_done']['data']['toolTelemetry']
                    altered['read_done']['data']['result'] = {'content': 'Agent is idle with zero queued messages.'}
                elif cause == 'busy':
                    altered['read_done']['data']['toolTelemetry']['properties']['status'] = 'running'
                elif cause == 'queued':
                    altered['read_done']['data']['toolTelemetry']['metrics']['queue_depth'] = 1
                elif cause == 'stale_counter':
                    altered['read_done']['data']['toolTelemetry']['metrics']['total_turns'] = 1
                elif cause == 'open_turn':
                    del altered['next_turn_end']
                elif cause == 'early_nonwaiting_read':
                    del altered['read_start']['data']['arguments']['wait']
                else:
                    altered['abort'] = self.event('abort', 16.5, {}, resume['message']['agentId'])
                self.save_followup(rows, altered)
                report = self.verify()
                self.assertFalse(report['passed'], report)
                if cause != 'abort':
                    self.assertEqual(report['status'], 'pending-native-turn')

    def test_followup_wrong_tool_identity_or_failed_check_cannot_pass(self):
        rows, resume = self.followup_trace()
        completion = next(r for r in rows if r['type'] == 'tool.execution_complete' and r.get('agentId')
                          == resume['message']['agentId'])
        payload = completion['data']
        good_interaction = payload['interactionId']
        payload['interactionId'] = 'old interaction'
        self.save_followup(rows, resume)
        self.assertIn('follow-up turn identity', self.verify()['errors'][0])
        payload['interactionId'] = good_interaction
        payload['shellExecution']['exitCode'] = 1
        self.save_followup(rows, resume)
        self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])

    def test_prior_qa_review_cannot_pass_while_followup_is_queued(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        worker = next(r['agentId'] for r in rows if r['type'] == 'subagent.started'
                      and r['data']['agentDisplayName'] == 'qa')
        rows.extend([self.event('tool.execution_start', 13, {
            'toolCallId': 'queued-follow-up', 'toolName': 'write_agent',
            'arguments': {'agent_id': worker, 'message': 'Please revisit the reviewed checks.'}}),
            self.event('tool.execution_complete', 13.1, {'toolCallId': 'queued-follow-up', 'success': True,
                        'toolTelemetry': {'properties': {'agent_id': worker}}})])
        self.save(rows)
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'pending-native-turn')

    def cross_seal(self, *, observed=None, receipt=None, agent=None):
        call = 'sealing-tool'
        result = {'toolCallId': call, 'success': True, 'shellExecution': {'exitCode': 0}}
        if observed is not None:
            result['fileEdits'] = [{'path': str(self.project / observed), 'kind': 'edit'}]
        if receipt is not None:
            result['result'] = {'content': team.RECEIPT + receipt['sha256']}
        return [self.event('tool.execution_start', -.5,
                           {'toolCallId': call, 'toolName': 'powershell',
                            'arguments': {'command': "& 'C:\\Python313\\python.exe' 'scripts\\team.py' init --plan plan.json"}}),
                self.event('tool.execution_complete', .1, result, agent)]

    def test_plan_sealing_command_can_complete_after_cutoff(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa) + self.cross_seal()
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertTrue(result['passed'], result)

    def test_cross_cutoff_completion_does_not_authenticate_prior_tool_receipts(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows = [r for r in rows if r['data'].get('toolCallId') != integrated['sha256']]
        rows += self.cross_seal(receipt=integrated)
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertIn('integration: missing native tool receipt', result['errors'][0])

    def test_cross_cutoff_completion_still_accounts_for_postseal_writes(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa) + self.cross_seal(observed='calc.py')
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertIn('Coordinator wrote outside', result['errors'][0])

    def test_true_orphan_and_changed_caller_still_fail_at_cutoff(self):
        owner, integrated, check, qa, _ = self.complete()
        baseline = self.trace(owner, integrated, check, qa)
        start, finish = self.cross_seal()
        self.save(sorted(baseline + [finish], key=lambda r: r['timestamp']))
        self.assertIn('lacks its original tool call', self.verify()['errors'][0])
        finish['agentId'] = str(uuid4())
        self.save(sorted(baseline + [start, finish], key=lambda r: r['timestamp']))
        self.assertIn('changed agent identity', self.verify()['errors'][0])

    def test_preseal_pending_starts_are_bounded_and_completed_calls_are_discarded(self):
        owner, integrated, check, qa, _ = self.complete()
        baseline = self.trace(owner, integrated, check, qa)
        start, finish = self.cross_seal()
        second = self.event('tool.execution_start', -.2, {'toolCallId': 'second-preplan'})
        self.save(sorted(baseline + [start, second, finish], key=lambda r: r['timestamp']))
        with patch.object(team_v2, 'MAX_NATIVE_PENDING_CALLS', 1):
            result = self.verify()
        self.assertEqual(result['status'], 'UNVERIFIED')
        self.assertIn('pre-plan pending tool budget', result['errors'][0])
        finish['timestamp'] = self.event('unused', -.3, {})['timestamp']
        self.save(sorted(baseline + [start, finish], key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertTrue(result['passed'], result)
        rows = [r for r in baseline if r['data'].get('toolCallId') != integrated['sha256']]
        post = self.event('tool.execution_complete', 7, {'toolCallId': 'sealing-tool', 'success': True})
        self.save(sorted(rows + [start, finish, post], key=lambda r: r['timestamp']))
        self.assertIn('lacks its original tool call', self.verify()['errors'][0])

    def test_selected_parent_binding_can_be_reused_without_inventing_an_identity(self):
        owner, integrated, check, qa, _ = self.complete()
        self.trace(owner, integrated, check, qa)
        proof.save(self.project / '.runtime-proof/teams/fix/host.json',
                   {'parent': self.parent, 'sessions': str(self.sessions)})
        result = team.verify_registered(self.project, 'fix')
        self.assertTrue(result['passed'], result)

    def test_explicit_runtime_parent_env_validates_actual_native_header(self):
        owner, integrated, check, qa, _ = self.complete()
        self.trace(owner, integrated, check, qa)
        with patch.dict(team_v2.os.environ, {'HARRTEST_PARENT_SESSION_ID': self.parent,
                                           'CODEX_THREAD_ID': str(uuid4())}):
            result = team.verify_registered(self.project, 'fix', sessions=self.sessions)
            self.assertTrue(result['passed'], result)
            result = team.verify_registered(self.project, 'fix', parent=str(uuid4()), sessions=self.sessions)
            self.assertEqual(result['status'], 'UNVERIFIED')
        with patch.dict(team_v2.os.environ, {'HARRTEST_PARENT_SESSION_ID': str(uuid4())}):
            self.assertEqual(team.verify_registered(self.project, 'fix', sessions=self.sessions)['status'], 'UNVERIFIED')

    def test_large_preplan_history_does_not_require_fullfile_retention(self):
        owner, integrated, check, qa, _ = self.complete()
        self.trace(owner, integrated, check, qa)
        add_preplan_history(self.path, self.state['created'], 'copilot')
        self.assertGreater(self.path.stat().st_size, team.MAX_ROLLOUT_BYTES)
        self.assertTrue(self.verify()['passed'], self.verify())

    def test_incomplete_tail_cannot_finish_a_pending_qa_turn(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        text = ''.join(json.dumps(x) + '\n' for x in rows)
        self.path.write_text(text.rstrip('\n'), encoding='utf-8')
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertEqual(result['status'], 'pending-native-turn')

    def test_oversized_malformed_and_exhausted_evidence_stay_unverified(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        original = self.path.read_bytes()
        header, rest = original.split(b'\n', 1)
        self.path.write_bytes(header + b'\n' + b'{"timestamp":"1900-01-01T00:00:00Z","payload":"' + b'x' * team_v2.MAX_NATIVE_EVENT_BYTES + b'"}\n' + rest)
        self.assertEqual(self.verify()['status'], 'UNVERIFIED')
        self.path.write_bytes(header + b'\n' + b'{"data":{"timestamp":"1900-01-01T00:00:00Z"},broken}\n' + rest)
        self.assertEqual(self.verify()['status'], 'UNVERIFIED')
        self.save(rows)
        with patch.object(team_v2, 'MAX_NATIVE_WINDOW_EVENTS', 2):
            self.assertEqual(self.verify()['status'], 'UNVERIFIED')
        with patch.object(team_v2, 'MAX_NATIVE_WINDOW_BYTES', 100):
            self.assertEqual(self.verify()['status'], 'UNVERIFIED')
        with patch.object(team_v2, 'MAX_NATIVE_PENDING_CALLS', 0):
            self.assertEqual(self.verify()['status'], 'UNVERIFIED')

    def test_assistant_text_cannot_replace_a_completed_native_receipt(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows = [r for r in rows if not (r['type'] == 'tool.execution_complete'
                and r['data'].get('toolCallId') == check['sha256'])]
        rows.append(self.event('assistant.message', 10, {'content': team.RECEIPT + check['sha256']}))
        self.save(rows)
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertIn('missing native tool receipt', result['errors'][0])

    def test_echoed_command_does_not_authenticate_receipt_stdout(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        for r in rows:
            if r['type'] == 'tool.execution_start' and r['data'].get('toolCallId') == check['sha256']:
                r['data']['arguments']['command'] = 'Write-Output "python scripts/team.py handoff"'
        self.save(rows)
        self.assertFalse(self.verify()['passed'])

    def test_changed_native_agent_binding_and_workspace_are_rejected(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        target = next(r for r in rows if r['type'] == 'tool.execution_complete' and r['data'].get('fileEdits'))
        target['data']['parentToolCallId'] = 'another-origin'
        self.save(rows)
        self.assertFalse(self.verify()['passed'])
        rows = self.trace(owner, integrated, check, qa)
        rows[0]['data']['context']['cwd'] = str(self.project.parent)
        self.save(rows)
        self.assertFalse(self.verify()['passed'])

    def test_unsupported_native_version_stays_unverified(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows[0]['data']['version'] = 99
        self.save(rows)
        self.assertEqual(self.verify()['status'], 'UNVERIFIED')

    def test_checkpoint_replay_and_later_workspace_change_cannot_authenticate(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        next(r for r in rows if r['type'] == 'tool.execution_complete'
             and r['data'].get('toolCallId') == check['sha256'])['checkpoint'] = True
        self.save(rows)
        self.assertFalse(self.verify()['passed'])
        rows = self.trace(owner, integrated, check, qa)
        rows.append(self.event('session.context_changed', 13, {'cwd': str(self.project.parent)}))
        self.save(rows)
        self.assertFalse(self.verify()['passed'])

    def test_native_effort_mismatch_and_failed_shell_cannot_pass(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        next(r for r in rows if r['type'] == 'subagent.configured')['data']['reasoningEffort'] = 'high'
        self.save(rows)
        self.assertFalse(self.verify()['passed'])
        rows = self.trace(owner, integrated, check, qa)
        next(r for r in rows if r['type'] == 'tool.execution_complete'
             and r['data'].get('toolCallId') == check['sha256'])['data']['shellExecution']['exitCode'] = 1
        self.save(rows)
        self.assertFalse(self.verify()['passed'])

    def test_same_model_changed_effort_before_seal_cannot_pass_low_pin(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows.append(self.event('session.model_change', -.5,
                               {'newModel': 'fixture-model', 'reasoningEffort': 'high', 'source': 'user'}))
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertIn('reasoning_effort differs', result['errors'][0])

    def test_postseal_effort_transition_remains_failed_after_return_to_low(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows += [self.event('session.model_change', 6, {'newModel': 'fixture-model', 'reasoningEffort': 'high'}),
                 self.event('session.model_change', 6.5, {'newModel': 'fixture-model', 'reasoningEffort': 'low'})]
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertIn('reasoning_effort differs', result['errors'][0])

    def test_sparse_preseal_transitions_preserve_last_effort_and_accept_correct_current_context(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows[0]['data']['selectedModel'] = 'old-model'
        rows[0]['data']['reasoningEffort'] = 'max'
        rows += [self.event('session.model_change', -.9, {'newModel': 'fixture-model', 'reasoningEffort': 'high'}),
                 self.event('session.model_change', -.7, {'newModel': 'fixture-model'})]
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        self.assertFalse(self.verify()['passed'])
        # The current low context is established by this actual sparse native
        # event, while the prior actual record still supplies the model value.
        rows.append(self.event('session.model_change', -.5, {'reasoningEffort': 'low'}))
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertTrue(result['passed'], result)

    def test_sparse_postseal_transitions_are_observed(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows += [self.event('session.model_change', 6, {'reasoningEffort': 'high'}),
                 self.event('session.model_change', 6.5, {'newModel': 'fixture-model'})]
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        self.assertFalse(self.verify()['passed'])

    def test_equal_timestamp_sparse_transitions_keep_actual_native_record_order(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows += [self.event('session.model_change', -.5, {'newModel': 'earlier-model'}),
                 self.event('session.model_change', -.5, {'newModel': 'intermediate-model', 'reasoningEffort': 'low'}),
                 self.event('session.model_change', -.5, {'newModel': 'fixture-model'})]
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        result = self.verify()
        self.assertTrue(result['passed'], result)

    def test_child_model_effort_transition_is_observed(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        child = next(r['agentId'] for r in rows if r['type'] == 'subagent.started'
                     and r['data']['agentDisplayName'] == 'arithmetic')
        rows.append(self.event('session.model_change', 3, {'newModel': 'fixture-model', 'reasoningEffort': 'high'}, child))
        self.save(sorted(rows, key=lambda r: r['timestamp']))
        self.assertFalse(self.verify()['passed'])

    def test_current_model_and_effort_transitions_cannot_be_reordered(self):
        owner, integrated, check, qa, _ = self.complete()
        rows = self.trace(owner, integrated, check, qa)
        rows.append(self.event('session.model_change', -.5,
                               {'newModel': 'fixture-model', 'reasoningEffort': 'high'}))
        self.save(rows)
        self.assertEqual(self.verify()['status'], 'UNVERIFIED')


def add_preplan_history(path, created, host):
    """Many ordinary bounded records, not one inflated event or generated artifact."""
    original = path.read_bytes()
    header, rest = original.split(b'\n', 1)
    timestamp = (team.instant(created) - timedelta(seconds=.5)).isoformat()
    with path.open('wb') as output:
        output.write(header + b'\n')
        for i in range(600):
            row = ({'type': 'assistant.message', 'data': {'content': 'x' * 60000}, 'id': 'old-' + str(i)}
                   if host == 'copilot' else {'type': 'response_item', 'payload': {'type': 'message', 'content': 'x' * 60000}})
            row['timestamp'] = timestamp
            output.write((json.dumps(row) + '\n').encode())
        output.write(rest)


class NativeSnapshotTests(unittest.TestCase):
    def test_fixed_snapshot_does_not_follow_appended_complete_receipts(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'events.jsonl'
        now = datetime.now().astimezone()
        header = {'type': 'session.start', 'timestamp': now.isoformat(), 'data': {}}
        partial = json.dumps({'type': 'tool.execution_complete', 'timestamp': now.isoformat(), 'data': {}})
        path.write_text(json.dumps(header) + '\n' + partial, encoding='utf-8')
        window = team_v2.NativeWindow(path, now, 'copilot')
        iterator = iter(window)
        self.assertEqual(next(iterator)['type'], 'session.start')
        with path.open('a') as output:
            output.write('\n' + json.dumps({'type': 'subagent.completed', 'timestamp': now.isoformat(), 'data': {}}) + '\n')
        self.assertEqual(list(iterator), [])
        self.assertTrue(window.tail_incomplete)
        self.assertLess(window.snapshot_bytes, path.stat().st_size)

    def test_latest_preseal_context_and_boundary_transition_are_both_retained(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'events.jsonl'
        now = datetime.now().astimezone()
        events = [{'type': 'session_meta', 'timestamp': (now - timedelta(seconds=3)).isoformat(), 'payload': {}},
                  {'type': 'turn_context', 'timestamp': (now - timedelta(seconds=2)).isoformat(),
                   'payload': {'model': 'old', 'effort': 'low'}},
                  {'type': 'turn_context', 'timestamp': (now - timedelta(seconds=1)).isoformat(),
                   'payload': {'model': 'current', 'effort': 'low'}},
                  {'type': 'turn_context', 'timestamp': now.isoformat(),
                   'payload': {'model': 'changed', 'effort': 'high'}}]
        path.write_text(''.join(json.dumps(x) + '\n' for x in events), encoding='utf-8')
        window = team_v2.NativeWindow(path, now, 'codex')
        retained = list(window)
        self.assertEqual([x['payload'].get('model') for x in retained], [None, 'current', 'changed'])
        self.assertEqual(window.contexts, [events[2]['payload'], events[3]['payload']])

    def test_oversized_current_event_is_unverified_without_timestamp_guessing(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / 'events.jsonl'
        now = datetime.now().astimezone()
        header = {'type': 'session.start', 'timestamp': now.isoformat(), 'data': {}}
        bad = {'type': 'assistant.message', 'timestamp': now.isoformat(), 'data': {'text': 'x' * 200}}
        path.write_text(json.dumps(header) + '\n' + json.dumps(bad) + '\n', encoding='utf-8')
        with patch.object(team_v2, 'MAX_NATIVE_EVENT_BYTES', 180):
            with self.assertRaises(team_v2.HostEvidenceUnavailable):
                list(team_v2.NativeWindow(path, now, 'copilot'))


if __name__ == '__main__':
    unittest.main()
