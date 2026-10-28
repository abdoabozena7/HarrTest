# Root Goal Binding — Prove It v2

## Why two verification layers?
A bounded smoke or component test can pass while the original user request remains incomplete. `proof.py verify` reports **CHILD_TASK_ONLY**. The second command `root_gate.py verify` requires sealed original requirements, provenance, valid latest child receipts, correct evidence mode, and an integrated acceptance child.

## Workflow
1. Preserve the **entire original user request**, not an agent-generated summary, in a local file.
2. Run `python scripts/root_gate.py init --project PROJECT --id mission --request-file REQUEST.txt`.
3. Populate `PROJECT/.runtime-proof/root-goals/mission/root-contract.json` from the root template. Anchor every requirement to an exact user-request excerpt, or to a governing repository contract file with current SHA-256.
4. Challenge omissions. The coverage review must list all unmapped segments; don't label coverage complete while any remain. State the real reviewer independence.
5. Link each root requirement to a required child task's sealed acceptance requirement. Set `evidence_mode=live` when real runtime proof is necessary. Include a separate final integration acceptance task.
6. **Before executing children**, `python scripts/root_gate.py seal --goal PROJECT/.runtime-proof/root-goals/mission`.
7. Execute and independently review each child via `proof.py`, then `python scripts/root_gate.py verify --goal PROJECT/.runtime-proof/root-goals/mission --write-report`.

## Root contract
`schema=2`; `goal_id`; `request_sha256`; `scope_statement`; `coverage_review` with `method`, `rationale` and `unmapped_segments=[]`; `requirements` with `id, claim, oracle, source, source_excerpt, evidence_mode, satisfiers`; `integration` with `task_id, requirement_id, scope`. For `source=repository_contract`, include `source_path` and `source_sha256`. A satisfier is `{"task_id":"child","requirement_id":"R01"}`.

## Status semantics
- **IMPLEMENTED:** code present, no behavioral proof implied.
- **VERIFIED_WITHIN_SCOPE:** child requirement and recorded execution validated.
- **ROOT_GOAL_VERIFIED:** all declared source-anchored root requirements and final integration validated with fresh child evidence.
- **ROOT_GOAL_UNVERIFIED:** missing, failed, older, wrong-mode, unsealed, blocked, or stale evidence.

**Example:** A 94-meter CARLA smoke can be a valid live child, while performance, full-route, second mode and held-out acceptance remain unverified. Keep the root status open. A claim of overall success must not depend only on green tests selected by the implementer.

## Limits
The mechanical gate verifies the declared provenance and evidence graph, not semantic completeness of self-written requirements or soundness of an arbitrary self-written test. Independent review of the original request, meaningful external outcomes, and protected verifier access are still necessary. No permissions, simulator budgets or holdout rights are automatically granted.
