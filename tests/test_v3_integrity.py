"""Regressions derived from the v2 code audit; real proof subprocesses where needed."""
import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import proof
import planning
import coverage
import strict_io
import root_gate
import workflow
import test_root_gate
import test_proof
import test_goal_guard


class StrictTests(unittest.TestCase):
    def test_duplicate_json_keys_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'result.json';p.write_text('{"passed":false,"passed":true}')
            with self.assertRaisesRegex(proof.ProofError,'Duplicate'):proof.load(p)
    def test_nested_duplicate_rejected(self):
        with self.assertRaises(ValueError):strict_io.loads('{"nested":{"status":0,"status":1}}')
    def test_nonfinite_rejected(self):
        for value in ('NaN','Infinity','-Infinity'):
            with self.assertRaises(ValueError):strict_io.loads('{"value":'+value+'}')
    def test_check_specific_helper_change_invalidates_receipt_engine(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'scripts').mkdir()
            for name in ('proof.py','planning.py','strict_io.py','browser_probe.py'):(root/'scripts'/name).write_text('initial')
            contract={'checks':[{'command':['python','{skill}/scripts/browser_probe.py']}]}
            with patch.object(proof,'SKILL',root):
                before=proof.engine_hash(contract)
                (root/'scripts/browser_probe.py').write_text('changed actual browser verifier')
                self.assertNotEqual(before,proof.engine_hash(contract))

    def test_declared_helper_receipt_can_verify_end_to_end(self):
        fixture=test_proof.ProofTests();fixture.setUp()
        try:
            fixture.c['harness_dependencies']=['scripts/version_guard.py']
            fixture.seal()
            proof.save(fixture.task/'seal.json',{'contract_hash':proof.digest(fixture.c),
                       'engine_hash':proof.engine_hash(fixture.c)})
            fixture.complete()
            self.assertTrue(proof.verify(fixture.task)['passed'])
        finally:fixture.tearDown()

    def test_journey_guard_accepts_schema_three_inventory(self):
        fixture=test_goal_guard.GoalGuardTests();fixture.setUp()
        try:
            contract=dict(fixture.contract,scope='root',root_request_sha256='b'*64)
            root={'schema':3,'request_sha256':'b'*64,'requirements':[{'id':'R1'}]}
            self.assertTrue(fixture.check(contract,root)['passed'])
        finally:fixture.doCleanups()

    def test_scope_parent_directory_and_case(self):
        self.assertTrue(strict_io.overlaps('SRC','src/file.py'))
        self.assertFalse(strict_io.overlaps('src/file.py','src/file.py.bak'))
    def test_absolute_and_traversal_paths_rejected(self):
        for name in ('C:/secret','../a','/root/a','a//b','a/./b','a\\b'):
            with self.assertRaises(ValueError):strict_io.scoped_path(Path('.'),name,must_exist=False)
    def test_engine_ignores_unrelated_helper_but_not_collector(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'scripts').mkdir()
            for name in ('proof.py','planning.py','strict_io.py','version_guard.py'):(root/'scripts'/name).write_text('initial')
            with patch.object(proof,'SKILL',root):
                before=proof.engine_hash();(root/'scripts/version_guard.py').write_text('update only release lookup')
                self.assertEqual(before,proof.engine_hash())
                (root/'scripts/proof.py').write_text('collector changed')
                self.assertNotEqual(before,proof.engine_hash())


class RootHookTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_root_gate.RootGateTests();self.fixture.setUp();self.project=self.fixture.project;self.goal=self.fixture.goal
    def tearDown(self):self.fixture.tearDown()
    def active(self, child):
        proof.save(self.project/'.runtime-proof/active.json',{'task':child,'root_goal':'mission','root_required':True})
    def upgrade_root(self, omit_tail=False):
        c=copy.deepcopy(self.fixture.c);c['schema']=3
        request=(self.goal/'original-request.txt').read_text()
        end=len(request)
        if omit_tail:
            request += '\nAlso restore saved results after restart.'
            (self.goal/'original-request.txt').write_text(request)
        c['request_sha256']=proof.file_hash(self.goal/'original-request.txt')
        c['request_segments']=[{'start':0,'end':end,'kind':'requirement','requirement_ids':['ROOT01','ROOT02']}]
        review={'request_sha256':c['request_sha256'],'segments_sha256':strict_io.digest(c['request_segments']),
                'acceptance_sha256':strict_io.digest({'requirements':c['requirements'],'integration':c['integration']}),
                'method':'fresh-context-agent','planner':'fixture-planner','reviewer':'fixture-reviewer','verdict':'covered',
                'unresolved_findings':[],'observations':'Synthetic structural test mapping original command and full integration; not a real agent review.'}
        proof.save(self.goal/'coverage.json',review)
        c['coverage_challenge']={'file':'coverage.json','sha256':proof.file_hash(self.goal/'coverage.json')}
        proof.save(self.goal/'root-contract.json',c)
        proof.save(self.goal/'root-seal.json',{'root_hash':proof.digest(c),'request_sha256':c['request_sha256'],'sealed_at':proof.now()})
    def test_v3_root_runs_real_child_acceptance(self):
        self.upgrade_root();self.fixture.child('smoke');self.fixture.child('integration')
        result=root_gate.check_root(self.goal)
        self.assertTrue(result['root_goal_achieved'])
        self.assertEqual(result['coverage_assurance'],'FULL_TEXT_MAPPED_REVIEW_DECLARED')
    def test_original_restart_text_omitted_from_v3_root_rejected(self):
        self.upgrade_root(omit_tail=True);self.fixture.child('smoke');self.fixture.child('integration')
        result=root_gate.check_root(self.goal)
        self.assertFalse(result['root_goal_achieved'])
        self.assertIn('unmapped',str(result['errors']))

    def test_child_pass_does_not_allow_root_success(self):
        self.fixture.child('smoke');self.active('smoke')
        out=proof.hook({'cwd':str(self.project)})
        self.assertEqual(out['decision'],'block')
        report=proof.load(self.project/'.runtime-proof/smoke/completion.json')
        self.assertFalse(report['root_goal_achieved'])
    def test_root_pass_allows_completion(self):
        self.fixture.child('smoke');self.fixture.child('integration');self.active('integration')
        self.assertEqual(proof.hook({'cwd':str(self.project)}),{})
        self.assertEqual(proof.load(self.project/'.runtime-proof/integration/completion.json')['disposition'],'GOAL_COMPLETE')
    def test_auto_discovers_related_unfinished_root(self):
        self.fixture.child('smoke');proof.save(self.project/'.runtime-proof/active.json',{'task':'smoke'})
        self.assertEqual(proof.hook({'cwd':str(self.project)})['decision'],'block')
    def test_user_cancel_is_respected_without_certification(self):
        self.fixture.child('smoke');self.active('smoke')
        self.assertEqual(proof.hook({'cwd':str(self.project),'user_requested_stop':True}),{})
        self.assertFalse(proof.load(self.project/'.runtime-proof/smoke/completion.json')['root_goal_achieved'])
    def test_forced_stop_still_not_goal_complete(self):
        self.fixture.child('smoke');self.active('smoke');proof.hook({'cwd':str(self.project)})
        self.assertEqual(proof.hook({'cwd':str(self.project),'stop_hook_active':True}),{})
        self.assertEqual(proof.load(self.project/'.runtime-proof/smoke/completion.json')['disposition'],'PAUSED_UNVERIFIED')
    def test_no_historical_gate_overwrite(self):
        child=self.fixture.child('smoke');self.active('smoke')
        proof.save(child/'gate.json',{'historical':'keep exact bytes'});before=(child/'gate.json').read_bytes()
        proof.hook({'cwd':str(self.project)});self.assertEqual(before,(child/'gate.json').read_bytes())
    def test_unknown_explicit_root_fails_closed_not_unhandled(self):
        self.fixture.child('smoke');self.active('smoke')
        proof.save(self.project/'.runtime-proof/active.json',{'task':'smoke','root_goal':'missing','root_required':True})
        self.assertEqual(proof.hook({'cwd':str(self.project)})['decision'],'block')


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.goal=Path(self.t.name)
        self.request='Save the results.\nRestore them after restart.\n'
        self.c={'schema':3,'request_sha256':strict_io.digest(self.request),
                'requirements':[{'id':'SAVE','source':'user_request'},{'id':'RESTORE','source':'user_request'}],
                'integration':{'task_id':'all','requirement_id':'R1'}}
        self.c['request_segments']=coverage.inventory(self.request)
        for seg,rid in zip(self.c['request_segments'],('SAVE','RESTORE')):seg['requirement_ids']=[rid]
        self.review()
    def tearDown(self):self.t.cleanup()
    def review(self,**extra):
        report={'request_sha256':self.c['request_sha256'],'segments_sha256':strict_io.digest(self.c['request_segments']),
                'acceptance_sha256':strict_io.digest({'requirements':self.c['requirements'],'integration':self.c['integration']}),
                'method':'fresh-context-agent','planner':'fixture-planner','reviewer':'fixture-reviewer',
                'verdict':'covered','unresolved_findings':[],
                'observations':'Synthetic structural fixture checks that both save and restart are explicitly mapped; no real LLM review is claimed.',**extra}
        proof.save(self.goal/'review.json',report)
        self.c['coverage_challenge']={'file':'review.json','sha256':proof.file_hash(self.goal/'review.json')}
    def test_complete_mapping_passes_structure_only(self):
        out=coverage.validate(self.request,self.c,self.goal);self.assertFalse(out['independence_authenticated'])
    def test_omitted_restart_span_fails(self):
        self.c['request_segments'].pop();self.review()
        with self.assertRaisesRegex(ValueError,'unmapped'):coverage.validate(self.request,self.c,self.goal)
    def test_requirement_not_linked_fails(self):
        self.c['request_segments'][1]['requirement_ids']=[];self.review()
        with self.assertRaises(ValueError):coverage.validate(self.request,self.c,self.goal)
    def test_same_reviewer_and_writer_rejected(self):
        self.review(reviewer='fixture-planner')
        with self.assertRaisesRegex(ValueError,'separate'):coverage.validate(self.request,self.c,self.goal)
    def test_unresolved_challenge_rejected(self):
        self.review(unresolved_findings=['Restart not exercised'])
        with self.assertRaisesRegex(ValueError,'unresolved'):coverage.validate(self.request,self.c,self.goal)
    def test_changed_acceptance_invalidates_review(self):
        self.c['requirements'][1]['claim']='Changed requirement after review'
        with self.assertRaisesRegex(ValueError,'different acceptance'):coverage.validate(self.request,self.c,self.goal)
    def test_tampered_review_rejected(self):
        (self.goal/'review.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'changed'):coverage.validate(self.request,self.c,self.goal)
    def test_overlapping_ranges_rejected(self):
        self.c['request_segments'][1]['start']=0;self.review()
        with self.assertRaisesRegex(ValueError,'Overlapping'):coverage.validate(self.request,self.c,self.goal)
    def test_context_not_silent_exclusion(self):
        self.c['request_segments'][1].update(kind='context',requirement_ids=[],rationale='skip');self.review()
        with self.assertRaises(ValueError):coverage.validate(self.request,self.c,self.goal)


class PlanConflictTests(unittest.TestCase):
    def plan(self):
        base=proof.load(Path(__file__).resolve().parents[1]/'examples/cli-contract.json')['plan']
        t=copy.deepcopy(base['tasks'][0]);t.update(id='A',role='implement',execution='subagent',write_scope=['src/common.py'])
        other=copy.deepcopy(t);other['id']='B'
        join=copy.deepcopy(t);join.update(id='C',role='integrate',execution='serial',depends_on=['A','B'],write_scope=[])
        base.update(strategy='parallel',delegation={'available':True,'evidence':'Synthetic host capability for planner checks'},tasks=[t,other,join]);return base
    def test_parallel_same_file_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflict'):planning.validate(self.plan(),{'R01'},{'addition'})
    def test_dependency_orders_same_file_safely(self):
        plan=self.plan();plan['tasks'][1]['depends_on']=['A'];planning.validate(plan,{'R01'},{'addition'})
    def test_independent_disjoint_workers_allowed(self):
        plan=self.plan();plan['tasks'][1]['write_scope']=['src/other.py'];planning.validate(plan,{'R01'},{'addition'})
    def test_read_write_overlap_rejected(self):
        plan=self.plan();plan['tasks'][1]['write_scope']=[];plan['tasks'][1]['read_scope']=['src']
        with self.assertRaises(ValueError):planning.validate(plan,{'R01'},{'addition'})
    def test_exclusive_resource_prevents_parallel_workers(self):
        plan=self.plan();plan['tasks'][1]['write_scope']=['src/other.py']
        plan['tasks'][0]['resources']=['simulator'];plan['tasks'][1]['resources']=['simulator']
        with self.assertRaises(ValueError):planning.validate(plan,{'R01'},{'addition'})


if __name__=='__main__':unittest.main()
