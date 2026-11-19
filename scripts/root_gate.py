#!/usr/bin/env python3
"""Verify the original goal, including the Gold protocol when sealed into it."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3
import sys
import proof

ROOT_DIR = "root-goals"
MODES = {"live", "offline", "replay", "fixture"}
REVIEWED_TEAM = 'reviewed-v1'


def root_dir(project: Path, goal_id: str) -> Path:
    proof.identifier(goal_id, "goal_id")
    return project.resolve() / proof.STATE / ROOT_DIR / goal_id


def validate(project: Path, goal: Path, contract: dict) -> None:
    if not isinstance(contract, dict) or contract.get("schema") not in {2, 3, 4}:
        raise proof.ProofError("Root contract must have schema 2, 3 or 4")
    schema = contract['schema']
    if schema == 4:
        if contract.get('protocol') != 'corporate-v1':
            raise proof.ProofError('Schema-4 roots require corporate-v1')
        if 'production_team' not in contract:
            raise proof.ProofError('Corporate root completion requires a bound schema-2 production team')
    elif "protocol" in contract and (schema != 3 or contract["protocol"] != "golden-v1"):
        raise proof.ProofError("Root protocol must be golden-v1 on a schema-3 root")
    if schema != 4 and 'corporate' in contract:
        raise proof.ProofError('Corporate binding requires a schema-4 root')
    if 'team_decomposition' in contract and (schema != 4 or contract['team_decomposition'] != REVIEWED_TEAM):
        raise proof.ProofError('Reviewed Team decomposition requires reviewed-v1 on a schema-4 root')
    if contract.get("goal_id") != goal.name:
        raise proof.ProofError("Root ID mismatch")
    if "production_team" in contract:
        proof.identifier(contract["production_team"], "production team ID")
        if schema not in {3, 4} or contract["production_team"] != contract["goal_id"]:
            raise proof.ProofError("Production team must match the goal ID on a schema-3/4 root")
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

    if schema >= 3:
        import coverage
        coverage.validate(original, contract, goal)
    if schema == 4:
        import corporate
        corporate.validate(project, goal, contract)


def mode_satisfies(required: str, actual: str) -> bool:
    return actual == required or (required == "offline" and actual == "live")


def require_team_sources(project, child, outputs):
    """Ensure the sealed runtime proof fingerprints the exact Team outputs."""
    sources = [proof.relative_file(project, path, must_exist=False) for path in child["source_paths"]]
    for output in sorted(set(outputs)):
        path = proof.relative_file(project, output, must_exist=False)
        if not any(path.is_relative_to(source) for source in sources):
            raise proof.ProofError(f'{child["task_id"]} proof must fingerprint Team output: {output}')


def team_outputs(binding):
    outputs = set(binding["integration_outputs"])
    for contributor in binding["tasks"].values():
        outputs.update(contributor["outputs"])
    return outputs


def reviewed_team_binding(project, contract):
    import team
    import team_v2

    team_id = contract['production_team']
    state = team.load_state(project, team_id)
    plan = state['plan']
    if plan.get('schema') != 2 or plan.get('decomposition') != REVIEWED_TEAM:
        raise proof.ProofError('Corporate root requires a Team plan with reviewed-v1 decomposition')
    team.binding(project, team_id, contract['request_sha256'])
    review = team_v2.approved_decomposition(project, state)
    return {'state_sha256': state['state_sha256'], 'review_sha256': review['sha256']}


def check_production_team(project, contract, sealing):
    import team

    if 'team_decomposition' in contract and sealing.get('reviewed_team') != reviewed_team_binding(project, contract):
        raise proof.ProofError('Team plan, baseline or review differs from the Corporate root seal')
    team_id = contract["production_team"]
    binding = team.binding(project, team_id, contract["request_sha256"])
    if contract['schema'] == 4:
        import corporate

        state = team.load_state(project, team_id)
        if sealing.get('corporate_team_sha256') != state['state_sha256']:
            raise proof.ProofError('Corporate Team state differs from the root seal')
        plan = _corporate_team_scope(project, contract, state, binding)
        baseline = plan['baseline']['source']['files']
        current = corporate.source_snapshot(project, plan['source_paths'])['files']
        owned = {team.product_key(rel) for rel in team_outputs(binding)}
        unowned = sorted(rel for rel in baseline.keys() | current.keys()
                         if baseline.get(rel) != current.get(rel) and team.product_key(rel) not in owned)
        if unowned:
            raise proof.ProofError('Corporate source changed outside sealed Team ownership: '
                                   + ', '.join(unowned[:10]))
    else:
        child_id = contract["integration"]["task_id"]
        path = proof.relative_file(project / proof.STATE, child_id)
        child = proof.load(path / "contract.json")
        require_team_sources(project, child, team_outputs(binding))
    return team.verify_registered(project, team_id, require_qa=True)


def _corporate_team_scope(project, contract, state, binding):
    if state['plan'].get('schema') != 2:
        raise proof.ProofError('Corporate roots require Team schema 2')
    plan = proof.load(proof.relative_file(project, contract['corporate']['plan']))
    expected = {row['id']: (sorted(row['outputs']), sorted(row['depends_on']))
                for row in plan['tasks']}
    actual = {row['id']: (sorted(row['outputs']), sorted(row['depends_on']))
              for row in state['plan']['tasks']}
    if actual != expected:
        raise proof.ProofError('Corporate implementation ownership/dependencies differ from the bound Team')
    outputs = team_outputs(binding)
    roots = [proof.relative_file(project, rel, must_exist=False) for rel in plan['source_paths']]
    for output in outputs:
        target = proof.relative_file(project, output, must_exist=False)
        if not any(target.is_relative_to(root) for root in roots):
            raise proof.ProofError('Corporate verification scope omits Team output: ' + output)
    baseline = plan['baseline']['source']['files']
    if any(baseline.get(rel) != digest for rel, digest in state['baseline'].items()):
        raise proof.ProofError('Team output baseline differs from the Corporate baseline')
    child_id = contract['integration']['task_id']
    task = proof.relative_file(project / proof.STATE, child_id)
    child = proof.load(task / 'contract.json')
    require_team_sources(project, child, outputs)
    return plan


def _corporate_dispatch_inputs(project, contract, state, *, baseline_current):
    import corporate
    import team

    if (contract.get('schema') != 4 or contract.get('protocol') != corporate.PROTOCOL
            or contract.get('production_team') != state['plan']['id']
            or contract.get('team_decomposition') != REVIEWED_TEAM):
        raise proof.ProofError('Corporate dispatch requires the matching reviewed schema-4 root')
    reviewed = reviewed_team_binding(project, contract)
    if reviewed['state_sha256'] != state.get('state_sha256'):
        raise proof.ProofError('Team state differs from the reviewed Corporate dispatch state')
    binding = team.binding(project, state['plan']['id'], contract['request_sha256'])
    plan = _corporate_team_scope(project, contract, state, binding)
    baseline = plan['baseline']['source']
    if baseline_current and (corporate.source_snapshot(project, plan['source_paths']) != baseline
            or team.snapshot(project, state['baseline']) != state['baseline']):
        raise proof.ProofError('Source changed before Corporate dispatch. Preserve the original baseline.')
    return reviewed


def require_corporate_dispatch(project, state, *, baseline_current):
    """Revalidate a substantive Team's root using its frozen inputs and checks."""
    import corporate
    import strict_io
    import team

    project = Path(project).resolve()
    if state['plan'].get('root_protocol') != corporate.PROTOCOL:
        raise proof.ProofError('Corporate dispatch requires the explicit Team root_protocol')
    goal_id = state['plan']['id']
    proof.identifier(goal_id, 'Corporate Team ID')
    try:
        goal = corporate.path(project, f'{proof.STATE}/{ROOT_DIR}/{goal_id}')
        root_path = corporate.path(goal, 'root-contract.json')
        seal_path = corporate.path(goal, 'root-seal.json')
    except ValueError as exc:
        raise proof.ProofError(f'Corporate dispatch needs a sealed schema-4 root for {goal_id}. '
                               'Prepare and review the root, then run root_gate.py seal.') from exc
    contract, seal = corporate.document(root_path), corporate.document(seal_path)
    validate(project, goal, contract)
    if seal.get('root_hash') != proof.digest(contract) or seal.get('request_sha256') != contract['request_sha256']:
        raise proof.ProofError('Corporate dispatch root contract differs from its seal')
    reviewed = _corporate_dispatch_inputs(project, contract, state, baseline_current=baseline_current)
    if (seal.get('reviewed_team') != reviewed
            or seal.get('corporate_team_sha256') != state['state_sha256']):
        raise proof.ProofError('Team plan, baseline or review differs from the Corporate root seal')
    if seal.get('corporate') != corporate.seal_binding(project, goal, contract):
        raise proof.ProofError('Corporate dispatch plan, baseline, checks or verifier differ from the root seal')
    reviewed_receipt = team.current_receipt(project, state, 'plan_review')
    sealed_at = corporate.instant(seal.get('sealed_at'))
    if not corporate.instant(reviewed_receipt['at']) <= sealed_at <= dt.datetime.now(dt.timezone.utc):
        raise proof.ProofError('Corporate dispatch requires a root seal after the Team review')
    return {'root_hash': seal['root_hash'], 'seal_sha256': strict_io.digest(seal),
            'sealed_at': seal['sealed_at'], 'team_state_sha256': reviewed['state_sha256'],
            'team_review_sha256': reviewed['review_sha256']}


