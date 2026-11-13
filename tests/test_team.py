"""Check production evidence gates with a controlled native rollout fixture.

The live release comparison uses real model rollouts in separate workspaces.
"""
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from uuid import uuid4

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
import team


class ProductionTeam(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve()
        self.sessions = self.project / 'sessions'
        self.logs = self.sessions / '2026/01/01'
        self.logs.mkdir(parents=True)
        self.parent = str(uuid4())
        self.plan = {
            'schema': 1, 'id': 'report', 'kind': 'greenfield',
            'request': 'Build a report from validated records and print a formatted total.',
            'contract': 'parse.py returns integer amounts. format.py formats an integer total.',
            'outcomes': {'parse': 'Reject malformed amounts before returning records.',
                         'format': 'Display the final report with its visible total.'},
            'tasks': [
                {'id': 'parser', 'brief': 'Implement input parsing in its own module.',
                 'outputs': ['parse.py'], 'depends_on': [], 'outcomes': ['parse']},
                {'id': 'formatter', 'brief': 'Implement the user-visible formatter.',
                 'outputs': ['format.py'], 'depends_on': [], 'outcomes': ['format']},
            ],
            'integration': {'outputs': ['main.py'], 'check': 'Run the public CLI on valid and malformed input.'},
        }

    def start(self):
        self.result = team.init(self.project, self.plan)
        self.state = team.load_state(self.project, 'report')
        self.clock = datetime.fromisoformat(self.state['created'])

    def stamp(self, sec):
        return (self.clock + timedelta(seconds=sec)).isoformat()

    def hold_native_turn_open(self, role):
        for path in self.logs.glob('*.jsonl'):
            rows = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
            source = rows[0]['payload']['source']
            if not isinstance(source, dict) or source['subagent']['thread_spawn']['agent_path'] != '/root/' + role:
                continue
            ending = next(r for r in rows if r['type'] == 'event_msg' and r['payload']['type'] == 'task_complete')
            rows.remove(ending)
            path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
            return path, ending
        self.fail('No native role trace to hold open')

    def test_handoff_does_not_complete_a_still_open_native_turn(self):
        self.deliver()
        self.hold_native_turn_open('parser')
        result = self.verify()
        self.assertFalse(result['passed'])
        self.assertTrue(result['retryable'])
        self.assertFalse(result['mission_complete'])
        self.assertEqual(result['pending_workers'], ['parser'])
        expired = team.verify_registered(self.project, 'report', parent=self.parent,
                                         sessions=self.sessions, wait_seconds=0.05)
        self.assertFalse(expired['passed'])
        self.assertEqual(expired['status'], 'pending-native-turn')

    def test_grace_observes_real_worker_completion_before_accepting(self):
        self.deliver()
        path, ending = self.hold_native_turn_open('parser')
        self.assertFalse(self.verify()['passed'])
        def finish():
            time.sleep(0.15)
            with path.open('a', encoding='utf-8') as target:
                target.write(json.dumps(ending) + '\n')
        writer = threading.Thread(target=finish)
        writer.start()
        try:
            result = team.verify_registered(self.project, 'report', parent=self.parent,
                                            sessions=self.sessions, wait_seconds=2)
        finally:
            writer.join()
        self.assertTrue(result['passed'], result)

    def test_pending_qa_never_becomes_acceptance_by_timeout(self):
        self.deliver()
        self.hold_native_turn_open('qa')
        result = team.verify_registered(self.project, 'report', parent=self.parent,
                                        sessions=self.sessions, wait_seconds=0.05)
        self.assertFalse(result['passed'])
        self.assertEqual(result['pending_workers'], ['qa'])

    def test_completed_handoffs_survive_a_later_open_turn_without_changes(self):
        self.deliver()
        for path in self.logs.glob('*.jsonl'):
            source = team.log_meta(path)['source']
            if not isinstance(source, dict):
                continue
            role = source['subagent']['thread_spawn']['agent_path'].rsplit('/', 1)[-1]
            if role in ('parser', 'qa'):
                with path.open('a', encoding='utf-8') as target:
                    target.write(json.dumps({'type': 'event_msg', 'timestamp': self.stamp(27),
                                             'payload': {'type': 'task_started'}}) + '\n')
        self.assertTrue(self.verify()['passed'], self.verify())

    def source(self, rel, content):
        path = self.project / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')

    def log(self, worker, start, end, *, patches=(), receipts=()):
        uid = self.parent if worker is None else str(uuid4())
        source = 'exec' if worker is None else {
            'subagent': {'thread_spawn': {'parent_thread_id': self.parent,
                                         'agent_path': '/root/' + worker, 'depth': 1}}}

        def event(kind, sec, data):
            return {'type': kind, 'timestamp': self.stamp(sec), 'payload': data}

        rows = [event('session_meta', start, {'id': uid, 'source': source,
                  'cwd': str(self.project), 'timestamp': self.stamp(start)}),
                event('turn_context', start, {'model': 'fixture', 'effort': 'low'}),
                event('event_msg', start, {'type': 'task_started'})]
        for i, (rel, sec) in enumerate(patches):
            call = f'write{i}'
            change = json.dumps(f'*** Begin Patch\n*** Add File: {rel}\n+body\n*** End Patch')
            rows += [event('response_item', sec, {'type': 'custom_tool_call', 'name': 'exec',
                      'input': 'text(await tools.apply_patch(' + change + '));', 'call_id': call}),
                     event('response_item', sec + .01, {'type': 'custom_tool_call_output',
                      'call_id': call, 'output': [{'text': 'Script completed\nOutput:\n{}'}]})]
        for i, (receipt, sec) in enumerate(receipts):
            call = f'record{i}'
            rows += [event('response_item', sec, {'type': 'custom_tool_call', 'name': 'exec',
                      'input': 'text(await tools.exec_command({"cmd":"python scripts/team.py handoff"}));', 'call_id': call}),
                     event('response_item', sec + .01, {'type': 'custom_tool_call_output',
                      'call_id': call, 'output': [{'text': 'Output:\n' + team.RECEIPT + receipt['sha256']} ]})]
        if end is not None:
            rows.append(event('event_msg', end, {'type': 'task_complete'}))
        (self.logs / f'rollout-2026-01-01T00-00-00-{uid}.jsonl').write_text(
            ''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')

    def deliver(self, *, serial=False, review_only=False, coordinator_write=False,
                qa_early=False, early_scaffold=False, early_assembly=False):
        if early_scaffold:
            self.plan['integration']['outputs'].append('index.html')
        self.start()
        self.source('parse.py', 'def parse(value): return int(value)\n')
        self.source('format.py', 'def show(total): return str(total)\n')
        parser = team.handoff(self.project, self.state, self.plan['tasks'][0])
        formatter = team.handoff(self.project, self.state, self.plan['tasks'][1])
        self.source('main.py', 'from parse import parse\nfrom format import show\nprint(show(parse("7")))\n')
        if early_scaffold:
            self.source('index.html', '<p>Report</p>\n')
        assembled, qa_packet = team.integrate(self.project, self.state)
        evidence = '.runtime-proof/teams/report/qa-evidence.txt'
        # Actual public process rather than a worker's assertion in the fixture.
        checked = team.runtime_check(self.project, self.state, [sys.executable, '-B', 'main.py'])
        self.assertEqual(checked['exit_code'], 0)
        retained = team.proof.load(self.project / next(iter(checked['files'])))
        self.assertEqual(retained['stdout'].strip(), '7')
        self.source(evidence, f'Executed main.py. Observed stdout: {retained["stdout"]}')
        qa = team.review(self.project, self.state, evidence, 'pass')
        self.assertEqual(qa_packet['task_name'], 'qa')
        self.log('parser', 1, 8, patches=[] if review_only else [('parse.py', 4)], receipts=[(parser, 6)])
        self.log('formatter', 9 if serial else 2, 14, patches=[('format.py', 10)], receipts=[(formatter, 12)])
        patches = [('main.py', 3 if early_assembly else 16)]
        if early_scaffold:
            patches.append(('index.html', .5))
        if coordinator_write:
            patches.append(('parse.py', 17))
        self.log(None, -10, None, patches=patches, receipts=[(assembled, 18)])
        self.log('qa', 15 if qa_early else 19, 25, receipts=[(checked, 21), (qa, 23)])

    def verify(self, require_qa=True):
        return team.verify_registered(self.project, 'report', require_qa=require_qa,
                                      parent=self.parent, sessions=self.sessions)

    def test_contributing_workers_and_later_independent_qa(self):
        self.deliver()
        report = self.verify()
        self.assertTrue(report['passed'], report)
        self.assertEqual(report['overlap'], [['parser', 'formatter']])
        self.assertTrue(report['independent_qa'])
        sha = hashlib.sha256(self.plan['request'].encode()).hexdigest()
        self.assertEqual(team.binding(self.project, 'report', sha)['integration_outputs'],
                         ['main.py', 'parse.py', 'format.py'])
        self.assertEqual([p['task_name'] for p in self.result['ready']], ['parser', 'formatter'])
        with self.assertRaisesRegex(ValueError, 'different original request'):
            team.binding(self.project, 'report', '0' * 64)

    def test_review_only_worker_cannot_take_credit_for_existing_file(self):
        self.deliver(review_only=True)
        report = self.verify()
        self.assertFalse(report['passed'])
        self.assertIn('native writes must match', report['errors'][0])

    def test_serial_worker_logs_do_not_prove_parallel_work(self):
        self.deliver(serial=True)
        self.assertIn('No overlap', self.verify()['errors'][0])

    def test_coordinator_cannot_rewrite_worker_output(self):
        self.deliver(coordinator_write=True)
        self.assertIn('Coordinator wrote', self.verify()['errors'][0])

    def test_early_reviewer_cannot_close_team(self):
        self.deliver(qa_early=True)
        self.assertTrue(self.verify(require_qa=False)['passed'])
        self.assertIn('QA must be', self.verify()['errors'][0])

    def test_current_proof_rejects_edited_component(self):
        self.deliver()
        self.source('parse.py', 'def parse(value): return 0\n')
        self.assertIn('handoff is stale', self.verify()['errors'][0])

    def test_scaffold_can_precede_workers_but_assembly_must_follow(self):
        self.deliver(early_scaffold=True)
        self.assertTrue(self.verify()['passed'])

    def test_assembly_before_component_handoffs_is_not_integrated(self):
        self.deliver(early_assembly=True)
        self.assertIn('Integration glue must be written', self.verify()['errors'][0])

    def test_plan_rejects_scope_overlap_and_review_roles(self):
        self.plan['tasks'][1]['outputs'] = ['PARSE.PY']
        with self.assertRaisesRegex(ValueError, 'scopes overlap'):
            self.start()
        self.plan['tasks'][1]['outputs'] = ['format.py']
        self.plan['tasks'][1]['role'] = 'review'
        with self.assertRaisesRegex(ValueError, 'own implementation'):
            self.start()

    def test_worker_must_change_output_after_registration(self):
        self.plan['kind'] = 'change'
        self.source('parse.py', 'old source')
        self.start()
        with self.assertRaisesRegex(ValueError, 'changed file'):
            team.handoff(self.project, self.state, self.plan['tasks'][0])

    def test_idle_time_between_turns_does_not_establish_overlap(self):
        left = {'intervals': [(self.stamp_clock(1), self.stamp_clock(4)),
                              (self.stamp_clock(12), self.stamp_clock(15))]}
        right = {'intervals': [(self.stamp_clock(6), self.stamp_clock(9))]}
        self.assertFalse(team.completed_overlap(left, right))
        self.assertFalse(team.completed_receipt(left, self.stamp_clock(10)))
        right['intervals'].append((self.stamp_clock(13), self.stamp_clock(16)))
        self.assertTrue(team.completed_overlap(left, right))

    @staticmethod
    def stamp_clock(second):
        return datetime.fromisoformat('2026-01-01T00:00:00+00:00') + timedelta(seconds=second)

    def test_patch_text_in_unrelated_source_does_not_credit_a_write(self):
        call = {'name': 'exec', 'input': "text('tools.apply_patch('); text('\\n*** Add File: fake.py\\n');"}
        self.assertEqual(team.patch_paths(self.project, call, 'Script completed\nOutput:\n{}'), set())
        patch = '*** Begin Patch\n*** Add File: parser.py\n+value = 1\n*** End Patch'
        literal = {'name': 'exec', 'input': 'const patch = ' + json.dumps(patch) + ';\ntext(await tools.apply_patch(patch));'}
        self.assertEqual(team.patch_paths(self.project, literal, 'Script completed\nOutput:\n{}'), {'parser.py'})
        self.assertEqual(team.patch_paths(self.project, literal, 'Script completed\nOutput:\nError: failed'), set())

    def test_native_two_variable_patch_wrapper_is_recognized_without_extra_code(self):
        patch = '*** Begin Patch\n*** Add File: parser.py\n+value = 1\n*** End Patch'
        source = 'const patch = ' + json.dumps(patch) + ';\nconst r = await tools.apply_patch(patch); text(r);'
        success = 'Script completed\nOutput:\n{}'
        self.assertEqual(team.patch_paths(self.project, {'name': 'exec', 'input': source}, success), {'parser.py'})
        for altered in (source.replace('text(r)', 'text(other)'),
                        source + ' text("unrelated");',
                        source.replace('tools.apply_patch(patch)', 'tools.other(patch)')):
            self.assertEqual(team.patch_paths(self.project, {'name': 'exec', 'input': altered}, success), set())

    def test_explicit_validation_context_is_sealed_and_reaches_all_packets(self):
        target = '.runtime-proof/target.json'
        self.source(target, '{"minimum_throughput": 30, "runtime": "declared"}\n')
        self.plan['validation_context'] = [target]
        self.deliver()
        digest = team.proof.file_hash(self.project / target)
        self.assertEqual(self.state['validation_inputs'], {target: digest})
        for ready in self.result['ready']:
            self.assertIn((self.project / target).as_posix(), ready['message'])
            self.assertIn(digest, ready['message'])
        _, qa = team.integrate(self.project, self.state)
        self.assertIn((self.project / target).as_posix(), qa['message'])
        self.assertIn(digest, qa['message'])
        self.source(target, '{"minimum_throughput": 1}\n')
        with self.assertRaisesRegex(ValueError, 'validation context changed'):
            team.load_state(self.project, 'report')
        with self.assertRaisesRegex(ValueError, 'validation context changed'):
            team.packet(self.project, self.state, self.plan['tasks'][0])
        with self.assertRaisesRegex(ValueError, 'validation context changed'):
            team.integrate(self.project, self.state)
        self.assertIn('validation context changed', self.verify()['errors'][0])

    def test_validation_context_rejects_unbounded_and_escaping_inputs(self):
        self.plan['validation_context'] = ['../outside.json']
        with self.assertRaises(ValueError):
            self.start()
        self.source('target.json', 'x' * (team.MAX_VALIDATION_FILE_BYTES + 1))
        self.plan['validation_context'] = ['target.json']
        with self.assertRaisesRegex(ValueError, 'too large'):
            self.start()
        self.source('target.json', '{}')
        self.plan['validation_context'] = ['target.json', 'target.json']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.start()

    def test_failed_qa_repair_returns_to_owner_and_forces_reintegration(self):
        target = '.runtime-proof/target.json'
        self.source(target, '{"runtime": "same-profile"}\n')
        self.plan['validation_context'] = [target]
        self.deliver()
        evidence = '.runtime-proof/teams/report/qa-evidence.txt'
        self.source(evidence, 'Public malformed input accepted; parser boundary check failed.')
        failed = team.review(self.project, self.state, evidence, 'fail')
        request = team.repair(self.project, self.state, 'parser', evidence,
                              'Malformed amount reaches output instead of rejecting before formatting.')
        self.assertFalse(request['mission_complete'])
        self.assertEqual(request['packet']['task_name'], 'parser')
        self.assertIn('Exclusive product files: parse.py', request['packet']['message'])
        self.assertIn((self.project / target).as_posix(), request['packet']['message'])
        self.assertIn('Malformed amount', request['packet']['message'])
        self.assertEqual([p['task_name'] for p in team.ready_packets(self.project, self.state)], ['parser'])
        with self.assertRaisesRegex(ValueError, 'fresh owner handoffs'):
            team.integrate(self.project, self.state)
        old = team.current_receipt(self.project, self.state, 'integration')
        self.source('parse.py', 'def parse(value):\n if not value.isdigit(): raise ValueError("amount")\n return int(value)\n')
        repaired = team.handoff(self.project, self.state, self.plan['tasks'][0])
        self.assertEqual(repaired['repair'], request['repair'])
        # A successful old check cannot accept newly handed-off source.
        with self.assertRaisesRegex(ValueError, 'Reintegrate fresh owner handoffs'):
            team.review(self.project, self.state, evidence, 'pass')
        integrated, _ = team.integrate(self.project, self.state)
        self.assertNotEqual(old['sha256'], integrated['sha256'])
        with self.assertRaisesRegex(ValueError, 'successful current subprocess'):
            team.review(self.project, self.state, evidence, 'pass')
        checked = team.runtime_check(self.project, self.state, [sys.executable, '-B', 'main.py'])
        self.assertEqual(checked['exit_code'], 0)
        # Rewriting the live narrative must not erase the retained failure.
        self.source(evidence, 'Replayed public CLI after parser repair; output 7, malformed input separately rejected.')
        accepted = team.review(self.project, self.state, evidence, 'pass')
        self.assertEqual(accepted['integration'], integrated['sha256'])
        self.assertEqual(team.ready_packets(self.project, self.state), [])
        repair = team.current_receipt(self.project, self.state, 'repair-parser')
        self.assertEqual(repair['qa'], failed['sha256'])
        retained = self.project / next(iter(repair['files']))
        self.assertIn('parser boundary check failed', retained.read_text(encoding='utf-8'))

    def test_repair_requires_failed_current_qa_and_a_declared_owner(self):
        self.deliver()
        evidence = '.runtime-proof/teams/report/qa-evidence.txt'
        with self.assertRaisesRegex(ValueError, 'failed QA'):
            team.repair(self.project, self.state, 'parser', evidence, 'Observed failure.')
        with self.assertRaisesRegex(ValueError, 'declared implementation owner'):
            team.repair(self.project, self.state, 'invented', evidence, 'Observed failure.')
        team.review(self.project, self.state, evidence, 'fail')
        with self.assertRaisesRegex(ValueError, 'private team directory'):
            team.repair(self.project, self.state, 'parser', 'parse.py', 'Observed failure.')

    def test_failed_review_cli_is_nonzero_and_directs_owner_repair(self):
        self.deliver()
        result = subprocess.run([sys.executable, '-B', str(REPO / 'scripts/team.py'), '--project', str(self.project),
                                 'review', '--team', 'report', '--evidence',
                                 '.runtime-proof/teams/report/qa-evidence.txt', '--verdict', 'fail'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('"passed": false', result.stdout)
        self.assertIn('"mission_complete": false', result.stdout)
        self.assertIn('assign-owner-repair', result.stdout)

    def test_ready_packets_reopen_stale_outputs_instead_of_suppressing_them(self):
        self.deliver()
        self.assertEqual(team.ready_packets(self.project, self.state), [])
        self.source('parse.py', 'def parse(value): return 0\n')
        self.assertEqual([p['task_name'] for p in team.ready_packets(self.project, self.state)], ['parser'])

    def test_changed_prerequisite_reopens_dependent_chain_in_order(self):
        self.plan['tasks'].extend([
            {'id': 'writer', 'brief': 'Write validated records using the parser interface.',
             'outputs': ['writer.py'], 'depends_on': ['parser'], 'outcomes': ['parse']},
            {'id': 'archive', 'brief': 'Archive the writer output without changing its content.',
             'outputs': ['archive.py'], 'depends_on': ['writer'], 'outcomes': ['format']},
        ])
        self.start()
        for task in self.plan['tasks']:
            self.source(task['outputs'][0], f'{task["id"]} output\n')
            team.handoff(self.project, self.state, task)
        self.assertEqual(team.ready_packets(self.project, self.state), [])
        self.source('parse.py', 'Updated parser output\n')
        team.handoff(self.project, self.state, self.plan['tasks'][0])
        self.assertEqual([p['task_name'] for p in team.ready_packets(self.project, self.state)], ['writer'])
        with self.assertRaisesRegex(ValueError, 'stale prerequisite'):
            team.handoff(self.project, self.state, self.plan['tasks'][3])
        team.handoff(self.project, self.state, self.plan['tasks'][2])
        self.assertEqual([p['task_name'] for p in team.ready_packets(self.project, self.state)], ['archive'])

    def shell_check_trace(self, *, poll=True, requested=93469, returned=None, direct=False,
                          plain=False, launch_marker=False, poll_command=None):
        """Replace the fixture check receipt with native launch/poll result envelopes."""
        path = next(p for p in self.logs.glob('*.jsonl')
                    if isinstance(team.log_meta(p).get('source'), dict)
                    and team.log_meta(p)['source'].get('subagent', {}).get('thread_spawn', {}).get('agent_path') == '/root/qa')
        rows = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
        rows = [r for r in rows if r.get('payload', {}).get('call_id') != 'poll0']
        check = team.current_receipt(self.project, self.state, 'check')
        marker = team.RECEIPT + check['sha256'] + '\r\n'
        def output(result):
            return [{'text': 'Script completed\nWall time 0.1 seconds\nOutput:\n'},
                    {'text': json.dumps(result)}]
        start = next(r for r in rows if r['payload'].get('type') == 'custom_tool_call'
                     and r['payload'].get('call_id') == 'record0')
        start['payload']['input'] = ('const r = await tools.exec_command({cmd:"python -B scripts/team.py check '
                                     '--team report -- python main.py",max_output_tokens:2000}); text(JSON.stringify(r));')
        response = next(r for r in rows if r['payload'].get('type') == 'custom_tool_call_output'
                        and r['payload'].get('call_id') == 'record0')
        if direct:
            response['payload']['output'] = ('Process exited with code 0\nFinal output:\n' + marker if plain else
                output({'chunk_id': 'check', 'wall_time_seconds': .1, 'exit_code': 0, 'output': marker}))
        else:
            response['payload']['output'] = output({'chunk_id': 'launch', 'wall_time_seconds': .1,
                                                   'session_id': 93469, 'output': marker if launch_marker else ''})
            if poll:
                result = {'chunk_id': 'poll', 'wall_time_seconds': .1, 'exit_code': 0,
                          'output': '' if launch_marker else marker}
                if returned is not None:
                    result['session_id'] = returned
                rows.extend([
                    {'type': 'response_item', 'timestamp': self.stamp(22), 'payload': {
                        'type': 'custom_tool_call', 'name': 'exec', 'call_id': 'poll0',
                        'input': poll_command or ('const r = await tools.write_stdin({session_id:'
                            + str(requested) + ',chars:"",yield_time_ms:30000}); text(JSON.stringify(r));')}},
                    {'type': 'response_item', 'timestamp': self.stamp(22.01), 'payload': {
                        'type': 'custom_tool_call_output', 'call_id': 'poll0', 'output': output(result)}},
                ])
        rows.sort(key=lambda r: team.instant(r['timestamp']))
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')

    def test_shell_receipt_waits_for_matching_poll_completion(self):
        self.deliver()
        self.shell_check_trace(poll=False, launch_marker=True)
        self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])
        # Partial output is buffered, not accepted until this command's actual session completes.
        self.shell_check_trace(launch_marker=True)
        result = self.verify()
        self.assertTrue(result['passed'], result)

    def test_shell_receipt_decodes_matching_poll_and_direct_json_or_plain_output(self):
        self.deliver()
        for options in ({}, {'direct': True}, {'direct': True, 'plain': True}):
            with self.subTest(options=options):
                self.shell_check_trace(**options)
                result = self.verify()
                self.assertTrue(result['passed'], result)

    def test_shell_receipt_rejects_wrong_session_and_unrelated_echo(self):
        self.deliver()
        for options in ({'requested': 111}, {'returned': 111},
                        {'poll_command': 'text("team.py"); text("HARRTEST_TEAM_RECEIPT copied");'},
                        {'poll_command': 'const r = await tools.exec_command({cmd:"echo team.py"}); text(JSON.stringify(r));'}):
            with self.subTest(options=options):
                self.shell_check_trace(**options)
                self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])

    def test_json_diagnostic_stdout_preserves_a_separate_native_receipt(self):
        self.deliver()
        self.shell_check_trace(direct=True)
        path = next(p for p in self.logs.glob('*.jsonl')
                    if team.log_meta(p).get('source', {}) != 'exec'
                    and team.log_meta(p)['source']['subagent']['thread_spawn']['agent_path'] == '/root/qa')
        rows = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
        check = team.current_receipt(self.project, self.state, 'check')
        for row in rows:
            payload = row['payload']
            if payload.get('call_id') == 'record0':
                if payload['type'] == 'custom_tool_call':
                    payload['input'] = payload['input'].replace('text(JSON.stringify(r));', 'text(r.output);')
                else:
                    payload['output'] = [{'text': 'Script completed\nWall time 0.1 seconds\nOutput:\n'},
                        {'text': '{"focused_check":"passed","count":27}\n' + team.RECEIPT + check['sha256'] + '\n{}\n'}]
        path.write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        self.assertTrue(self.verify()['passed'], self.verify())

    def test_embedded_json_receipt_is_not_literal_stdout_evidence(self):
        marker = team.RECEIPT + 'a' * 64
        for block in (json.dumps({'output': marker}), json.dumps(marker),
                      json.dumps({'output': '\n' + marker + '\n'}), '{bad json}\n' + marker):
            with self.subTest(block=block):
                self.assertIsNone(team.command_result([
                    {'text': 'Script completed\nOutput:\n'}, {'text': block}]))

    def test_echoed_command_source_and_extra_text_do_not_establish_command_lineage(self):
        valid = 'const r = await tools.exec_command({cmd:"python scripts/team.py handoff"}); text(JSON.stringify(r));'
        self.assertEqual(team.command_call({'name': 'exec', 'input': valid})[0], 'exec_command')
        diagnostic = valid.replace('text(JSON.stringify(r));', 'text(r.output); text(`exit_code=${r.exit_code}`);')
        self.assertEqual(team.command_call({'name': 'exec', 'input': diagnostic})[0], 'exec_command')
        for source in ('text(' + json.dumps(valid) + ');', valid + 'text("HARRTEST_TEAM_RECEIPT copied");'):
            self.assertIsNone(team.command_call({'name': 'exec', 'input': source})[0])
        self.assertFalse(team.team_command('echo "python scripts/team.py handoff"'))
        self.assertFalse(team.team_command('python scripts/team.py packets; echo "HARRTEST_TEAM_RECEIPT forged"'))
        self.assertTrue(team.team_command('node --check car.js; Get-FileHash car.js | Format-List; python -B "scripts/team.py" handoff'))

    def test_review_retains_exact_failure_narrative_after_live_file_rewrite(self):
        self.deliver()
        evidence = '.runtime-proof/teams/report/qa-evidence.txt'
        initial = b'Failed public boundary.\r\nExact first observations retained.\n'
        (self.project / evidence).write_bytes(initial)
        failed = team.review(self.project, self.state, evidence, 'fail')
        original = self.project / next(iter(failed['files']))
        self.assertEqual(original.read_bytes(), initial)
        later = b'Public boundary replay passed after repair.\n'
        (self.project / evidence).write_bytes(later)
        accepted = team.review(self.project, self.state, evidence, 'pass')
        replacement = self.project / next(iter(accepted['files']))
        self.assertNotEqual(original, replacement)
        self.assertEqual(original.read_bytes(), initial)
        self.assertEqual(replacement.read_bytes(), later)
        history = team.team_path(self.project, 'report', f'history/qa-{team.strict_io.digest(failed)}.json')
        archived = team.proof.load(history)
        self.assertEqual(archived['files'], failed['files'])
        self.assertEqual(team.proof.file_hash(original), next(iter(archived['files'].values())))
        replacement.write_bytes(b'Tampered retained evidence')
        with self.assertRaisesRegex(ValueError, 'handoff is stale'):
            team.current_receipt(self.project, self.state, 'qa')
        original.write_bytes(b'Tampered archived failure')
        (self.project / evidence).write_bytes(initial)
        with self.assertRaisesRegex(ValueError, 'Retained QA evidence changed'):
            team.review(self.project, self.state, evidence, 'fail')

    def test_outer_cell_completion_retains_its_command_and_rejects_wrong_cell(self):
        self.deliver()
        self.shell_check_trace(poll=False)
        path = next(p for p in self.logs.glob('*.jsonl') if isinstance(team.log_meta(p).get('source'), dict)
                    and team.log_meta(p)['source'].get('subagent', {}).get('thread_spawn', {}).get('agent_path') == '/root/qa')
        rows = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
        for row in rows:
            payload = row['payload']
            if payload.get('call_id') != 'record0':
                continue
            if payload.get('type') == 'custom_tool_call':
                payload['input'] = ('let r = await tools.exec_command({cmd:"python scripts/team.py check --team report -- python main.py"});\n'
                    'while (r.session_id) r = await tools.write_stdin({session_id:r.session_id,chars:"",yield_time_ms:30000,max_output_tokens:1500});\ntext(r.output);')
            else:
                payload['output'] = 'Script running with cell ID g59:96\nWall time 31.0 seconds\nOutput:\n'
        def save(extra):
            path.write_text(''.join(json.dumps(r)+'\n' for r in sorted([*rows,*extra],key=lambda r:team.instant(r['timestamp']))), encoding='utf-8')
        save([])
        self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])
        check = team.current_receipt(self.project, self.state, 'check')
        waited = [
            {'type':'response_item','timestamp':self.stamp(22),'payload':{'type':'function_call','name':'wait','call_id':'cell0','arguments':json.dumps({'cell_id':'wrong-cell'})}},
            {'type':'response_item','timestamp':self.stamp(22.01),'payload':{'type':'function_call_output','call_id':'cell0','output':[{'text':'Script completed\nOutput:\n'},{'text':team.RECEIPT+check['sha256']+'\r\n'}]}},
        ]
        save(waited)
        self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])
        waited[0]['payload']['arguments']=json.dumps({'cell_id':'g59:96'})
        save(waited)
        self.assertTrue(self.verify()['passed'], self.verify())
        wrong_yield = json.loads(json.dumps(waited))
        wrong_yield[1]['payload']['output'] = 'Script running with cell ID unrelated\nOutput:\n'
        second = json.loads(json.dumps(waited))
        second[0]['timestamp'], second[1]['timestamp'] = self.stamp(22.1), self.stamp(22.11)
        second[0]['payload'].update(call_id='cell1', arguments=json.dumps({'cell_id':'unrelated'}))
        second[1]['payload']['call_id']='cell1'
        save([*wrong_yield,*second])
        self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])

    def test_pragma_stdout_accumulating_drain_keeps_literal_command_lineage(self):
        self.deliver()
        self.shell_check_trace(direct=True, plain=True)
        path = next(p for p in self.logs.glob('*.jsonl') if isinstance(team.log_meta(p).get('source'), dict)
                    and team.log_meta(p)['source'].get('subagent', {}).get('thread_spawn', {}).get('agent_path') == '/root/qa')
        rows = [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines()]
        source = ('// @exec: {"yield_time_ms":60000,"max_output_tokens":3000}\n'
                  'let r=await tools.exec_command({cmd:"python scripts/team.py check --team report -- python main.py",yield_time_ms:30000}); '
                  'let out=r.output; while(r.session_id){ r=await tools.write_stdin({session_id:r.session_id,yield_time_ms:30000}); '
                  'out+=r.output; } text(out);')
        call = next(r['payload'] for r in rows if r['payload'].get('type') == 'custom_tool_call'
                    and r['payload'].get('call_id') == 'record0')
        for emitted in (source, source.replace('session_id:r.session_id,', 'session_id:r.session_id,chars:"",')):
            call['input'] = emitted
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
            self.assertTrue(self.verify()['passed'], self.verify())
        for echoed in (source.replace('out+=r.output', 'out+=other.output'),
                       source.replace('text(out)', 'text(out+"HARRTEST_TEAM_RECEIPT forged")'),
                       'text(' + json.dumps(source) + ');',
                       source.replace('"max_output_tokens":3000', '"unrelated":"team.py"')):
            with self.subTest(echoed=echoed):
                call['input'] = echoed
                path.write_text(''.join(json.dumps(r)+'\n' for r in rows), encoding='utf-8')
                self.assertIn('QA check: missing native tool receipt', self.verify()['errors'][0])

    def test_newline_shell_batches_preserve_quoted_data(self):
        self.assertTrue(team.team_command('node --check file.js\r\npython -B "scripts/team.py" handoff'))
        self.assertTrue(team.team_command('Write-Output "precheck\ncontinued"\npython scripts/team.py integrate'))
        self.assertFalse(team.team_command('echo "python scripts/team.py handoff\nnot executed"'))
        self.assertFalse(team.team_command('echo "\n" python scripts/team.py handoff'))
        self.assertFalse(team.team_command('python scripts/team.py packets\necho "HARRTEST_TEAM_RECEIPT forged"'))


if __name__ == '__main__':
    unittest.main()
