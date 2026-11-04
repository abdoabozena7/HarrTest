"""Actual SQLite transactions, crash/reopen, resource claims, and effect reconciliation."""
import copy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from runtime_store import Store, RuntimeErrorState


def spec():
    return {'schema': 1, 'goal_id': 'goal', 'root_goal': '.runtime-proof/root-goals/goal', 'tasks': [
        {'id': 'left', 'proof_task': '.runtime-proof/left', 'outcome': 'Implement and verify left', 'depends_on': [], 'write_scope': ['src/left.py']},
        {'id': 'right', 'proof_task': '.runtime-proof/right', 'outcome': 'Implement and verify right', 'depends_on': [], 'write_scope': ['src/right.py']},
        {'id': 'join', 'proof_task': '.runtime-proof/join', 'role': 'integrate', 'outcome': 'Run full integration', 'depends_on': ['left', 'right'], 'write_scope': []}]}


EVIDENCE = {'path': '.runtime-proof/observed.log', 'sha256': 'a' * 64}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.path = Path(self.tmp.name) / 'workflows.sqlite'
        self.t = 100.; self.s = Store(self.path, clock=lambda: self.t); self.plan = spec(); self.s.create(self.plan)
    def tearDown(self): self.tmp.cleanup()
    def claim(self, task='left', seconds=10): return self.s.claim('goal', task, 'real-host-worker', seconds)
    def test_idempotent_create_and_changed_plan_rejected(self):
        self.assertFalse(self.s.create(self.plan))
        changed = copy.deepcopy(self.plan); changed['tasks'][0]['outcome'] = 'silently replaced outcome'
        with self.assertRaises(RuntimeErrorState): self.s.create(changed)
    def test_dependencies_block_until_both_deliver(self):
        with self.assertRaises(RuntimeErrorState): self.claim('join')
        for tid in ('left','right'):
            c=self.claim(tid);self.s.handoff('goal',tid,c['token'],EVIDENCE)
        self.assertEqual(self.claim('join')['task'], 'join')
    def test_parallel_distinct_files(self):
        self.claim('left');self.claim('right')
        self.assertEqual(sum(r['state']=='RUNNING' for r in self.s.inspect('goal')),2)
    def test_overlapping_scope_prevents_claim(self):
        plan=spec();plan['goal_id']='other';plan['tasks'][0]['write_scope']=['src']
        self.s.create(plan);self.claim()
        with self.assertRaisesRegex(RuntimeErrorState,'conflict'):self.s.claim('other','left','worker',10)
    def test_read_write_conflict(self):
        plan=spec();plan['goal_id']='other';plan['tasks'][0]['write_scope']=[];plan['tasks'][0]['read_scope']=['src/left.py']
        self.s.create(plan);self.claim()
        with self.assertRaisesRegex(RuntimeErrorState,'conflict'):self.s.claim('other','left','worker',10)
    def test_exclusive_gpu_resource(self):
        plan=spec();plan['goal_id']='gpu';plan['tasks'][0]['resources']=['gpu:0'];plan['tasks'][1]['resources']=['gpu:0']
        self.s.create(plan);self.s.claim('gpu','left','worker-one',10)
        with self.assertRaisesRegex(RuntimeErrorState,'conflict'):self.s.claim('gpu','right','worker-two',10)
    def test_expired_worker_cannot_handoff(self):
        c=self.claim();self.t=111
        with self.assertRaisesRegex(RuntimeErrorState,'expired'):self.s.handoff('goal','left',c['token'],EVIDENCE)
    def test_recovery_invalidates_old_tokens(self):
        c=self.claim();self.t=111;self.s.recover('goal','left',EVIDENCE);new=self.claim()
        self.assertGreater(new['generation'],c['generation'])
        with self.assertRaisesRegex(RuntimeErrorState,'Stale'):self.s.handoff('goal','left',c['token'],EVIDENCE)
    def test_expired_lock_not_automatically_stolen(self):
        self.claim();self.t=111
        with self.assertRaises(RuntimeErrorState):self.claim()
    def test_heartbeat_renews_live_lease_only(self):
        c=self.claim();self.t=108;self.s.heartbeat('goal','left',c['token'],10);self.t=115
        self.s.handoff('goal','left',c['token'],EVIDENCE)
    def test_reopen_preserves_running_work(self):
        c=self.claim();other=Store(self.path,clock=lambda:self.t)
        with self.assertRaises(RuntimeErrorState):other.claim('goal','left','other-worker',10)
        other.handoff('goal','left',c['token'],EVIDENCE)
        self.assertEqual(next(row for row in self.s.inspect('goal') if row['id']=='left')['state'],'IMPLEMENTED')
    def test_unknown_effect_never_blindly_reexecutes(self):
        c=self.claim();self.assertTrue(self.s.operation('goal','left',c['token'],'send-once','a'*64)['execute'])
        other=Store(self.path,clock=lambda:self.t)
        self.assertFalse(other.operation('goal','left',c['token'],'send-once','a'*64)['execute'])
        with self.assertRaises(RuntimeErrorState):other.handoff('goal','left',c['token'],EVIDENCE)
    def test_effect_reconciliation_allows_handoff_not_reexecution(self):
        c=self.claim();self.s.operation('goal','left',c['token'],'send-once','a'*64)
        self.s.reconcile('send-once','OBSERVED_DONE',EVIDENCE)
        self.assertFalse(self.s.operation('goal','left',c['token'],'send-once','a'*64)['execute'])
        self.s.handoff('goal','left',c['token'],EVIDENCE)
    def test_unknown_effect_blocks_recovery(self):
        c=self.claim();self.s.operation('goal','left',c['token'],'send-once','a'*64);self.t=111
        with self.assertRaisesRegex(RuntimeErrorState,'Unknown'):self.s.recover('goal','left',EVIDENCE)
    def test_same_key_different_inputs_rejected(self):
        c=self.claim();self.s.operation('goal','left',c['token'],'send-once','a'*64)
        with self.assertRaises(RuntimeErrorState):self.s.operation('goal','left',c['token'],'send-once','b'*64)
    def test_direct_done_does_not_exist(self):
        with self.assertRaises(RuntimeErrorState):self.s.verify('goal','left',lambda n:{'passed':True})
    def test_failed_fresh_verification_reopens_state(self):
        c=self.claim();self.s.handoff('goal','left',c['token'],EVIDENCE)
        self.s.verify('goal','left',lambda n:{'passed':True})
        self.s.verify('goal','left',lambda n:{'passed':False,'reason':'new source changed'})
        self.assertEqual(next(row for row in self.s.inspect('goal') if row['id']=='left')['state'],'IMPLEMENTED')
    def test_typed_verdict_required(self):
        c=self.claim();self.s.handoff('goal','left',c['token'],EVIDENCE)
        with self.assertRaises(RuntimeErrorState):self.s.verify('goal','left',lambda n:{'passed':'true'})
    def test_event_chain_reopens_and_is_append_only(self):
        self.claim();self.assertEqual(len(Store(self.path).audit()),2)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM events')
    def test_concurrent_claim_one_winner(self):
        def take(i):
            try:return Store(self.path,clock=lambda:100).claim('goal','left',f'worker-{i}',10)['task']
            except RuntimeErrorState:return None
        with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(take,range(4)))
        self.assertEqual(result.count('left'),1)
    def test_negative_lease_and_nonfinite_rejected(self):
        for value in (-1,0,float('inf'),float('nan'),True):
            with self.assertRaises(RuntimeErrorState):self.claim(seconds=value)
    def test_dependency_cycle_fails_before_creation(self):
        s=spec();s['tasks'][0]['depends_on']=['join']
        with self.assertRaises(RuntimeErrorState):Store.validate(s)
    def test_wildcard_path_not_silently_mislocked(self):
        s=spec();s['tasks'][0]['write_scope']=['src/*.py']
        with self.assertRaises(ValueError):Store.validate(s)


if __name__=='__main__':unittest.main()