def check_root(goal: Path) -> dict:
    goal = goal.resolve()
    project = goal.parents[2]
    errors = []
    details = []
    contract = None
    try:
        contract = proof.load(goal / "root-contract.json")
        validate(project, goal, contract)
        sealed = proof.load(goal / "root-seal.json")
        if (sealed.get("root_hash") != proof.digest(contract) or
            sealed.get("request_sha256") != contract["request_sha256"] or not sealed.get("sealed_at")):
            raise proof.ProofError("Root contract/request changed after sealing; do not narrow the original goal")
        production_team = None
        if "production_team" in contract:
            try:
                production_team = check_production_team(project, contract, sealed)
                if production_team.get("passed") is not True:
                    errors.extend("Production team: " + e for e in
                                  (production_team.get("errors") or ["verification is incomplete"]))
            except (proof.ProofError, KeyError, OSError, ValueError, TypeError, sqlite3.Error) as exc:
                errors.append("Production team: " + str(exc))
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
        gold = None
        if not errors and contract.get("protocol") == "golden-v1":
            try:
                gold = check_gold(project, goal)
            except (proof.ProofError, KeyError, OSError, ValueError, TypeError, sqlite3.Error) as exc:
                errors.append("Gold gate: " + str(exc))
        corporate_result = None
        if contract['schema'] == 4:
            try:
                import corporate
                corporate_result = corporate.check(project, goal, contract)
                if corporate_result.get('passed') is not True:
                    errors.extend('Corporate gate: ' + e for e in
                                  (corporate_result.get('errors') or ['Required quality layers are unverified']))
            except (proof.ProofError, KeyError, OSError, ValueError, TypeError, sqlite3.Error) as exc:
                errors.append('Corporate gate: ' + str(exc))
        return {"schema": contract["schema"], "goal_id": contract["goal_id"],
                "root_status": "ROOT_GOAL_VERIFIED" if not errors else "ROOT_GOAL_UNVERIFIED",
                "root_goal_achieved": not errors,
                "request_sha256": contract["request_sha256"],
                "contract_hash": proof.digest(contract),
                "coverage_assurance": "FULL_TEXT_MAPPED_REVIEW_DECLARED" if contract["schema"] >= 3 else "LEGACY_DECLARED_COVERAGE",
                "requirements": details,
                "verified_children": [k for k, v in children.items() if v[1]["passed"]],
                **({"golden": gold} if contract.get("protocol") == "golden-v1" else {}),
                **({"corporate": corporate_result} if contract['schema'] == 4 else {}),
                **({"production_team": production_team} if "production_team" in contract else {}),
                "errors": errors,
                "limitation": "Mechanical coverage of a sealed scope does not prove the completeness or validity of self-authored natural-language oracles."}
    except (proof.ProofError, KeyError, OSError, TypeError, ValueError) as exc:
        return {"schema": contract.get('schema', 2) if isinstance(contract, dict) else 2,
                "goal_id": goal.name, "root_status": "ROOT_GOAL_UNVERIFIED",
                "root_goal_achieved": False, "requirements": details, "errors": [str(exc)]}


