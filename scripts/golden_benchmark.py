#!/usr/bin/env python3
"""Compare actual workflow decisions on matched deterministic local CLI fixtures."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import zipfile

import strict_io

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = "6151b68f1abf16edb0e71170a4084013b31ee2cb"
GOAL = ".runtime-proof/root-goals/mission"
EVIDENCE = ".runtime-proof/benchmark"


@dataclass(frozen=True)
class Case:
    id: str
    expect: str
    stage: str
    oracle: str
    diagnostic: str = ""


CASES = (
    Case("complete-intake", "accept", "init", "A complete evidence-backed plan can be registered."),
    Case("unresolved-edge", "reject", "init", "An unanswered signed integer edge case prevents planning.",
         r"signed-input edge resolution"),
    Case("unsupported-decision", "reject", "init", "A consequential decision without source evidence prevents planning.",
         r"json-result: evidence is required"),
    Case("stale-intake-evidence", "reject", "init", "Changed bytes invalidate a previously cited evidence file.",
         r"evidence changed: behavior-contract\.txt"),
    Case("missing-prompt", "reject", "init", "An implementation node without a portable prompt prevents planning.",
         r"prompt"),
    Case("missing-qa-mapping", "reject", "init", "Every implementation node must have an independent QA assignment.",
         r"review|tester|qa"),
    Case("overlapping-writes", "reject", "init", "Conflicting unordered write scopes prevent plan admission.",
         r"conflict|overlap"),
    Case("parallel-claims", "accept", "claim", "Both disjoint ready tasks can hold live leases at the same time."),
    Case("valid-handoff", "accept", "handoff", "Fresh runtime evidence with matching task and invocation metadata can be handed off."),
    Case("missing-invocation", "reject", "handoff", "A handoff without recorded host invocation provenance is rejected.",
         r"actual native host invocation ID"),
    Case("self-qa", "reject", "review", "An implementer cannot act as the tester of its own output.",
         r"different host worker from each reviewed implementer"),
    Case("wrong-runtime-value", "reject", "run-check", "An actual exit-zero CLI response of 13 fails an independent oracle of 12.",
         r"assertion .*failed"),
)

APP = """import json
import sys
from addition import calculate as add
from multiplication import calculate as multiply
operation, a, b = sys.argv[1:]
operations = {'add': add, 'multiply': multiply}
print(json.dumps({'result': operations[operation](int(a), int(b))}))
"""

REQUEST = (
    "Return the exact signed integer sum through the public CLI.\n"
    "Return the exact signed integer product through the public CLI.\n"
    "Verify the combined behavior on the final implementation.\n"
)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference(root, path):
    return {"path": path.relative_to(root).as_posix(), "sha256": sha(path)}


def tree_identity(root):
    files = [root / "VERSION", *sorted((root / "scripts").glob("*.py")), root / "examples/cli-contract.json"]
    files.extend(sorted((root / "assets/templates").glob("*.json")))
    return strict_io.digest([reference(root, path) for path in files])


def parse_stdout(raw):
    """The check command emits both a check summary and its final receipt."""
    decoder = json.JSONDecoder()
    if raw.startswith("RUN "):
        raw = raw.partition("\n")[2]
    remaining, parsed = raw.lstrip(), []
    while remaining:
        try:
            value, offset = decoder.raw_decode(remaining)
        except ValueError:
            return None
        parsed.append(value)
        remaining = remaining[offset:].lstrip()
    return parsed[-1] if parsed and isinstance(parsed[-1], dict) else None


class FixtureError(Exception):
    pass


class Trial:
    def __init__(self, project, checkout, protocol):
        self.project = project
        self.checkout = checkout
        self.protocol = protocol
        self.transcript = []
        project.mkdir(parents=True)
        self.environment = {**os.environ, "HARRTEST_STATE_HOME": str(project / "memory")}

    def command(self, script, *args):
        started = subprocess.run(
            [sys.executable, "-S", "-B", str(self.checkout / "scripts" / script), *args],
            cwd=self.project, env=self.environment, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        parsed = parse_stdout(started.stdout)
        public_args = [
            "<lease-token>" if index and args[index - 1] == "--token" else arg
            for index, arg in enumerate(args)
        ]
        safe_stdout = started.stdout
        if parsed and "token" in parsed:
            safe_stdout = safe_stdout.replace(parsed["token"], "<lease-token>")
        entry = {"script": script, "args": public_args, "exit_code": started.returncode,
                 "stdout": safe_stdout, "stderr": started.stderr}
        self.transcript.append(entry)
        return entry, parsed

    def workflow(self, command, *args):
        return self.command("workflow.py", "--project", ".", command, *args)

    def setup(self):
        for name, source in {
            "tool_cli.py": APP,
            "addition.py": "def calculate(a, b):\n    return a + b\n",
            "multiplication.py": "def calculate(a, b):\n    return a * b\n",
            "check_combined.py": (
                "import json, subprocess, sys\n"
                "for op, a, b, expected in [('add', 7, 5, 12), ('add', -4, 0, -4), "
                "('multiply', 7, 5, 35), ('multiply', -4, 0, 0)]:\n"
                "    output = subprocess.check_output([sys.executable, '-B', 'tool_cli.py', op, str(a), str(b)])\n"
                "    assert json.loads(output) == {'result': expected}, output\n"
                "print(json.dumps({'verified_cases': 4}))\n"
            ),
        }.items():
            (self.project / name).write_text(source, encoding="utf-8")
        request = self.project / "request.txt"
        request.write_text(REQUEST, encoding="utf-8")
        require_ok(self.command("root_gate.py", "init", "--project", ".", "--id", "mission",
                                "--request-file", request.name)[0], "root initialization")
        original = self.project / GOAL / "original-request.txt"
        tasks = [
            {"id": "sum", "role": "implement", "depends_on": [], "write_scope": ["addition.py"],
             "read_scope": ["tool_cli.py"], "execution": "subagent",
             "outcome": "Return the exact signed integer sum.",
             "prompt": "Work in addition.py. Preserve the public CLI and verify the integer sum."},
            {"id": "product", "role": "implement", "depends_on": [], "write_scope": ["multiplication.py"],
             "read_scope": ["tool_cli.py"], "execution": "subagent",
             "outcome": "Return the exact signed integer product.",
             "prompt": "Work in multiplication.py. Preserve the public CLI and verify the integer product."},
            {"id": "qa", "role": "review", "reviews": ["sum", "product"], "depends_on": ["sum", "product"],
             "write_scope": [], "read_scope": ["addition.py", "multiplication.py", "tool_cli.py", "check_combined.py"],
             "execution": "subagent", "outcome": "Independently test both CLI operations after handoff.",
             "prompt": "Read the CLI contract and verify both independent results through the public command."},
            {"id": "integration", "role": "integrate", "depends_on": ["qa"], "write_scope": [],
             "read_scope": ["addition.py", "multiplication.py", "tool_cli.py", "check_combined.py"],
             "execution": "serial", "outcome": "Verify the complete CLI behavior after QA.",
             "prompt": "Execute the integrated check against the final CLI source, including zero and negative operands."},
        ]
        root_requirements = []
        for rid, excerpt, children in zip(("SUM", "PRODUCT", "COMBINED"), REQUEST.splitlines(),
                                           (("sum",), ("product",), ("qa", "integration"))):
            root_requirements.append({
                "id": rid, "claim": excerpt, "source": "user_request", "source_excerpt": excerpt,
                "oracle": "Compare the JSON public CLI response with independently declared literal integers.",
                "evidence_mode": "live",
                "satisfiers": [{"task_id": tid, "requirement_id": "R01"} for tid in children],
            })
        root = {
            "schema": 3, "goal_id": "mission", "protocol": "golden-v1",
            "request_sha256": sha(original), "requirements": root_requirements,
            "scope_statement": "Deterministic arithmetic fixture for local workflow decisions.",
            "coverage_review": {"method": "same-agent", "unmapped_segments": [],
                                "rationale": "This authored fixture maps both CLI operations and their combined behavior."},
            "integration": {"task_id": "integration", "requirement_id": "R01",
                            "scope": "Independent process calls of both public CLI operations."},
        }
        offset, segments = 0, []
        for line, requirement in zip(REQUEST.splitlines(keepends=True), root_requirements):
            segments.append({"start": offset, "end": offset + len(line), "kind": "requirement",
                             "requirement_ids": [requirement["id"]]})
            offset += len(line)
        challenge = self.project / GOAL / "fixture-coverage-challenge.json"
        save(challenge, {
            "request_sha256": sha(original), "segments_sha256": strict_io.digest(segments),
            "acceptance_sha256": strict_io.digest({"requirements": root_requirements, "integration": root["integration"]}),
            "method": "fresh-context-agent", "reviewer": "fixture-reviewer", "planner": "fixture-planner",
            "unresolved_findings": [], "verdict": "covered",
            "observations": "Synthetic fixture metadata exercises the schema without claiming a live coverage review.",
        })
        root.update(request_segments=segments, coverage_challenge={"file": challenge.name, "sha256": sha(challenge)})
        save(self.project / GOAL / "root-contract.json", root)
        require_ok(self.command("root_gate.py", "seal", "--goal", GOAL)[0], "root seal")
        for task in tasks:
            task["proof_task"] = ".runtime-proof/" + task["id"]
            task["context_files"] = task["read_scope"]
            self.seal_child(task)
        facts = self.project / "behavior-contract.txt"
        facts.write_text(
            "Signed integer inputs are exact. Zero and negatives are valid for both operations. "
            "The CLI returns one JSON object with an integer result. "
            "The combined smoke executes both operations in separate processes.\n",
            encoding="utf-8",
        )
        refs = [reference(self.project, facts)]
        ids = [r["id"] for r in root_requirements]
        self.intake = {
            "schema": 1, "request_sha256": sha(original),
            "interpretation": "The fixture exposes two independent integer operations and a combined acceptance check.",
            "requirements": [{"id": row["id"], "meaning": row["claim"], "evidence": refs}
                             for row in root_requirements],
            "edge_cases": [
                {"id": "signed-input", "requirement_ids": ids,
                 "question": "Must each operation accept zero and negative operands?",
                 "resolution": "Both operations accept zero and negative operands as exact integers.",
                 "source": "repository_contract", "evidence": refs},
            ],
            "decisions": [
                {"id": "json-result", "requirement_ids": ids,
                 "choice": "Keep the existing JSON result contract and integer precision.",
                 "rationale": "The repository behavior contract specifies integer outputs and a shared JSON field.",
                 "evidence": refs},
            ],
        }
        self.plan = {
            "schema": 1, "goal_id": "mission", "root_goal": GOAL, "tasks": tasks,
            "golden": {"intake": EVIDENCE + "/intake.json", "protocol": EVIDENCE + "/protocol.json",
                       "measurement": EVIDENCE + "/measurement.json"},
        }
        save(self.project / self.plan["golden"]["protocol"], self.protocol)

    def seal_child(self, task):
        tid = task["id"]
        proof_task = task["proof_task"]
        require_ok(self.command("proof.py", "init", "--project", ".", "--id", tid,
                                "--goal", task["outcome"], "--kind", "cli",
                                "--root-goal", "mission", "--detached")[0], "child initialization")
        contract = strict_io.load(ROOT / "examples/cli-contract.json")
        contract.update(task_id=tid, goal=task["outcome"], source_paths=task["read_scope"] + task["write_scope"])
        check = contract["checks"][0]
        if tid in {"sum", "product"}:
            action, expected = ("add", 12) if tid == "sum" else ("multiply", 35)
            command = ["tool_cli.py", action, "7", "5"]
            pointer = "/result"
        else:
            command, pointer, expected = ["check_combined.py"], "/verified_cases", 4
        check.update(command=["{python}", "-B", *command],
                     assertions=[{"type": "json", "file": "stdout.log", "pointer": pointer,
                                  "op": "eq", "value": expected}])
        contract["requirements"][0].update(claim=task["outcome"],
                                           oracle="Compare parsed JSON with fixed independent expected integers.")
        save(self.project / proof_task / "contract.json", contract)
        require_ok(self.command("proof.py", "seal", "--task", proof_task)[0], "child seal")

    def initialize(self, case):
        if case.id == "unresolved-edge":
            self.intake["edge_cases"][0]["resolution"] = ""
        if case.id == "unsupported-decision":
            self.intake["decisions"][0]["evidence"] = []
        if case.id == "stale-intake-evidence":
            (self.project / "behavior-contract.txt").write_text("Changed after the recorded decision.", encoding="utf-8")
        if case.id == "missing-prompt":
            self.plan["tasks"][0].pop("prompt")
        if case.id == "missing-qa-mapping":
            self.plan["tasks"][2]["reviews"] = ["product"]
        if case.id == "overlapping-writes":
            self.plan["tasks"][1]["write_scope"].append("addition.py")
        save(self.project / self.plan["golden"]["intake"], self.intake)
        save(self.project / "plan.json", self.plan)
        return self.workflow("init", "--plan", "plan.json")[0]

    def claim(self, task, worker):
        entry, lease = self.workflow("claim", "--goal", "mission", "--task", task, "--worker", worker,
                                     "--lease-seconds", "90")
        if lease and entry["exit_code"] == 0:
            lease["started_at"] = datetime.now(timezone.utc).isoformat()
        return entry, lease

    def run_check(self, lease):
        return self.workflow("run-check", "--goal", "mission", "--task", lease["task"],
                             "--token", lease["token"], "--check", "addition")[0]

    def handoff(self, lease, case):
        task = lease["task"]
        receipt_file = self.project / ".runtime-proof" / task / "latest/addition.json"
        receipt = strict_io.load(receipt_file)
        run = self.project / ".runtime-proof" / task / receipt["run"]
        actual = strict_io.load(run / "stdout.log")["result"]
        invocation = "local-fixture-" + task + "-" + sha(receipt_file)[:16]
        trace = self.project / EVIDENCE / (task + "-trace.json")
        times = {"started_at": lease["started_at"], "finished_at": datetime.now(timezone.utc).isoformat()}
        save(trace, {"kind": "deterministic fixture, no model execution",
                     "worker_id": lease["owner"], "invocation_id": invocation,
                     "packet_sha256": lease.get("packet_sha256"),
                     "observed": actual, "receipt": reference(self.project, run / "receipt.json"), **times})
        record = {"task_id": task, "generation": lease["generation"], "worker_id": lease["owner"],
                  "packet_sha256": lease.get("packet_sha256"),
                  "invocation_id": invocation, "trace": trace.relative_to(self.project).as_posix(),
                  "decisions": [{"id": "integer-exactness",
                                 "choice": "Preserve exact signed integer arithmetic.",
                                 "rationale": "The checked contract permits signed inputs and requires integer output.",
                                 "evidence": [reference(self.project, self.project / "behavior-contract.txt")]}],
                  "observations": {"addition": {
                      "expected": "The JSON result is " + ("12." if task == "sum" else "35."),
                      "observed": f"The actual process emitted the integer {actual} in the result field."}}, **times}
        if case.id == "missing-invocation":
            record.pop("invocation_id")
        handoff = EVIDENCE + "/" + task + "-handoff.json"
        save(self.project / handoff, record)
        return self.workflow("handoff", "--goal", "mission", "--task", task,
                             "--token", lease["token"], "--evidence", handoff)[0]

    def execute(self, case):
        initialized = self.initialize(case)
        if case.stage == "init":
            return initialized
        require_ok(initialized, "workflow init")
        first, sum_lease = self.claim("sum", "fixture-sum-worker")
        require_ok(first, "first worker claim")
        if case.stage == "claim":
            second, _ = self.claim("product", "fixture-product-worker")
            require_ok(second, "independent product claim")
            status, state = self.workflow("status", "--goal", "mission")
            require_ok(status, "read back overlapping live leases")
            running = {row["id"] for row in state["tasks"] if row["state"] == "RUNNING" and not row["lease_expired"]}
            if running != {"sum", "product"}:
                raise FixtureError("Expected both independent workers to hold live leases simultaneously")
            return second
        if case.id == "wrong-runtime-value":
            (self.project / "addition.py").write_text("def calculate(a, b):\n    return a + b + 1\n", encoding="utf-8")
        checked = self.run_check(sum_lease)
        if case.stage == "run-check":
            latest = strict_io.load(self.project / ".runtime-proof/sum/latest/addition.json")
            run = self.project / ".runtime-proof/sum" / latest["run"]
            receipt = strict_io.load(run / "receipt.json")
            actual = strict_io.load(run / "stdout.log")
            if receipt["exit_code"] != 0 or actual != {"result": 13}:
                raise FixtureError("Negative runtime control must exit zero and return the deliberately incorrect integer 13")
            return checked
        require_ok(checked, "real sum check")
        handed_off = self.handoff(sum_lease, case)
        if case.stage == "handoff":
            return handed_off
        require_ok(handed_off, "sum handoff")
        self.mark_verified("sum")
        require_ok(self.workflow("verify", "--goal", "mission", "--task", "sum")[0],
                   "sum verification")
        second, product_lease = self.claim("product", "fixture-product-worker")
        require_ok(second, "second worker claim")
        require_ok(self.run_check(product_lease), "real product check")
        require_ok(self.handoff(product_lease, case), "product handoff")
        self.mark_verified("product")
        require_ok(self.workflow("verify", "--goal", "mission", "--task", "product")[0],
                   "product verification")
        return self.claim("qa", "fixture-sum-worker")[0]

    def mark_verified(self, task):
        require_ok(self.command("proof.py", "step", "--task", ".runtime-proof/" + task,
                                "--id", "T01", "--status", "VERIFIED", "--note",
                                "The actual public CLI check observed the expected integer result.")[0],
                   "sealed plan progress")


def require_ok(entry, stage):
    if entry["exit_code"] != 0:
        raise FixtureError(stage + ": " + (entry["stderr"] or entry["stdout"]).strip())


def run_trial(case, variant, checkout, output, protocol):
    trial = Trial(output / variant / case.id, checkout, protocol)
    result, classification = None, "error"
    try:
        trial.setup()
        result = trial.execute(case)
        if result["exit_code"] == 0 and parse_stdout(result["stdout"]):
            classification = "accept"
        elif (result["exit_code"] in {1, 2} and case.diagnostic
              and re.search(case.diagnostic, result["stderr"] + result["stdout"], re.I)):
            classification = "reject"
        detail = "" if classification != "error" else "Unrecognized outcome at measured workflow boundary"
    except (FixtureError, KeyError, ValueError, OSError, subprocess.TimeoutExpired) as exc:
        detail = str(exc)
    log = trial.project / "attempt.json"
    save(log, {"case": case.id, "variant": variant, "expect": case.expect, "outcome": classification,
               "observed": result, "detail": detail, "transcript": trial.transcript})
    return {"case": case.id, "variant": variant, "outcome": classification,
            "detail": detail, "evidence": reference(output, log)}


def summarize(attempts):
    expected = {case.id: case.expect for case in CASES}
    results = {}
    for variant in ("baseline", "candidate"):
        rows = {r["case"]: r["outcome"] for r in attempts if r["variant"] == variant}
        results[variant] = {
            "assigned": len(expected),
            "correct": sum(rows.get(cid) == wanted for cid, wanted in expected.items()),
            "false_accepts": sum(rows.get(cid) == "accept" and wanted == "reject" for cid, wanted in expected.items()),
            "false_blocks": sum(rows.get(cid) == "reject" and wanted == "accept" for cid, wanted in expected.items()),
            "errors_or_missing": sum(rows.get(cid) not in {"accept", "reject"} for cid in expected),
        }
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=DEFAULT_BASELINE, help="Local Git ref to archive (default: v3.2.2 commit).")
    parser.add_argument("--output", type=Path, required=True, help="New directory for attempts and report.")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    baseline_ref = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", args.baseline + "^{commit}"], cwd=ROOT, text=True,
    ).strip()
    archive = output / "baseline.zip"
    subprocess.run(["git", "archive", "--format=zip", "-o", str(archive), baseline_ref], cwd=ROOT, check=True)
    baseline = output / "baseline-source"
    with zipfile.ZipFile(archive) as files:
        files.extractall(baseline)
    baseline_identity = tree_identity(baseline)
    candidate_identity = tree_identity(ROOT)
    protocol = {
        "schema": 1, "mode": "fixture",
        "controls": {"runner": "Same benchmark fixture, subprocess commands, and independent literal oracles.",
                     "environment": platform.platform() + " / Python " + platform.python_version()},
        "baseline": {"id": baseline_ref, "source_sha256": baseline_identity},
        "cases": [{"id": case.id, "expect": case.expect, "oracle": case.oracle} for case in CASES],
        "thresholds": {"min_candidate_correct": len(CASES), "max_candidate_false_accepts": 0,
                       "min_correct_gain": 1},
    }
    save(output / "protocol.json", protocol)
    variants = {"baseline": (baseline, baseline_identity), "candidate": (ROOT, candidate_identity)}
    attempts = []
    for case in CASES:
        for variant, (checkout, identity) in variants.items():
            record = run_trial(case, variant, checkout, output, protocol)
            attempts.append({**record, "source_sha256": identity})
            print(f"{case.id:24} {variant:9} {record['outcome']}", flush=True)
    summary = summarize(attempts)
    candidate, before = summary["candidate"], summary["baseline"]
    stable_source = tree_identity(ROOT) == candidate_identity
    bounds = protocol["thresholds"]
    passed = (stable_source and not (candidate["errors_or_missing"] or before["errors_or_missing"])
              and candidate["correct"] >= bounds["min_candidate_correct"]
              and candidate["false_accepts"] <= bounds["max_candidate_false_accepts"]
              and candidate["correct"] - before["correct"] >= bounds["min_correct_gain"])
    report = {"schema": 1, "evidence_class": "deterministic-fixture",
              "protocol_sha256": strict_io.digest(protocol), "baseline": protocol["baseline"],
              "candidate": {"version": (ROOT / "VERSION").read_text(encoding="utf-8").strip(),
                            "source_sha256": candidate_identity},
              "source_unchanged_during_run": stable_source,
              "summary": summary, "passed": passed, "attempts": attempts}
    save(output / "report.json", report)
    print(json.dumps({"passed": passed, "summary": summary, "report": str(output / "report.json")}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
