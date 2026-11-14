"""Existing-code Team2 behavior; native adapter fixtures are not live-model claims."""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import proof
import team
import team_v2


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
        owner = self.implement()
        integrated, packet = team.integrate(self.project, self.state)
        check = team.runtime_check(self.project, self.state, [sys.executable, '-B', '-c',
                                   'from calc import add; assert add(7,5)==12; assert add(-7,5)==-2'])
        self.assertEqual(check['exit_code'], 0)
        evidence = '.runtime-proof/teams/fix/qa.txt'
        self.write(evidence, 'Independently imported add and checked positive and signed arithmetic through the existing interface.')
        review = team.review(self.project, self.state, evidence, 'pass')
        return owner, integrated, check, review, packet

    def test_single_owner_real_check_without_invented_glue(self):
        owner, integrated, check, review, packet = self.complete()
        self.assertEqual(set(integrated['files']), {'calc.py'})
        self.assertEqual(integrated['inputs'], {'arithmetic': owner['sha256']})
        self.assertEqual(review['check'], check['sha256'])
        self.assertEqual(packet['task_name'], 'qa')
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
        self.start()
        self.write('rules.txt', 'Different semantics cannot reuse the prior sealed attempt.\n')
        with self.assertRaisesRegex(ValueError, 'context changed'):
            team.ready_packets(self.project, self.state)

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

    def native(self, role, start, end, writes, receipts, uid=None):
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
            rows.extend([event('response_item', sec, {'type': 'custom_tool_call', 'name': 'exec',
                         'call_id': str(i), 'input': 'text(await tools.exec_command({"cmd":"python scripts/team.py handoff"}));'}),
                         event('response_item', sec + .01, {'type': 'custom_tool_call_output', 'call_id': str(i),
                         'output': [{'text': 'Output:\n' + team.RECEIPT + receipt['sha256']}]})])
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

    def trace(self, owner, integrated, check, qa):
        rows = [self.event('session.start', -1, {
            'sessionId': self.parent, 'version': 1, 'producer': 'copilot-agent',
            'copilotVersion': '1.0.104', 'selectedModel': 'fixture-model', 'reasoningEffort': 'low',
            'startTime': (team.instant(self.state['created']) - timedelta(seconds=1)).isoformat(),
            'context': {'cwd': str(self.project)}})]
        for role, start, finish, writes, receipts in [
                ('arithmetic', 1, 5, ['calc.py'], [(owner, 4)]),
                ('integration', -1, None, [], [(integrated, 7)]),
                ('qa', 8, 12, [], [(check, 9), (qa, 11)])]:
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
                payload = {'toolCallId': call, 'toolName': 'powershell', 'model': 'fixture-model',
                           'arguments': {'command': 'python scripts/team.py handoff'}, 'parentToolCallId': dispatch}
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
