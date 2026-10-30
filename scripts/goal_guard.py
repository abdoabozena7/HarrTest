#!/usr/bin/env python3
"""Strict, read-only journey/evidence audit for HarrTest.

Checks a frozen declared goal inventory against *reported* observable steps.
It cannot authenticate a self-written oracle or replace actual runtime checks,
inspected artifacts, proof.py receipts, or root_gate.py verification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

HEX = re.compile(r"^[a-f0-9]{64}$")
LABEL = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$")
MODES = {"live", "offline", "replay", "fixture"}
STATES = {"PASS", "FAIL", "PENDING", "NOT_RUN", "UNAVAILABLE"}


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fd:
        for block in iter(lambda: fd.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def _path(root: Path, value: str) -> Path:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise ValueError("evidence path must be nonempty and relative")
    rel = Path(value)
    if rel.is_absolute() or any(x in {"..", "."} for x in rel.parts):
        raise ValueError("evidence path escapes the selected evidence root")
    candidate = root / rel
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("evidence path resolves outside root")
    node = candidate
    while node != root:
        if node.is_symlink():
            raise ValueError("symlink evidence is not accepted")
        node = node.parent
    if not candidate.is_file():
        raise ValueError("evidence file missing")
    return candidate


def _label(value, what):
    if not isinstance(value, str) or not LABEL.fullmatch(value):
        raise ValueError(f"invalid {what}: {value!r}")
    return value


def _sha(value, what):
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise ValueError(f"invalid {what}: expected lowercase sha256")
    return value


def assess(contract: dict, events_doc: dict, evidence_root: Path, root_contract: dict | None = None) -> dict:
    """Fail closed; a newer incomplete run cannot inherit an older success.

    A later complete valid PASS run may supersede an earlier FAIL. Individual
    steps from different runs must never be combined into a passing journey.
    """
    problems, rows = [], []
    try:
        if not isinstance(contract, dict) or contract.get("schema") != 1:
            raise ValueError("expected goal-guard contract schema 1")
        if contract.get("scope") not in {"child", "root"}:
            raise ValueError("scope must be child or root")
        source = _sha(contract.get("source_sha256"), "source_sha256")
        reqs = contract.get("requirements")
        if not isinstance(reqs, list) or not reqs:
            raise ValueError("requirements must be nonempty")
        specs = {}
        ids = set()
        for req in reqs:
            if not isinstance(req, dict):
                raise ValueError("malformed requirement")
            rid = _label(req.get("id"), "requirement id")
            if rid in ids:
                raise ValueError("duplicate requirement id")
            ids.add(rid)
            target = req.get("target")
            if not isinstance(target, str) or not target.strip():
                raise ValueError(f"{rid}: target required")
            if req.get("mode") not in MODES:
                raise ValueError(f"{rid}: unsupported evidence mode")
            journeys = req.get("journeys")
            if not isinstance(journeys, list) or not journeys:
                raise ValueError(f"{rid}: journeys required")
            for journey in journeys:
                if not isinstance(journey, dict):
                    raise ValueError(f"{rid}: malformed journey")
                jid = _label(journey.get("id"), "journey id")
                steps = journey.get("steps")
                if not isinstance(steps, list) or not steps or any(not isinstance(step, str) or not LABEL.fullmatch(step) for step in steps) or len(steps) != len(set(steps)):
                    raise ValueError(f"{rid}/{jid}: steps must be unique named observable checks")
                key = (rid, jid)
                if key in specs:
                    raise ValueError(f"duplicate journey {rid}/{jid}")
                specs[key] = {"target": target, "mode": req["mode"], "steps": steps}
        if contract["scope"] == "root":
            if not isinstance(root_contract, dict) or root_contract.get("schema") != 2:
                raise ValueError("root scope requires a v2 root contract; seal validation is delegated to root_gate.py")
            if _sha(root_contract.get("request_sha256"), "root request hash") != _sha(contract.get("root_request_sha256"), "root_request_sha256"):
                raise ValueError("original root request hash mismatch")
            original_ids = [r.get("id") for r in root_contract.get("requirements", [])]
            if len(original_ids) != len(set(original_ids)) or set(original_ids) != ids:
                raise ValueError("guard does not cover every original root requirement")
        if not isinstance(events_doc, dict) or events_doc.get("schema") != 1 or not isinstance(events_doc.get("events"), list):
            raise ValueError("expected structured event document schema 1")
        runs = {key: {} for key in specs}
        order = {key: [] for key in specs}
        for index, event in enumerate(events_doc["events"]):
            if not isinstance(event, dict):
                problems.append(f"event {index}: invalid object")
                continue
            key = (event.get("requirement_id"), event.get("journey_id"))
            if key not in specs:
                problems.append(f"event {index}: unknown requirement/journey {key}")
                continue
            spec = specs[key]
            run_id = event.get("run_id")
            try:
                _label(run_id, "run_id")
                step = _label(event.get("step_id"), "step_id")
                if step not in spec["steps"]:
                    raise ValueError("unrecognized journey step")
                if event.get("target") != spec["target"] or event.get("mode") != spec["mode"]:
                    raise ValueError("wrong target/mode")
                if event.get("source_sha256") != source:
                    raise ValueError("stale or foreign source")
                state = event.get("status")
                if state not in STATES:
                    raise ValueError("missing or invalid explicit outcome status")
                correct_pass = True if state == "PASS" else False if state == "FAIL" else None
                if event.get("passed", object()) is not correct_pass:
                    raise ValueError("status and passed disagree or are missing")
                _sha(event.get("evidence_sha256"), "evidence hash")
                evidence = _path(evidence_root.resolve(), event.get("evidence_file"))
                if _hash(evidence) != event["evidence_sha256"]:
                    raise ValueError("evidence bytes changed")
                if not isinstance(event.get("observer"), str) or not event["observer"].strip():
                    raise ValueError("missing observer provenance")
                if run_id not in runs[key]:
                    runs[key][run_id] = []
                    order[key].append(run_id)
                elif order[key][-1] != run_id:
                    raise ValueError("noncontiguous run reuse can hide newer failures")
                runs[key][run_id].append((step, state))
            except (KeyError, TypeError, ValueError, OSError) as exc:
                problems.append(f"event {index}: {exc}")
        for key, spec in specs.items():
            if not order[key]:
                errors = ["no evidence run for required journey"]
                last_run = None
            else:
                last_run = order[key][-1]
                selected = runs[key][last_run]
                observed_steps = [s for s, _ in selected]
                errors = []
                if observed_steps != spec["steps"]:
                    errors.append("latest run does not execute every required step in order")
                if any(status != "PASS" for _, status in selected):
                    errors.append("latest run contains non-PASS evidence")
            rows.append({"requirement_id": key[0], "journey_id": key[1], "latest_run": last_run,
                         "passed": not errors, "errors": errors})
    except (ValueError, TypeError, KeyError) as exc:
        problems.append(str(exc))
    for row in rows:
        problems.extend(f"{row['requirement_id']}/{row['journey_id']}: {e}" for e in row["errors"])
    return {"schema": 1, "scope": contract.get("scope") if isinstance(contract, dict) else None,
            "passed": not problems and bool(rows),
            "status": "DECLARED_EVIDENCE_ACCEPTED" if not problems and rows else "UNVERIFIED",
            "journeys": rows, "errors": problems,
            "limitations": "Checks declared evidence structure/bytes, not oracle completeness or observed behavior truth; root_gate.py remains authoritative."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--root-contract", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        contract = json.loads(args.contract.read_text(encoding="utf-8-sig"))
        events = json.loads(args.events.read_text(encoding="utf-8-sig"))
        root = json.loads(args.root_contract.read_text(encoding="utf-8-sig")) if args.root_contract else None
        result = assess(contract, events, args.evidence_root or args.events.parent, root)
    except (OSError, ValueError, TypeError) as exc:
        result = {"schema": 1, "passed": False, "status": "UNVERIFIED", "errors": [f"invalid input: {exc}"]}
    output = args.output
    if not output and os.environ.get("PROVE_IT_OUTPUT_DIR"):
        output = Path(os.environ["PROVE_IT_OUTPUT_DIR"]) / "goal-guard.json"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