def check_gold(project, goal):
    import strict_io
    import workflow
    from runtime_store import Store

    database = strict_io.scoped_path(project, ".runtime-proof/workflows.sqlite")
    store = Store(database)
    spec = store.goal(goal.name)
    if strict_io.scoped_path(project, spec["root_goal"]) != goal or spec["goal_id"] != goal.name:
        raise ValueError("Workflow belongs to a different original root")
    return workflow.check_golden_root(project, store, spec)


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
    inventory = commands.add_parser("inventory")
    inventory.add_argument("--goal", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == "init":
            project = args.project.resolve()
            goal = root_dir(project, args.id)
            request = args.request_file.read_bytes()
            proof.meaningful(request.decode("utf-8"), "exact original request", 15)
            original = proof.relative_file(project, (goal / "original-request.txt").relative_to(project).as_posix(),
                                           must_exist=False)
            try:
                goal.mkdir(parents=True, exist_ok=False)
            except FileExistsError:
                if not original.is_file() or original.read_bytes() != request:
                    raise proof.ProofError("This goal already exists with a different or missing original request. "
                                           "Keep its evidence and use a new goal ID for a different request.")
                already_initialized = True
            else:
                with original.open("xb") as file:
                    file.write(request)
                already_initialized = False
            print(json.dumps({"goal": str(goal),
                              "request_sha256": proof.file_hash(original),
                              "already_initialized": already_initialized,
                              "status": "ROOT_GOAL_UNVERIFIED"}))
            return 0
        goal = args.goal.resolve()
        if args.action == "inventory":
            import coverage
            request = (goal / "original-request.txt").read_text(encoding="utf-8")
            print(json.dumps({"request_segments": coverage.inventory(request)}, indent=2))
            return 0
        if args.action == "seal":
            c = proof.load(goal / "root-contract.json")
            project = goal.parents[2]
            validate(project, goal, c)
            sealed = {"root_hash": proof.digest(c), "request_sha256": c["request_sha256"]}
            if c['schema'] == 4:
                import corporate
                import team

                state = team.load_state(project, c['production_team'])
                sealed['corporate_team_sha256'] = state['state_sha256']
                reviewed = 'team_decomposition' in c
                if reviewed and state['plan'].get('root_protocol') == 'corporate-v1':
                    sealed['reviewed_team'] = _corporate_dispatch_inputs(project, c, state, baseline_current=True)
                else:
                    binding = team.binding(project, c['production_team'], c['request_sha256'])
                    _corporate_team_scope(project, c, state, binding)
                    if reviewed:
                        sealed['reviewed_team'] = reviewed_team_binding(project, c)
                sealed['corporate'] = corporate.seal_binding(project, goal, c)
            sealed['sealed_at'] = proof.now()
            proof.save(goal / "root-seal.json", sealed, exclusive=True)
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
