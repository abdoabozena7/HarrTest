#!/usr/bin/env python3
"""HarrTest v2 root-goal verification: a passing child never closes the mission."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import sys
import proof

ROOT_DIR = "root-goals"
MODES = {"live", "offline", "replay", "fixture"}


def root_dir(project: Path, goal_id: str) -> Path:
    proof.identifier(goal_id, "goal_id")
    return project.resolve() / proof.STATE / ROOT_DIR / goal_id


def validate(project: Path, goal: Path, contract: dict) -> None:
    if not isinstance(contract, dict) or contract.get("schema") != 2:
        raise proof.ProofError("Root contract must have schema=2")
    if contract.get("goal_id") != goal.name:
        raise proof.ProofError("Root ID mismatch")
    original_file = goal / "original-request.txt"
    if not original_file.is_file():
        raise proof.ProofError("Original user request snapshot missing")
    original = original_file.read_text(encoding="utf-8")
    proof.meaningful(original, "original user request", 15)
    if proof.file_hash(original_file) != contract.get("request_sha256"):
        raise proof.ProofError("Root user request was modified or replaced")
    proof.meaningful(contract.get("scope_statement"), "root scope", 20)
    review = contract.get("coverage_review")
    if not isinstance(review, dict) or review.get("method") not in {"human", "fresh-context-agent", "same-agent"}:
        raise proof.ProofError("Root scope coverage review must state actual independence")
    proof.meaningful(review.get("rationale"), "root scope review", 35)
    if review.get("unmapped_segments") != []:
        raise proof.ProofError("The original request has unmapped segments")
    requirements = contract.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise proof.ProofError("The root requires nonempty original requirements")
    identities = set()
    all_links = set()
    for row in requirements:
        if not isinstance(row, dict):
            raise proof.ProofError("Malformed root requirement")
        rid = row.get("id")
        proof.identifier(rid, "root requirement")
        if rid in identities:
            raise proof.ProofError("Duplicate root requirement")
        identities.add(rid)
        proof.meaningful(row.get("claim"), rid + " claim")
        proof.meaningful(row.get("oracle"), rid + " oracle")
        excerpt = row.get("source_excerpt")
        proof.meaningful(excerpt, rid + " original source excerpt", 3)
        source = row.get("source")
        if source == "user_request":
            if excerpt not in original:
                raise proof.ProofError(rid + " excerpt absent from original user request")
        elif source == "repository_contract":
            src = proof.relative_file(project, row.get("source_path") or "")
            if not src.is_file() or src.stat().st_size > 2_000_000:
                raise proof.ProofError(rid + " invalid project acceptance contract path")
            if proof.file_hash(src) != row.get("source_sha256"):
                raise proof.ProofError(rid + " authoritative source changed since root binding")
            if excerpt not in src.read_text(encoding="utf-8"):
                raise proof.ProofError(rid + " missing authoritative excerpt")
        else:
            raise proof.ProofError(rid + " missing source provenance")
        if row.get("evidence_mode") not in MODES:
            raise proof.ProofError(rid + " invalid evidence mode")
        satisfiers = row.get("satisfiers")
        if not isinstance(satisfiers, list) or not satisfiers:
            raise proof.ProofError(rid + " has no required child evidence")
        local = set()
        for item in satisfiers:
            if not isinstance(item, dict):
                raise proof.ProofError(rid + " invalid satisfier")
            task_id, req_id = item.get("task_id"), item.get("requirement_id")
            proof.identifier(task_id, "child task")
            proof.identifier(req_id, "child requirement")
            if task_id == goal.name or (task_id, req_id) in local:
                raise proof.ProofError(rid + " invalid/duplicate child mapping")
            local.add((task_id, req_id))
            all_links.add((task_id, req_id))
    integration = contract.get("integration")
    if not isinstance(integration, dict):
        raise proof.ProofError("Root needs a final integration acceptance child")
    task_id, req_id = integration.get("task_id"), integration.get("requirement_id")
    proof.identifier(task_id, "integration task")
    proof.identifier(req_id, "integration requirement")
    proof.meaningful(integration.get("scope"), "integrated acceptance scope", 20)
    if (task_id, req_id) not in all_links:
        raise proof.ProofError("Final integration is not linked to a root requirement")


def mode_satisfies(required: str, actual: str) -> bool:
    return actual == required or (required == "offline" and actual == "live")


def check_root(goal: Path) -> dict:
    goal = goal.resolve()
    project = goal.parents[2]
    errors = []
    details = []
    try:
        contract = proof.load(goal / "root-contract.json")
        validate(project, goal, contract)
        sealed = proof.load(goal / "root-seal.json")
        if (sealed.get("root_hash") != proof.digest(contract) or
            sealed.get("request_sha256") != contract["request_sha256"] or not sealed.get("sealed_at")):
            raise proof.ProofError("Root contract/request changed after sealing; do not narrow the original goal")
        children = {}
        for row in contract["requirements"]:
            failures = []
            for link in row["satisfiers"]:
                tid, rid = link["task_id"], link["requirement_id"]
                try:
                    path = proof.relative_file(project / proof.STATE, tid)
                    if not path.is_dir() or tid in {ROOT_DIR, "active.json"}:
                        raise proof.ProofError("Required child task is missing")
                    if tid not in children:
                        children[tid] = (proof.load(path / "contract.json"), proof.verify(path))
                    child, outcome = children[tid]
                    if child.get("task_id") != tid:
                        raise proof.ProofError("Child identity mismatch")
                    requirement = next((r for r in child["requirements"] if r["id"] == rid), None)
                    if requirement is None:
                        raise proof.ProofError("Required child requirement is missing")
                    matching = [c for c in child["checks"] if c["id"] in requirement["checks"] and
                                c["role"] == "acceptance" and mode_satisfies(row["evidence_mode"], c["mode"])]
                    if not matching:
                        raise proof.ProofError("Child evidence does not satisfy root evidence mode")
                    if not outcome["passed"] or not any(x["id"] == rid and x["passed"] for x in outcome["requirements"]):
                        raise proof.ProofError("Child proof/plan is failed, incomplete, or stale")
                    # Do not permit a root invented after a successful smoke to claim that old run.
                    for child_check in matching:
                        latest = proof.load(path / "latest" / (child_check["id"] + ".json"))
                        receipt = proof.load(path / latest["run"] / "receipt.json")
                        if dt.datetime.fromisoformat(receipt["started_at"]) < dt.datetime.fromisoformat(sealed["sealed_at"]):
                            raise proof.ProofError("Child execution predates the sealed root goal")
                except (proof.ProofError, KeyError, OSError, ValueError, TypeError) as exc:
                    failures.append(tid + "/" + rid + ": " + str(exc))
            details.append({"id": row["id"], "claim": row["claim"], "passed": not failures, "errors": failures})
            errors.extend(row["id"] + ": " + item for item in failures)
        integration = contract["integration"]["task_id"]
        if integration not in children or not children[integration][1]["passed"]:
            errors.append("Final integrated acceptance is unverified")
        return {"schema": 2, "goal_id": contract["goal_id"],
                "root_status": "ROOT_GOAL_VERIFIED" if not errors else "ROOT_GOAL_UNVERIFIED",
                "root_goal_achieved": not errors,
                "request_sha256": contract["request_sha256"],
                "contract_hash": proof.digest(contract),
                "requirements": details,
                "verified_children": [k for k, v in children.items() if v[1]["passed"]],
                "errors": errors,
                "limitation": "Mechanical coverage of a sealed scope does not prove the completeness or validity of self-authored natural-language oracles."}
    except (proof.ProofError, KeyError, OSError, TypeError, ValueError) as exc:
        return {"schema": 2, "goal_id": goal.name, "root_status": "ROOT_GOAL_UNVERIFIED",
                "root_goal_achieved": False, "requirements": details, "errors": [str(exc)]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init")
    init.add_argument("--project", type=Path, required=True)
    init.add_argument("--id", required=True)
    init.add_argument("--request-file", type=Path, required=True)
    seal = commands.add_parser("seal")
    seal.add_argument("--goal", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--goal", type=Path, required=True)
    verify.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    try:
        if args.action == "init":
            project = args.project.resolve()
            goal = root_dir(project, args.id)
            request = args.request_file.read_text(encoding="utf-8")
            proof.meaningful(request, "exact original request", 15)
            goal.mkdir(parents=True, exist_ok=False)
            (goal / "original-request.txt").write_text(request, encoding="utf-8")
            print(json.dumps({"goal": str(goal),
                              "request_sha256": proof.file_hash(goal / "original-request.txt"),
                              "status": "ROOT_GOAL_UNVERIFIED"}))
            return 0
        goal = args.goal.resolve()
        if args.action == "seal":
            c = proof.load(goal / "root-contract.json")
            validate(goal.parents[2], goal, c)
            proof.save(goal / "root-seal.json",
                       {"root_hash": proof.digest(c), "request_sha256": c["request_sha256"],
                        "sealed_at": proof.now()}, exclusive=True)
            print("Root goal sealed. Child tests cannot redefine original requirements.")
            return 0
        result = check_root(goal)
        if args.write_report:
            proof.save(goal / "root-gate.json", result)
        print(json.dumps(result, indent=2))
        return 0 if result["root_goal_achieved"] else 1
    except (proof.ProofError, ValueError, OSError, KeyError, TypeError) as exc:
        print("ROOT_GOAL_UNVERIFIED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
