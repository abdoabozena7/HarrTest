import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from goal_guard import assess

class GoalGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        (self.base / "evidence.json").write_text('{"observed":"fixture"}')
        self.hash = hashlib.sha256((self.base / "evidence.json").read_bytes()).hexdigest()
        self.contract = {"schema":1, "scope":"child", "source_sha256":"a"*64,
            "requirements":[{"id":"R1","target":"timer.html","mode":"live",
                "journeys":[{"id":"timer_flow","steps":["start","pause","resume","reset"]}]}]}
        self.events = {"schema":1,"events":[self.event(s) for s in ["start","pause","resume","reset"]]}
    def event(self, step, run="first", **kwargs):
        obj = {"requirement_id":"R1","journey_id":"timer_flow","step_id":step,
            "run_id":run,"source_sha256":"a"*64,"target":"timer.html","mode":"live",
            "status":"PASS","passed":True,"observer":"playwright",
            "evidence_file":"evidence.json","evidence_sha256":self.hash}
        obj.update(kwargs)
        return obj
    def check(self, contract=None, root=None):
        return assess(contract or self.contract,self.events,self.base,root)
    def test_valid_full_sequence(self):
        self.assertTrue(self.check()["passed"])
    def test_incomplete_sequence(self):
        self.events["events"].pop(2)
        self.assertFalse(self.check()["passed"])
    def test_new_incomplete_run_overrules_old_success(self):
        self.events["events"].append(self.event("start","second"))
        self.assertFalse(self.check()["passed"])
    def test_interleaved_runs_cannot_be_combined(self):
        self.events["events"][2]["run_id"]="second"
        self.events["events"][3]["run_id"]="second"
        self.assertFalse(self.check()["passed"])
    def test_fresh_repaired_complete_run(self):
        self.events["events"][2].update(status="FAIL",passed=False)
        self.events["events"].extend(self.event(s,"second") for s in ["start","pause","resume","reset"])
        self.assertTrue(self.check()["passed"])
    def test_status_keyword_cannot_override_fail(self):
        self.events["events"][2].update(status="FAIL",passed=False,message="PASS")
        self.assertFalse(self.check()["passed"])
    def test_conflicting_status_passed_rejected(self):
        self.events["events"][2].update(status="FAIL",passed=True)
        self.assertFalse(self.check()["passed"])
    def test_unknown_does_not_supersede_failure(self):
        self.events["events"].append(self.event("start","second",status="UNAVAILABLE",passed=None))
        self.assertFalse(self.check()["passed"])
    def test_wrong_target_rejected(self):
        self.events["events"][0]["target"]="other.html"
        self.assertFalse(self.check()["passed"])
    def test_stale_source_rejected(self):
        self.events["events"][0]["source_sha256"]="b"*64
        self.assertFalse(self.check()["passed"])
    def test_modified_evidence_rejected(self):
        (self.base / "evidence.json").write_text("tampered")
        self.assertFalse(self.check()["passed"])
    def test_missing_evidence_rejected(self):
        (self.base / "evidence.json").unlink()
        self.assertFalse(self.check()["passed"])
    def test_traversal_rejected(self):
        self.events["events"][0]["evidence_file"]="../escape"
        self.assertFalse(self.check()["passed"])
    def test_unknown_step_rejected(self):
        self.events["events"][0]["step_id"]="pretend"
        self.assertFalse(self.check()["passed"])
    def test_root_missing_original_requirement(self):
        contract=dict(self.contract,scope="root",root_request_sha256="b"*64)
        root={"schema":2,"request_sha256":"b"*64,"requirements":[{"id":"R1"},{"id":"R2"}]}
        self.assertFalse(self.check(contract,root)["passed"])
    def test_root_complete_inventory(self):
        contract=dict(self.contract,scope="root",root_request_sha256="b"*64)
        contract["requirements"]=self.contract["requirements"]+[{"id":"R2","target":"timer.html",
           "mode":"live","journeys":[{"id":"reset_flow","steps":["reset"]}]}]
        self.events["events"].append(self.event("reset",requirement_id="R2",journey_id="reset_flow"))
        root={"schema":2,"request_sha256":"b"*64,"requirements":[{"id":"R1"},{"id":"R2"}]}
        self.assertTrue(self.check(contract,root)["passed"])
    def test_root_wrong_request(self):
        contract=dict(self.contract,scope="root",root_request_sha256="c"*64)
        root={"schema":2,"request_sha256":"b"*64,"requirements":[{"id":"R1"}]}
        self.assertFalse(self.check(contract,root)["passed"])
    def test_extra_event_rejected(self):
        self.events["events"].append(self.event("reset"))
        self.assertFalse(self.check()["passed"])

if __name__ == "__main__":
    unittest.main()
