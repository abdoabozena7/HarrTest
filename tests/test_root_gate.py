"""Root-gate v2 regression cases: a passed smoke cannot close an incomplete root."""
import copy
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import proof
import root_gate

class RootGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.project=Path(self.tmp.name)
        (self.project/"demo_cli.py").write_bytes((ROOT/"examples/demo_cli.py").read_bytes())
        self.goal=self.project/".runtime-proof/root-goals/mission"
        self.goal.mkdir(parents=True)
        request="Build a working arithmetic command that returns numeric twelve, and verify the final integrated command."
        (self.goal/"original-request.txt").write_text(request)
        self.c={"schema":2,"goal_id":"mission","request_sha256":proof.file_hash(self.goal/"original-request.txt"),
          "scope_statement":"Verify the working command and full integrated behavior separately.",
          "coverage_review":{"method":"same-agent","rationale":"The entire request was compared to implementation and integration acceptance contracts.", "unmapped_segments":[]},
          "requirements":[
            {"id":"ROOT01","claim":"Working command returns numeric twelve.","oracle":"Execute real command and observe the numeric twelve.",
             "source":"user_request","source_excerpt":"working arithmetic command","evidence_mode":"live",
             "satisfiers":[{"task_id":"smoke","requirement_id":"R01"}]},
            {"id":"ROOT02","claim":"Final integrated CLI behavior passes.","oracle":"Execute the actual finished CLI and compare outputs.",
             "source":"user_request","source_excerpt":"verify the final integrated command","evidence_mode":"live",
             "satisfiers":[{"task_id":"integration","requirement_id":"R01"}]}],
          "integration":{"task_id":"integration","requirement_id":"R01","scope":"Entire integrated CLI journey verified independently."}}
        proof.save(self.goal/"root-contract.json",self.c)
        proof.save(self.goal/"root-seal.json",{"root_hash":proof.digest(self.c),
           "request_sha256":self.c["request_sha256"],"sealed_at":proof.now()})
    def tearDown(self): self.tmp.cleanup()
    def child(self,name):
        task=self.project/".runtime-proof"/name
        task.mkdir()
        c=proof.load(ROOT/"examples/cli-contract.json")
        c["task_id"]=name
        proof.save(task/"context.json",{"project":str(self.project)})
        proof.save(task/"contract.json",c)
        proof.save(task/"seal.json",{"contract_hash":proof.digest(c),"engine_hash":proof.engine_hash()})
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(proof.run_check(task,"addition")["passed"])
        proof.update_step(task,"T01","VERIFIED","Ran and checked real arithmetic subprocess result of numeric twelve.")
        return task
    def test_no_children_fails(self):
        self.assertFalse(root_gate.check_root(self.goal)["root_goal_achieved"])
    def test_child_success_does_not_complete_root(self):
        smoke=self.child("smoke")
        self.assertTrue(proof.verify(smoke)["passed"])
        self.assertEqual(proof.verify(smoke)["completion_scope"],"CHILD_TASK_ONLY")
        self.assertFalse(proof.verify(smoke)["root_goal_achieved"])
        result=root_gate.check_root(self.goal)
        self.assertFalse(result["root_goal_achieved"])
        self.assertTrue(result["requirements"][0]["passed"])
        self.assertFalse(result["requirements"][1]["passed"])
    def test_integration_required(self):
        self.child("smoke")
        self.child("integration")
        self.assertTrue(root_gate.check_root(self.goal)["root_goal_achieved"])
    def test_changed_source_invalidates_root(self):
        self.child("smoke"); self.child("integration")
        with (self.project/"demo_cli.py").open("a") as f:f.write("\n#changed")
        self.assertFalse(root_gate.check_root(self.goal)["root_goal_achieved"])
    def test_contract_cannot_be_shrunk_after_sealing(self):
        self.child("smoke")
        c=copy.deepcopy(self.c)
        c["requirements"]=c["requirements"][:1]
        c["integration"]["task_id"]="smoke"
        proof.save(self.goal/"root-contract.json",c)
        self.assertFalse(root_gate.check_root(self.goal)["root_goal_achieved"])
    def test_invalid_request_provenance_refused(self):
        c=copy.deepcopy(self.c)
        c["requirements"][0]["source_excerpt"]="absent from original"
        with self.assertRaises(proof.ProofError):
            root_gate.validate(self.project,self.goal,c)
    def test_unmapped_segments_refused(self):
        c=copy.deepcopy(self.c)
        c["coverage_review"]["unmapped_segments"]=["missing requirement"]
        with self.assertRaises(proof.ProofError):
            root_gate.validate(self.project,self.goal,c)
    def test_wrong_evidence_mode_refused(self):
        self.child("smoke"); self.child("integration")
        p=self.project/".runtime-proof/smoke/contract.json"
        c=proof.load(p); c["checks"][0]["mode"]="offline";proof.save(p,c)
        self.assertFalse(root_gate.check_root(self.goal)["root_goal_achieved"])

if __name__=="__main__":unittest.main()
