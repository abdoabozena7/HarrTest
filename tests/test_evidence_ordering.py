"""Real collector subprocess races; barriers control completion, never source edits.

The fixture is an executable CLI, not an agent/model performance benchmark.
"""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import proof
import root_gate
import builder


CONTROLLED_CLI = '''import json
import os
from pathlib import Path
import time
run = Path(os.environ['PROVE_IT_OUTPUT_DIR'])
(run / 'ready').write_text(str(os.getpid()), encoding='utf-8')
deadline = time.monotonic() + 20
while not (run / 'release.json').exists():
    if time.monotonic() > deadline:
        raise SystemExit('Test controller did not release command')
    time.sleep(0.01)
value = json.loads((run / 'release.json').read_text(encoding='utf-8'))
try:
    os.write(1, (json.dumps(value) + '\\n').encode('utf-8'))
except OSError:
    pass  # A killed collector must not leave a fixture process running.
(run / 'finished').write_text('actual command exited', encoding='utf-8')
'''


class EvidenceOrderingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='harrtest-order-')
        self.project = Path(self.temp.name)
        self.task = self.project / '.runtime-proof/cli-demo'
        self.task.mkdir(parents=True)
        (self.project / 'demo_cli.py').write_text(CONTROLLED_CLI, encoding='utf-8')
        self.contract = proof.load(ROOT / 'examples/cli-contract.json')
        self.contract['checks'][0]['timeout_seconds'] = 25
        self.processes = []
        self.owned_tasks = set()
        self.seal()

    def tearDown(self):
        self.cleanup_processes()
        self.temp.cleanup()

    def cleanup_processes(self):
        # Release owned commands even when an assertion fails; kill only collectors
        # this test launched. Fixture commands also have a finite health timeout.
        runs = {run for proc, run in self.processes if run is not None}
        # A collector may fail before start() has observed its pointer. All of
        # these task trees are exclusive disposable fixtures owned by this test.
        for task in self.owned_tasks:
            runs.update(path.parent for path in task.glob('runs/*/*/started.json'))
        for run in runs:
            proof.save(run / 'release.json', {'sum': 12})
        for proc, run in self.processes:
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate(timeout=5)
        for run in runs:
            if (run / 'ready').exists():
                self.wait_for(lambda: (run / 'finished').exists(), 'owned command cleanup')
        self.processes.clear()

    def seal(self):
        proof.save(self.task / 'context.json', {'project': str(self.project)})
        proof.save(self.task / 'contract.json', self.contract)
        proof.save(self.task / 'seal.json', {'contract_hash': proof.digest(self.contract),
                                            'engine_hash': proof.engine_hash(self.contract)})

    def wait_for(self, condition, label, proc=None):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            value = condition()
            if value:
                return value
            if proc is not None and proc.poll() is not None:
                out, err = proc.communicate()
                self.fail(f'Collector stopped before {label}: {out}\n{err}')
            time.sleep(0.01)
        self.fail('Timed out waiting for ' + label)

    def latest(self, check='addition'):
        # Avoid a Windows read handle racing atomic replacement. Production
        # verification already fails closed on unreadable evidence; the test's
        # polling must not interfere with the collector it is observing.
        with proof.latest_guard(self.task):
            return proof.load(self.task / 'latest' / (check + '.json'))

    def start(self, check='addition'):
        self.owned_tasks.add(self.task)
        marker = self.task / 'latest' / (check + '.json')
        previous = self.latest(check)['run'] if marker.exists() else None
        proc = subprocess.Popen([sys.executable, '-B', str(ROOT / 'scripts/proof.py'),
                                 'run', '--task', str(self.task), '--check', check],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.processes.append((proc, None))
        def admitted():
            if not marker.exists():
                return None
            latest = self.latest(check)
            if latest['run'] != previous:
                return self.task / latest['run']
        run = self.wait_for(admitted, 'new admission marker', proc)
        self.processes[-1] = (proc, run)
        self.wait_for(lambda: (run / 'ready').exists(), 'actual command entrypoint', proc)
        return proc, run

    def finish(self, attempt, value):
        proc, run = attempt
        proof.save(run / 'release.json', {'sum': value})
        out, err = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 0 if value == 12 else 1, (out, err))
        receipt = proof.load(run / 'receipt.json')
        self.assertEqual(receipt['passed'], value == 12)
        return receipt

    def verify_step(self):
        proof.update_step(self.task, 'T01', 'VERIFIED',
                          'Inspected actual subprocess JSON and independent numeric expectation.')
        return proof.verify(self.task)

    def test_older_pass_cannot_hide_newer_failure(self):
        older = self.start()
        newer = self.start()
        self.finish(newer, 13)
        self.finish(older, 12)
        self.assertEqual(self.latest()['run'], newer[1].relative_to(self.task).as_posix())
        self.assertFalse(proof.verify(self.task, include_plan=False)['passed'])
        with self.assertRaises(proof.ProofError):
            self.verify_step()
        self.assertTrue((older[1] / 'receipt.json').is_file())
        self.assertTrue((newer[1] / 'receipt.json').is_file())

    def test_older_failure_does_not_hide_newer_pass(self):
        older = self.start()
        newer = self.start()
        self.finish(newer, 12)
        self.finish(older, 13)
        self.assertEqual(self.latest()['run'], newer[1].relative_to(self.task).as_posix())
        self.assertTrue(self.verify_step()['passed'])

    def test_interrupted_newer_attempt_blocks_until_actual_restart(self):
        older = self.start()
        newer = self.start()
        newer[0].kill()
        newer[0].communicate(timeout=5)
        proof.save(newer[1] / 'release.json', {'sum': 12})
        self.wait_for(lambda: (newer[1] / 'finished').exists(), 'interrupted command exit')
        self.finish(older, 12)
        self.assertEqual(self.latest()['run'], newer[1].relative_to(self.task).as_posix())
        self.assertIsNone(self.latest()['receipt_hash'])
        self.assertFalse(proof.verify(self.task, include_plan=False)['passed'])
        restarted = self.start()
        self.finish(restarted, 12)
        self.assertTrue(self.verify_step()['passed'])
        self.assertTrue((newer[1] / 'started.json').is_file())
        self.assertFalse((newer[1] / 'receipt.json').exists())
        self.assertTrue((older[1] / 'receipt.json').is_file())

    def test_three_overlaps_use_admission_order_not_finish_order(self):
        attempts = [self.start() for _ in range(3)]
        for attempt, result in zip(reversed(attempts), (13, 12, 12)):
            self.finish(attempt, result)
        self.assertEqual(self.latest()['run'], attempts[-1][1].relative_to(self.task).as_posix())
        self.assertFalse(proof.verify(self.task, include_plan=False)['passed'])
        self.assertEqual(len(list((self.task / 'runs/addition').glob('*/receipt.json'))), 3)

    def test_separate_checks_execute_while_another_command_is_pending(self):
        second = copy.deepcopy(self.contract['checks'][0])
        second['id'] = 'independent'
        self.contract['checks'].append(second)
        self.contract['requirements'][0]['checks'].append('independent')
        self.contract['plan']['tasks'][0]['checks'].append('independent')
        self.seal()
        first = self.start()
        other = self.start('independent')
        self.finish(other, 12)
        self.assertIsNone(first[0].poll())
        self.finish(first, 12)
        self.assertTrue(self.verify_step()['passed'])
        self.assertNotEqual(self.latest()['run'], self.latest('independent')['run'])

    def test_new_failure_reaches_root_workflow_and_builder(self):
        # Real sealed root + two already proven children. Inject overlap only in
        # final integration; use existing public controllers with the new evidence.
        import test_builder
        fixture = test_builder.BuilderTests()
        fixture.setUp()
        try:
            fixture.deliver('slice')
            fixture.deliver('delivery')
            self.assertTrue(fixture.gate('M2')['root_goal_achieved'])
            self.project = fixture.project
            self.task = self.project / '.runtime-proof/integration'
            self.contract = proof.load(self.task / 'contract.json')
            # A deliberate source change requires fresh proof. It cannot change
            # contracts or the root, and is captured by both actual new receipts.
            (self.project / 'demo_cli.py').write_text(CONTROLLED_CLI, encoding='utf-8')
            integration = self.task
            # Refresh the predecessor too: root rejection must come from the
            # newest failed integration, never unrelated stale slice evidence.
            for child in ('smoke', 'integration'):
                self.task = self.project / '.runtime-proof' / child
                current = self.start()
                self.finish(current, 12)
                self.assertTrue(self.verify_step()['passed'])
            self.task = integration
            self.assertTrue(fixture.gate('M2')['root_goal_achieved'])
            older = self.start()
            newer = self.start()
            self.finish(newer, 13)
            self.finish(older, 12)
            with self.assertRaises(proof.ProofError):
                self.verify_step()
            self.assertFalse(root_gate.check_root(fixture.fixture.goal)['root_goal_achieved'])
            result = fixture.store.verify('mission', 'delivery',
                lambda node: proof.verify(self.project / node['proof_task']))
            self.assertFalse(result['passed'])
            self.assertFalse(fixture.gate('M2')['root_goal_achieved'])
            self.assertNotEqual(builder.next_action(self.project, fixture.store, fixture.saved,
                                                   fixture.shape)['action'], 'DELIVER')
            command = [sys.executable, '-B', str(ROOT / 'scripts/workflow.py'), '--project',
                       str(self.project), 'root', '--goal', 'mission']
            rejected = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(rejected.returncode, 1, rejected.stdout + rejected.stderr)
            repaired = self.start()
            self.finish(repaired, 12)
            self.assertTrue(self.verify_step()['passed'])
            self.assertTrue(fixture.gate('M2')['root_goal_achieved'])
            accepted = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        finally:
            self.cleanup_processes()
            fixture.tearDown()

    def test_comparison_and_admission_share_cross_process_critical_section(self):
        attempt = self.start()
        self.finish(attempt, 12)
        pointer = self.task / 'latest/addition.json'
        receipt_hash = self.latest()['receipt_hash']
        ready, release = self.project / 'comparing', self.project / 'unlock'
        # Pause an actual publishing process immediately before it compares the
        # pointer. An admission must fail closed on a short lock health timeout,
        # proving the comparison itself is inside the shared critical section.
        code = '''import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import proof
task, run, ready, release = map(Path, sys.argv[2:6])
original = proof.load
def paused_load(path):
    if path == task / 'latest/addition.json':
        ready.write_text('inside comparison')
        deadline = time.monotonic() + 20
        while not release.exists():
            if time.monotonic() > deadline: raise TimeoutError('test release missing')
            time.sleep(.01)
    return original(path)
proof.load = paused_load
assert proof.publish_latest(task, 'addition', run, sys.argv[6])
'''
        actor = subprocess.Popen([sys.executable, '-B', '-c', code, str(ROOT / 'scripts'),
                                  str(self.task), str(attempt[1]), str(ready), str(release), receipt_hash],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(ready.exists, 'locked comparison', actor)
            contender = '''import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import proof
original = proof.sqlite3.connect
def short_timeout(*args, **kwargs):
    kwargs['timeout'] = .1
    return original(*args, **kwargs)
proof.sqlite3.connect = short_timeout
try:
    proof.publish_latest(Path(sys.argv[2]), 'addition', Path(sys.argv[3]))
except proof.ProofError as exc:
    assert 'Cannot coordinate' in str(exc)
    print('LOCKED_OUT')
else:
    raise AssertionError('Admission raced inside another publication comparison')
'''
            next_run = self.task / 'runs/addition/next-admission'
            result = subprocess.run([sys.executable, '-B', '-c', contender, str(ROOT / 'scripts'),
                                     str(self.task), str(next_run)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('LOCKED_OUT', result.stdout)
            self.assertEqual(proof.load(pointer)['receipt_hash'], receipt_hash)
        finally:
            release.touch()
            try:
                out, err = actor.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                actor.kill(); actor.communicate(timeout=5)
                raise
        self.assertEqual(actor.returncode, 0, out + err)
        self.assertTrue(proof.publish_latest(self.task, 'addition', next_run))
        self.assertIsNone(self.latest()['receipt_hash'])

    def test_killed_lock_owner_does_not_require_stale_lock_deletion(self):
        ready = self.project / 'lock-held'
        code = '''import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import proof
with proof.latest_guard(Path(sys.argv[2])):
    Path(sys.argv[3]).write_text('locked')
    time.sleep(20)
'''
        actor = subprocess.Popen([sys.executable, '-B', '-c', code, str(ROOT / 'scripts'),
                                  str(self.task), str(ready)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.wait_for(ready.exists, 'owned publication lock', actor)
        finally:
            actor.kill(); actor.communicate(timeout=5)
        self.assertTrue((self.task / '.latest-lock.sqlite').exists())
        attempt = self.start()
        self.finish(attempt, 12)
        self.assertTrue(self.verify_step()['passed'])

    def test_invalid_lock_database_never_runs_command_or_falls_back(self):
        (self.task / '.latest-lock.sqlite').write_text('not a SQLite database', encoding='utf-8')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/proof.py'),
                                 'run', '--task', str(self.task), '--check', 'addition'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Cannot coordinate latest evidence publication', result.stderr)
        self.assertEqual(list((self.task / 'runs').glob('*/*/ready')), [])
        self.assertFalse(proof.verify(self.task)['passed'])


if __name__ == '__main__':
    unittest.main()
