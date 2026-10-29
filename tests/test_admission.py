import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from admission import precheck

NOW = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)


def fixture():
    return ({'action':'diagnostic', 'unit':'seconds', 'requested_units':480, 'minimum_reservation_units':480},
            {'scope':['diagnostic'], 'unit':'seconds', 'remaining_units':600,
             'protected':False, 'expires_at':'2026-10-31T00:00:00Z',
             'approval_provenance':{'source':'current user message', 'evidence':'explicit 600-second scope'}})


class AdmissionTest(unittest.TestCase):
    def test_positive_is_never_a_permission_token(self):
        i,p=fixture();r=precheck(i,p,NOW)
        self.assertEqual(r['status'],'PRECHECK_OK_NOT_AUTHORIZED')
        self.assertTrue(r['external_host_gate_required'])
        self.assertFalse(r['mutates_ledger'])
        self.assertEqual(r['after_if_admitted_units'],120)
    def test_actual_342_seconds_cannot_admit_480(self):
        i,p=fixture();p['remaining_units']=342.997
        self.assertIn('INSUFFICIENT_REMAINING_RESOURCE',precheck(i,p,NOW)['reasons'])
    def test_expired(self):
        i,p=fixture();p['expires_at']='2026-10-28T12:00:00Z'
        self.assertIn('DECLARED_ENVELOPE_EXPIRED',precheck(i,p,NOW)['reasons'])
    def test_outside_scope(self):
        i,p=fixture();i['action']='acceptance'
        self.assertIn('ACTION_OUTSIDE_DECLARED_SCOPE',precheck(i,p,NOW)['reasons'])
    def test_protected(self):
        i,p=fixture();p['protected']=True
        self.assertIn('PROTECTED_RESOURCE_REQUIRES_SEPARATE_AUTHORITY',precheck(i,p,NOW)['reasons'])
    def test_missing_provenance(self):
        i,p=fixture();p['approval_provenance']={}
        self.assertIn('NO_RECORDED_APPROVAL_PROVENANCE',precheck(i,p,NOW)['reasons'])
    def test_missing_expiry(self):
        i,p=fixture();p.pop('expires_at')
        self.assertIn('NO_EXPIRY_BOUND',precheck(i,p,NOW)['reasons'])
    def test_refuse_negative_nan_and_booleans(self):
        for bad in (-1, float('nan'), True, '480'):
            i,p=fixture();i['requested_units']=bad
            with self.subTest(bad=repr(bad)),self.assertRaises(ValueError): precheck(i,p,NOW)
    def test_minimum_guard(self):
        i,p=fixture();i['requested_units']=479
        with self.assertRaisesRegex(ValueError,'minimum'):precheck(i,p,NOW)
    def test_unit_mismatch(self):
        i,p=fixture();p['unit']='USD'
        with self.assertRaisesRegex(ValueError,'unit mismatch'):precheck(i,p,NOW)
    def test_no_timezone_expiry(self):
        i,p=fixture();p['expires_at']='2026-10-31T00:00:00'
        with self.assertRaisesRegex(ValueError,'timezone'):precheck(i,p,NOW)
    def test_equal_allowance_is_eligible(self):
        i,p=fixture();p['remaining_units']=480
        self.assertEqual(precheck(i,p,NOW)['after_if_admitted_units'],0)

if __name__=='__main__':unittest.main()