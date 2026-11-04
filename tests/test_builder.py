"""Milestone controls on actual proof fixtures; not a live-model benchmark."""
import contextlib
import copy
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import builder
import proof
import strict_io
from runtime_store import Store
import test_root_gate


def plan():
    return {'schema': 1, 'goal_id': 'mission', 'root_goal': '.runtime-proof/root-goals/mission',
            'tasks': [
                {'id': 'slice', 'role': 'integrate', 'outcome': 'Runnable actual command', 'proof_task': '.runtime-proof/smoke',
                 'depends_on': [], 'write_scope': ['demo_cli.py']},
                {'id': 'delivery', 'role': 'integrate', 'outcome': 'Final full public integration', 'proof_task': '.runtime-proof/integration',
                 'depends_on': ['slice'], 'write_scope': []}],
            'build': {'mode': 'greenfield',
                'architecture': {'runtime': 'local Python', 'selected_stack': 'standard-library CLI',
                    'rationale': 'No external service is required for this narrow example.',
                    'deliverable': 'Runnable command verified from its public interface',
                    'constraints': ['No new model provider or paid service'],
                    'alternatives': [{'option': 'External web service', 'tradeoff': 'Extra dependency not needed for the task'}]},
                'host': {'delegation_available': False, 'stronger_model_available': False,
                         'evidence': 'Local deterministic test process, no model or delegation tools', 'max_parallel_workers': 1},
                'interfaces': [],
                'risks': [{'failure': 'A command may print a label instead of correct result',
                           'probe': 'Compare actual parsed numeric result', 'milestone': 'M1'}],
                'milestones': [
                    {'id': 'M1', 'kind': 'vertical_slice', 'outcome': 'Actual public command works',
                     'tasks': ['slice'], 'requirements': ['ROOT01'], 'depends_on': [], 'integration_task': 'slice'},
                    {'id': 'M2', 'kind': 'delivery', 'outcome': 'Full integrated behavior verified',
                     'tasks': ['delivery'], 'requirements': ['ROOT02'], 'depends_on': ['M1'], 'integration_task': 'delivery'}]}}


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_root_gate.RootGateTests(); self.fixture.setUp()
        self.project = self.fixture.project
        self.private = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'HARRTEST_STATE_HOME': self.private.name}); self.env.start()
        self.fixture.child('smoke'); self.fixture.child('integration')
        self.spec = plan(); builder.register(self.project, self.spec)
        self.reload()
    def tearDown(self):
        self.env.stop(); self.private.cleanup(); self.fixture.tearDown()
    def reload(self):
        self.store, self.saved, self.shape = builder.open_build(self.project, 'mission')
    def deliver(self, tid):
        claim = builder.claim(self.project, self.store, self.saved, self.shape, tid, 'actual-local-process', 120)
        path = self.project / '.runtime-proof' / (tid + '-handoff.txt')
        path.write_text('Actual fixture subprocess and checked expected arithmetic result.')
        self.store.handoff('mission', tid, claim['token'], builder.workflow.artifact(self.project, path.relative_to(self.project).as_posix()))
    def gate(self, mid): return builder.gate(self.project, self.store, self.saved, self.shape, mid)
    def test_intake_from_empty_project_and_repeat(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder); project=base/'empty';project.mkdir();request=base/'request.txt'
            request.write_text('Build a runnable system and preserve original acceptance.')
            first=builder.bootstrap(project,'new-goal',request)
            self.assertTrue(first['created']);self.assertFalse(first['project_complete'])
            self.assertFalse(builder.bootstrap(project,'new-goal',request)['created'])
            self.assertEqual([p.name for p in project.iterdir()],['.runtime-proof'])
    def test_intake_refuses_changed_goal(self):
        request=self.project/'new-request.txt';request.write_text('This is a different original request than the existing root.')
        with self.assertRaisesRegex(ValueError,'differs'):builder.bootstrap(self.project,'mission',request)
    def test_cannot_advance_from_successful_child_without_handoff(self):
        with self.assertRaisesRegex(ValueError,'Earlier'):builder.claim(self.project,self.store,self.saved,self.shape,'delivery','worker',120)
    def test_milestone_success_does_not_close_project(self):
        self.deliver('slice');r=self.gate('M1')
        self.assertTrue(r['passed']);self.assertFalse(r['root_goal_achieved'])
    def test_final_gate_requires_all_handoffs_and_proof(self):
        self.deliver('slice');self.assertFalse(self.gate('M2')['passed'])
        self.deliver('delivery');self.assertTrue(self.gate('M2')['root_goal_achieved'])
    def test_resume_selects_next_milestone_without_repeating_slice(self):
        self.deliver('slice');self.gate('M1');self.reload()
        result=builder.next_action(self.project,self.store,self.saved,self.shape)
        self.assertEqual(result['milestone'],'M2');self.assertEqual(result['action'],'IMPLEMENT_MILESTONE')
    def test_checks_reuse_fresh_evidence_without_executing(self):
        before=list((self.project/'.runtime-proof').glob('*/runs/*/*'))
        state=builder.snapshot(self.project,self.store,self.saved,self.shape)
        result=builder.checks_needed(self.shape,state,'M2')
        self.assertEqual(result['run_only_missing_failed_or_stale'],[])
        self.assertEqual(len(result['reuse_current_checks']),2)
        self.assertEqual(before,list((self.project/'.runtime-proof').glob('*/runs/*/*')))
    def test_regression_reopens_prior_acceptance_not_prior_work(self):
        self.deliver('slice');self.gate('M1');self.deliver('delivery');self.gate('M2')
        source=self.project/'demo_cli.py';source.write_text(source.read_text()+'\n# relevant change\n')
        result=builder.next_action(self.project,self.store,self.saved,self.shape)
        self.assertEqual(result['action'],'REVALIDATE_CHANGED_MILESTONE')
        self.assertFalse(self.gate('M2')['root_goal_achieved'])
    def test_reopen_repair_requires_failure(self):
        self.deliver('slice')
        with self.assertRaisesRegex(ValueError,'failed/stale'):
            builder.reopen(self.project,self.store,self.saved,self.shape,'slice','.runtime-proof/slice-handoff.txt','Try another implementation')
    def test_reopen_preserves_artifacts_and_fences_active_descendants(self):
        self.deliver('slice');c=builder.claim(self.project,self.store,self.saved,self.shape,'delivery','worker',120)
        source=self.project/'demo_cli.py';source.write_text('print("bad")\n')
        with self.assertRaisesRegex(ValueError,'downstream'):
            builder.reopen(self.project,self.store,self.saved,self.shape,'slice','.runtime-proof/slice-handoff.txt','Fix the independently reproduced bad output')
        self.store.handoff('mission','delivery',c['token'],builder.workflow.artifact(self.project,'.runtime-proof/slice-handoff.txt'))
        out=builder.reopen(self.project,self.store,self.saved,self.shape,'slice','.runtime-proof/slice-handoff.txt','Fix the independently reproduced bad output')
        self.assertEqual(out['status'],'REPAIR_READY')
        self.assertTrue((self.project/'.runtime-proof/smoke/latest/addition.json').is_file())
        self.assertEqual(next(r for r in self.store.inspect('mission') if r['id']=='slice')['state'],'TODO')
    def test_repair_can_fix_a_regression_in_earlier_milestone_without_deadlock(self):
        self.deliver('slice');self.deliver('delivery')
        source=self.project/'demo_cli.py';source.write_text('print(\'{"sum":13}\')\n')
        with contextlib.redirect_stdout(io.StringIO()):
            result=proof.run_check(self.project/'.runtime-proof/integration','addition')
        self.assertFalse(result['passed'])
        latest=proof.load(self.project/'.runtime-proof/integration/latest/addition.json')
        evidence=(self.project/'.runtime-proof/integration'/latest['run']/'stdout.log').relative_to(self.project).as_posix()
        builder.reopen(self.project,self.store,self.saved,self.shape,'delivery',evidence,'Reproduce wrong numeric result and correct the integration regression')
        self.reload()
        self.assertEqual(builder.next_action(self.project,self.store,self.saved,self.shape)['action'],'REPAIR_REGISTERED_DEFECT')
        claim=builder.claim(self.project,self.store,self.saved,self.shape,'delivery','actual-repair-worker',120)
        self.assertTrue(claim['repair_mode'])
        self.assertFalse(self.gate('M2')['root_goal_achieved'])

    def test_unstarted_task_cannot_disguise_initial_work_as_a_repair(self):
        source=self.project/'demo_cli.py';source.write_text('print(\'{"sum":13}\')\n')
        evidence=self.project/'diagnosis.txt';evidence.write_text('The current output differs from the independent expected numeric result.')
        with self.assertRaisesRegex(ValueError,'previously attempted'):
            builder.reopen(self.project,self.store,self.saved,self.shape,'delivery','diagnosis.txt','Try to jump ahead without completing the runnable slice')

    def test_architecture_missing_rejected(self):
        s=plan();s['build'].pop('architecture')
        with self.assertRaisesRegex(ValueError,'Architecture'):builder.validate_plan(s)
    def test_no_alternative_considered_rejected(self):
        s=plan();s['build']['architecture']['alternatives']=[]
        with self.assertRaises(ValueError):builder.validate_plan(s)
    def test_milestone_omission_rejected(self):
        s=plan();s['build']['milestones'][1]['tasks']=['slice']
        with self.assertRaises(ValueError):builder.validate_plan(s)
    def test_first_stage_requires_runnable_slice(self):
        s=plan();s['build']['milestones'][0]['kind']='increment'
        with self.assertRaisesRegex(ValueError,'runnable'):builder.validate_plan(s)
    def test_milestone_dependency_cycle_rejected(self):
        s=plan();s['build']['milestones'][0]['depends_on']=['M2']
        with self.assertRaisesRegex(ValueError,'cycle'):builder.validate_plan(s)
    def test_omitted_root_requirement_rejected(self):
        s=plan();s['build']['milestones'][1]['requirements']=['ROOT01']
        with self.assertRaisesRegex(ValueError,'original root'):builder.binding(self.project,s)
    def test_fake_extra_root_requirement_rejected(self):
        s=plan();s['build']['milestones'][1]['requirements'].append('INVENTED')
        with self.assertRaises(ValueError):builder.binding(self.project,s)
    def test_stage_without_live_acceptance_rejected(self):
        p=self.project/'.runtime-proof/smoke/contract.json';c=proof.load(p)
        c['checks'][0]['mode']='offline';c['requirements'][0]['runtime_required']=False
        proof.save(p,c);proof.save(p.parent/'seal.json',{'contract_hash':proof.digest(c),'engine_hash':proof.engine_hash(c)})
        with self.assertRaisesRegex(ValueError,'live'):builder.binding(self.project,plan())
    def test_unknown_interface_producer_rejected(self):
        s=plan();s['build']['interfaces']=[{'id':'HTTP','producer':'missing','consumers':['delivery'],'contract_file':'README.md'}]
        with self.assertRaises(ValueError):builder.validate_plan(s)
    def test_changed_interface_contract_rejected(self):
        f=self.project/'API.md';f.write_text('Required interface contract, not implementation output.')
        s=plan();s['goal_id']='other';s['build']['interfaces']=[{'id':'API','producer':'slice','consumers':['delivery'],'contract_file':'API.md'}]
        builder.register(self.project,s);f.write_text('silently weakened response contract')
        with self.assertRaisesRegex(ValueError,'contracts changed'):builder.open_build(self.project,'other')
    def test_invalid_host_boolean_rejected(self):
        s=plan();s['build']['host']['delegation_available']='true'
        with self.assertRaises(ValueError):builder.validate_plan(s)
    def test_serial_when_host_cannot_delegate(self):
        r=builder.routing(self.spec['tasks'],self.spec['build']['host'])
        self.assertEqual(r['mode'],'serial-current-host');self.assertFalse(r['agents_spawned'])
    def test_parallel_only_independent_available_host_work(self):
        tasks=[{'id':'A','write_scope':['src/a.py']},{'id':'B','write_scope':['src/b.py']}]
        host=dict(self.spec['build']['host'],delegation_available=True,max_parallel_workers=2)
        self.assertEqual(builder.routing(tasks,host)['task_ids'],['A','B'])
        tasks[1]['write_scope']=['src']
        self.assertEqual(builder.routing(tasks,host)['task_ids'],['A'])
    def test_parallel_resource_conflict_not_selected(self):
        tasks=[{'id':'A','resources':['gpu:0']},{'id':'B','resources':['gpu:0']}]
        host=dict(self.spec['build']['host'],delegation_available=True,max_parallel_workers=2)
        self.assertEqual(len(builder.routing(tasks,host)['task_ids']),1)
    def test_repeated_registration_does_not_reset_progress(self):
        self.deliver('slice');builder.register(self.project,self.spec)
        self.assertEqual(next(r for r in self.store.inspect('mission') if r['id']=='slice')['state'],'IMPLEMENTED')
    def test_changed_plan_not_silently_applied(self):
        s=copy.deepcopy(self.spec);s['build']['architecture']['rationale']='A new architectural decision after registration'
        with self.assertRaisesRegex(ValueError,'different plan'):builder.register(self.project,s)
    def test_next_does_not_treat_running_task_as_finished(self):
        builder.claim(self.project,self.store,self.saved,self.shape,'slice','worker',120)
        self.assertEqual(builder.next_action(self.project,self.store,self.saved,self.shape)['action'],'CONTINUE_ACTIVE_WORK')
    def test_lease_expiry_is_not_completion(self):
        builder.claim(self.project,self.store,self.saved,self.shape,'slice','worker',120)
        self.store.clock=lambda:1e15
        r=builder.next_action(self.project,self.store,self.saved,self.shape)
        self.assertEqual(r['action'],'RECONCILE_EXPIRED_WORKER');self.assertFalse(r['root_goal_achieved'])
    def test_ready_deliver_only_when_original_root_passes(self):
        self.deliver('slice');self.deliver('delivery')
        result=builder.next_action(self.project,self.store,self.saved,self.shape)
        self.assertEqual(result['action'],'DELIVER');self.assertTrue(result['root']['root_goal_achieved'])


if __name__=='__main__':unittest.main()
