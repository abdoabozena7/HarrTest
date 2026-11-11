"""Real CLI and SQLite checks with deterministic, labelled host/measurement fixtures."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import golden
from golden_benchmark import CASES, EVIDENCE, GOAL, Trial, reference, save
import strict_io


def now():
    return datetime.now(timezone.utc).isoformat()


class GoldenWorkflow(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.project = Path(temp.name).resolve() / 'project'
        self.protocol = {
            'schema': 1, 'mode': 'fixture',
            'controls': {'runner': 'Identical command-line fixtures', 'environment': 'Isolated temporary project'},
            'baseline': {'id': 'baseline-fixture', 'source_sha256': 'a' * 64},
            'cases': [
                {'id': 'actual-execution', 'expect': 'accept', 'oracle': 'Actual checks match literal outputs.'},
                {'id': 'unverified-work', 'expect': 'reject', 'oracle': 'Reject work without a numeric comparison.'},
            ],
            'thresholds': {'min_candidate_correct': 2, 'max_candidate_false_accepts': 0, 'min_correct_gain': 1},
        }
        self.trial = Trial(self.project, ROOT, self.protocol)
        self.trial.setup()
        self.assert_exit(self.trial.initialize(CASES[0]))

    def assert_exit(self, entry, code=0, reason=None):
        output = entry['stdout'] + entry['stderr']
        self.assertEqual(entry['exit_code'], code, output)
        if reason:
            self.assertIn(reason, output)

    def claim(self, node, worker=None):
        entry, lease = self.trial.claim(node, worker or f'fixture-{node}-worker')
        self.assert_exit(entry)
        self.assertNotIn('original_request', lease['packet'])
        self.assertEqual(strict_io.digest(lease['packet']), lease['packet_sha256'])
        self.assertEqual(lease['packet']['task']['id'], node)
        return lease

    def invoke(self, command, node, *args):
        return self.trial.workflow(command, '--goal', 'mission', '--task', node, *args)[0]

    def handoff(self, lease, *, finish=None, host_worker=None):
        node = lease['task']
        trace = self.project / EVIDENCE / f'{node}-{lease["generation"]}-trace.json'
        decision = trace.with_name(f'{node}-{lease["generation"]}-decision.txt')
        decision.write_text('Fixture observed the exact signed integer results required by the CLI.\n', encoding='utf-8')
        record = {'task_id': node, 'generation': lease['generation'], 'worker_id': lease['owner'],
                  'packet_sha256': lease['packet_sha256'],
                  'observations': {'addition': {'expected': 'The CLI emits the independently expected integer result.',
                                                'observed': 'The runtime subprocess emitted the expected JSON result.'}},
                  'decisions': []}
        if node in {'sum', 'product'}:
            record['decisions'].append({
                'id': 'integer-exactness', 'choice': 'Preserve exact signed integer arithmetic.',
                'rationale': 'The runtime exercises the documented integer behavior.',
                'evidence': [reference(self.project, decision)],
            })
        if node != 'integration':
            native = {'invocation_id': f'fixture-invocation-{node}-{lease["generation"]}',
                      'started_at': lease['started_at'], 'finished_at': finish or now()}
            save(trace, {**native, 'worker_id': host_worker or lease['owner'], 'mode': 'synthetic host trace fixture',
                         'packet_sha256': lease['packet_sha256']})
            record.update(native, trace=trace.relative_to(self.project).as_posix())
            if host_worker:
                record['host_worker_id'] = host_worker
        manifest = trace.with_name(f'{node}-{lease["generation"]}-handoff.json')
        save(manifest, record)
        return self.invoke('handoff', node, '--token', lease['token'], '--evidence',
                           manifest.relative_to(self.project).as_posix())

    def verify(self, node):
        self.trial.mark_verified(node)
        self.assert_exit(self.invoke('verify', node))

    def comparison(self, *, passing):
        actual = golden.source_identity(self.project, self.trial.plan)
        attempts = []
        for case in self.protocol['cases']:
            for arm in ('baseline', 'candidate'):
                path = self.project / EVIDENCE / f'{case["id"]}-{arm}-fixture.json'
                outcome = case['expect'] if arm == 'candidate' and passing else 'accept'
                observation = {'case': case['id'], 'variant': arm, 'outcome': outcome,
                               'source_sha256': actual if arm == 'candidate' else 'a' * 64}
                raw = path.with_suffix('.txt')
                raw.write_text(f'Synthetic comparison input: {observation}\n', encoding='utf-8')
                save(path, {'schema': 1, **observation, 'artifacts': [reference(self.project, raw)]})
                attempts.append({**observation, 'evidence': reference(self.project, path)})
        save(self.project / self.trial.plan['golden']['measurement'], {
            'schema': 1, 'protocol_sha256': strict_io.digest(self.protocol),
            'candidate': {'id': 'candidate-fixture', 'source_sha256': actual}, 'attempts': attempts,
        })

    def test_independent_checks_and_comparison_enforce_original_root(self):
        left = self.claim('sum')
        right = self.claim('product')
        with ThreadPoolExecutor(max_workers=2) as pool:
            for result in pool.map(self.trial.run_check, (left, right)):
                self.assert_exit(result)
        finish = now()
        for lease in (left, right):
            self.assert_exit(self.handoff(lease, finish=finish))
            self.verify(lease['task'])

        source = self.project / 'addition.py'
        valid = source.read_bytes()
        source.write_bytes(valid + b'\n# Source changed after handoff\n')
        _, readiness = self.trial.workflow('ready', '--goal', 'mission')
        self.assertNotIn('qa', {row['id'] for row in readiness['tasks']})
        source.write_bytes(valid)
        same_worker, _ = self.trial.claim('qa', left['owner'])
        self.assert_exit(same_worker, 2, 'different host worker')
        qa = self.claim('qa')
        self.assertEqual(set(qa['packet']['dependency_evidence']), {'sum', 'product'})
        busy_retry = self.invoke('retry', 'sum', '--evidence', 'behavior-contract.txt')
        self.assert_exit(busy_retry, 2, 'reconcile all affected running work')
        out_of_band, _ = self.trial.command('proof.py', 'run', '--task', '.runtime-proof/qa', '--check', 'addition')
        self.assert_exit(out_of_band)
        self.assert_exit(self.handoff(qa), 2, 'must be run under this Golden worker lease')
        self.assert_exit(self.trial.run_check(qa))
        self.assert_exit(self.handoff(qa, host_worker=left['owner']), 2, 'cannot reuse the reviewed implementer')
        self.assert_exit(self.handoff(qa))
        self.verify('qa')

        integration = self.claim('integration')
        self.assert_exit(self.trial.run_check(integration))
        self.assert_exit(self.handoff(integration))
        self.verify('integration')

        direct, _ = self.trial.command('root_gate.py', 'verify', '--goal', GOAL)
        self.assert_exit(direct, 1, 'Missing scoped path')
        self.comparison(passing=False)
        refused, _ = self.trial.workflow('root', '--goal', 'mission')
        self.assert_exit(refused, 1, 'missed its sealed numeric thresholds')
        self.comparison(passing=True)
        approved, result = self.trial.workflow('root', '--goal', 'mission')
        self.assert_exit(approved)
        self.assertTrue(result['root_goal_achieved'])
        self.assertGreater(result['golden']['recorded_implementation_overlap']['seconds'], 0)
        self.assertEqual(result['golden']['measurement']['correct_gain_points'], 50)
        self.assertEqual(result['golden']['measurement']['mode'], 'fixture')

        decision = self.project / EVIDENCE / 'sum-1-decision.txt'
        decision.write_text('The cited material decision artifact changed.', encoding='utf-8')
        stale, _ = self.trial.command('root_gate.py', 'verify', '--goal', GOAL)
        self.assert_exit(stale, 1, 'decision evidence: evidence changed')
        failure = decision.relative_to(self.project).as_posix()
        reopened = self.invoke('retry', 'sum', '--evidence', failure)
        self.assert_exit(reopened)
        self.assertEqual(strict_io.loads(reopened['stdout'])['tasks'], ['integration', 'qa', 'sum'])
        replacement = self.claim('sum')
        self.assertEqual(replacement['generation'], 2)
        stale_run = self.invoke('run-check', 'sum', '--check', 'addition', '--token', left['token'])
        self.assert_exit(stale_run, 2, 'Stale or foreign worker token')


if __name__ == '__main__':
    unittest.main()
