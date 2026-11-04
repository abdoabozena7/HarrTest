"""Do not let evaluation bookkeeping manufacture an improvement claim."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluation


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.manifest={'schema':1,'arms':['baseline','candidate'],'trials':[{'id':'task-1'},{'id':'task-2'}]}
        base={'outcome':'VERIFIED','claimed_complete':True,'independent_pass':True,'evidence':['real-run-reference'],
              'evidence_class':'deterministic-fixture','model':'same','host':'same','source':'same','tools':'same',
              'permissions':'same','evaluator':'same','avoidable_interventions':0,'policy_violations':0}
        self.rows=[dict(base,trial=t['id'],arm=a) for t in self.manifest['trials'] for a in self.manifest['arms']]
    def test_fixtures_never_prove_model_uplift(self):
        r=evaluation.summarize(self.manifest,self.rows);self.assertEqual(r['behavioral_impact'],'BEHAVIORAL_IMPACT_UNPROVEN')
        self.assertFalse(r['release_recommended'])
    def test_missing_trials_stay_in_denominator(self):
        r=evaluation.summarize(self.manifest,self.rows[:2]);self.assertEqual(r['arms']['candidate']['root_completion_rate'],0.5)
    def test_blocked_not_silently_excluded(self):
        self.rows[-1].update(outcome='BLOCKED',claimed_complete=False,independent_pass=None,evidence=[])
        r=evaluation.summarize(self.manifest,self.rows);self.assertEqual(r['arms']['candidate']['root_completion_rate'],0.5)
    def test_false_success_is_counted(self):
        self.rows[-1].update(outcome='FAILED',independent_pass=False)
        r=evaluation.summarize(self.manifest,self.rows);self.assertEqual(r['arms']['candidate']['false_verified'],1)
    def test_duplicate_records_rejected(self):
        with self.assertRaises(ValueError):evaluation.summarize(self.manifest,self.rows+[self.rows[0]])
    def test_string_true_rejected(self):
        self.rows[0]['independent_pass']='true'
        with self.assertRaises(ValueError):evaluation.summarize(self.manifest,self.rows)
    def test_mismatched_model_prevents_controlled_label(self):
        for r in self.rows:r['evidence_class']='live-agent'
        self.rows[0]['model']='different'
        self.assertEqual(evaluation.summarize(self.manifest,self.rows)['behavioral_impact'],'BEHAVIORAL_IMPACT_UNPROVEN')
    def test_unreviewed_success_claim_visible(self):
        self.rows[0].update(outcome='FAILED',independent_pass=None)
        r=evaluation.summarize(self.manifest,self.rows);self.assertEqual(r['arms']['baseline']['unreviewed_claims'],1)
    def test_no_pass_without_evidence(self):
        self.rows[0]['evidence']=[]
        with self.assertRaises(ValueError):evaluation.summarize(self.manifest,self.rows)
    def test_security_violation_not_offset_by_success(self):
        self.rows[0]['policy_violations']=1
        self.assertFalse(evaluation.summarize(self.manifest,self.rows)['permission_gate_passed'])


if __name__=='__main__':unittest.main()
