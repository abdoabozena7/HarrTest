import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from strict_gates import evaluate


def contract():
    return {'required_gates':[
        {'id':'p95_ms','op':'<=','limit':'200'},
        {'id':'p99_ms','op':'<=','limit':'250'},
        {'id':'late_count','op':'==','limit':0},
        {'id':'samples','op':'==','limit':601}]}


def readings():
    return {'observations':{'p95_ms':'184.656','p99_ms':'201.667','late_count':1,'samples':601}}


class StrictGateTests(unittest.TestCase):
    def test_percentile_pass_one_tail_failure_is_failure(self):
        r=evaluate(contract(),readings())
        self.assertFalse(r['passed']);self.assertEqual(r['status'],'FAIL_HARD_GATE')
        self.assertEqual([g['id'] for g in r['checks'] if not g['passed']],['late_count'])
    def test_true_all_of_is_only_declared_scope(self):
        r=readings();r['observations']['late_count']=0
        report=evaluate(contract(),r)
        self.assertTrue(report['passed']);self.assertTrue(report['authoritative_contract_and_evidence_required'])
    def test_missing_observation_fails_closed(self):
        r=readings();del r['observations']['late_count']
        self.assertFalse(evaluate(contract(),r)['passed'])
    def test_nan_fails(self):
        r=readings();r['observations']['late_count']=float('nan')
        self.assertFalse(evaluate(contract(),r)['passed'])
    def test_missing_samples_fails(self):
        r=readings();r['observations']['samples']=600
        self.assertFalse(evaluate(contract(),r)['passed'])
    def test_duplicate_gate_rejected(self):
        c=contract();c['required_gates'].append(c['required_gates'][0])
        with self.assertRaisesRegex(ValueError,'duplicate'):evaluate(c,readings())
    def test_unknown_comparator_rejected(self):
        c=contract();c['required_gates'][0]['op']='approx'
        with self.assertRaisesRegex(ValueError,'comparator'):evaluate(c,readings())
    def test_boolean_measurement_is_not_numeric(self):
        r=readings();r['observations']['late_count']=True
        self.assertFalse(evaluate(contract(),r)['passed'])


if __name__=='__main__':unittest.main()