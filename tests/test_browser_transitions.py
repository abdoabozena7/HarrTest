import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from browser_probe import assert_text_comparison, validate_transition_step

class Transitions(unittest.TestCase):
    def test_pause_stable(self):
        assert_text_comparison({"paused":"01:59"},"paused","01:59",must_change=False)
    def test_resume_changes(self):
        assert_text_comparison({"paused":"01:59"},"paused","01:58",must_change=True)
    def test_broken_resume_fails(self):
        with self.assertRaises(AssertionError):
            assert_text_comparison({"paused":"01:59"},"paused","01:59",must_change=True)
    def test_hidden_timer_fails(self):
        with self.assertRaises(AssertionError):
            assert_text_comparison({"paused":"01:59"},"paused","01:58",must_change=False)
    def test_missing_reference_fails(self):
        with self.assertRaises(ValueError):
            assert_text_comparison({},"paused","01:58",must_change=True)
    def test_wait_limit(self):
        with self.assertRaises(ValueError):
            validate_transition_step({"action":"wait_ms","milliseconds":20000})
    def test_wait_boolean_rejected(self):
        with self.assertRaises(ValueError):
            validate_transition_step({"action":"wait_ms","milliseconds":True})
    def test_missing_selector(self):
        with self.assertRaises(ValueError):
            validate_transition_step({"action":"expect_text_changed","name":"x"})
    def test_valid_text_check(self):
        validate_transition_step({"action":"expect_text_changed","name":"paused","selector":"#clock"})
if __name__=="__main__":
    unittest.main()
