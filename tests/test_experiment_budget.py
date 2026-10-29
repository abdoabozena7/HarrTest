import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from experiment_budget import plan


def case():
    return ({'unit':'seconds','min_execution':180,'max_execution':1800,
             'fixed_reserve':300,'spendable':'550.070','protected':False},
            {'unit':'seconds','minimum_meaningful_execution':240,'preferred_execution':300,
             'may_shorten_preferred':True,'execution_granularity':1,'unspent_margin':'10'})


class BudgetPlannerTests(unittest.TestCase):
    def test_legal_shorter_plan_exposes_planned_vs_true_minimum(self):
        p,e=case();r=plan(p,e)
        self.assertEqual(r['policy_minimum_total'],'480')
        self.assertEqual(r['preferred_total'],'600')
        self.assertEqual(r['meaningful_minimum_total'],'540')
        self.assertEqual(r['candidate_execution'],'240')
        self.assertEqual(r['candidate_reservation'],'540')
        self.assertEqual(r['status'],'CANDIDATE_READ_ONLY_NOT_AUTHORIZED')
        self.assertFalse(r['authorization_granted'])
        self.assertTrue(r['host_preflight_required'])
    def test_one_remaining_balance_below_true_minimum(self):
        p,e=case();p['spendable']='262.367';r=plan(p,e)
        self.assertEqual(r['status'],'BLOCKED_RESOURCE_READ_ONLY')
        self.assertEqual(r['minimum_policy_shortfall'],'217.633')
        self.assertEqual(r['minimum_meaningful_shortfall'],'287.633')
        self.assertIsNone(r['candidate_execution'])
    def test_no_shorter_than_preferred_if_original_goal_disallows(self):
        p,e=case();e['may_shorten_preferred']=False
        self.assertEqual(plan(p,e)['status'],'BLOCKED_RESOURCE_READ_ONLY')
    def test_does_not_drain_protected_budget(self):
        p,e=case();p['protected']=True
        with self.assertRaisesRegex(ValueError,'unprotected'):plan(p,e)
    def test_invalid_policy_no_unsafe_fallback(self):
        p,e=case();p['min_execution']=1801
        with self.assertRaisesRegex(ValueError,'maximum'):plan(p,e)
    def test_meaningful_goal_floor_not_weakened(self):
        p,e=case();e['minimum_meaningful_execution']=301
        with self.assertRaisesRegex(ValueError,'below'):plan(p,e)
    def test_negative_nan_bool_string_coercion_blocked(self):
        for value in (-1,True,float('nan'),[],None):
            p,e=case();p['spendable']=value
            with self.subTest(value=repr(value)),self.assertRaises(ValueError):plan(p,e)
    def test_precision_rounds_execution_down_to_granularity(self):
        p,e=case();p['spendable']='550.50';e['unspent_margin']='10';
        self.assertEqual(plan(p,e)['candidate_execution'],'240')
    def test_unit_mismatch(self):
        p,e=case();e['unit']='USD'
        with self.assertRaisesRegex(ValueError,'unit'):plan(p,e)
    def test_fixed_cleanup_reserve_cannot_be_ignored(self):
        p,e=case();p['spendable']=270
        self.assertEqual(plan(p,e)['status'],'BLOCKED_RESOURCE_READ_ONLY')
    def test_exact_science_minimum_plus_margin(self):
        p,e=case();p['spendable']=550
        self.assertEqual(plan(p,e)['candidate_reservation'],'540')
    def test_no_provenance_or_approval_claim(self):
        p,e=case();r=plan(p,e)
        self.assertFalse(r['changes_policy_or_thresholds'])
        self.assertFalse(r['authorization_granted'])


if __name__ == '__main__':unittest.main()