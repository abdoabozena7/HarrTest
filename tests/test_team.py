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
                      'input': 'python scripts/team.py handoff', 'call_id': call}),
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


if __name__ == '__main__':
    unittest.main()
