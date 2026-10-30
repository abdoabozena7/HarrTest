# Blocked-goal recovery without the audit treadmill

Use only for a **genuinely unfinished goal** and an independently confirmed external blocker (resource limit, authorization requirement, or unavailable host). This is a coordination protocol, not a loophole for protected budgets.

## 1. Check whether anything substantive changed

At each resumed session, inspect the last sealed root, task state, current project source identity, last verified evidence and actual policy/admission status. Avoid rereading every long goal and rerunning all previously conclusive diagnostics if those identities are unchanged. Reuse valid source-bound historical findings for **triage**, not for current-version acceptance. If a prior offline investigation already found *no causally justified fix*, another audit of the same recording without a new falsifiable question is not goal progress.

Before `proof.py init`, inspect the existing active task/session ownership and prefer existing sealed tasks. Never steal `active.json` from an unfinished session or create a new parent whose goal is easier than the original. Preserve prior blocked/failure reports and raw data. When the installed proof scripts change, previous seals and receipts may cease to verify as **current**; this is deliberate integrity behavior, not proof of a new product regression. Do not repeatedly verify with `--write-report` against an old seal and overwrite its previous historical `gate.json`. If necessary, copy or archive the old gate first and run a non-writing verification or a clearly separate audit scope. Never claim old receipts became current merely because the old gate is preserved.

### Interaction-timeout clarification (v2.6)

A failed or timed-out `Ask User` delivery means **the interaction channel
failed**, not that the user is physically absent, has declined, or consented.
Before escalating, classify the question: optional reversible consultation may
be skipped with a recorded autonomous choice; mandatory authorization may NOT
be skipped. When approval is genuinely required, pause only the protected
action, continue other meaningful pre-authorized work, and use
`ACTION_REQUIRED` only if no useful independent work remains. An agent-made
time estimate, slow model response, or optional review timeout is not a
project-wide stop condition; actual policy/host limits still apply.

## 2. Convert a real blocker into a single decision

When the next original native/live step cannot be admitted and no other evidence-supported authorized implementation experiment is ready:

1. Verify the **actual host/source-of-truth** allowance, policy minimum, cleanup reserve and protected budgets. Do not infer authorization from a user goal, an agent-created JSON file or a helpful script.
2. Identify one minimum *meaningful* step and the separate resources needed **for that step**, not the complete mission. Do not assume that the arithmetic minimum is scientifically useful.
3. If the host has a supported `Ask User` tool and the user has not opted out, present **one** succinct, bounded request: action and resource pool, amount/units, where/when valid, unchanged safety/acceptance requirements, and what will be run after approval. Repeated empty answers or old approvals are not consent.
4. Without an interactive user decision, continue other authorized independent work first. When none remains, end with `ACTION_REQUIRED: [specific user grant/host fix]`, `ROOT_GOAL_UNVERIFIED` and a clear choice to approve or decline. The UI's **Task completed** indicator only means the agent turn ended.
5. Do not run protected work until a **new explicit grant** and real project/host admission succeed. On valid grant, resume the next pending original gate; do not repeat an unchanged offline audit for the sake of showing activity.

For optional deterministic communication support, run `python scripts/blocker_handoff.py --current current-blocker.json --previous previous-blocker.json` (omit `--previous` if unknown). This is **read-only**. The JSON input is assembled from independently verified facts, not taken as authority. Its output is a decision *request*, never a permission or a success verdict. A signature over source, evidence, authorization identity, gate and budget detects **unchanged repeated blockers** even when log timestamps differ. A changed signature indicates new input and requires reevaluation, not automatic approval.

Example input (`current-blocker.json`):

```json
{
  "root_goal_id": "original-carla-driving-goal",
  "root_status": "ROOT_GOAL_UNVERIFIED",
  "blocker_kind": "RESOURCE_LIMIT",
  "source_identity": "actual-current-source-id",
  "evidence_identity": "actual-frame-and-evidence-fingerprint",
  "authorization_identity": "actual-current-policy-ledger-version",
  "first_pending_gate": "native diagnostic requalification",
  "required_action": "native diagnostic",
  "authorized_safe_next_step": false,
  "resource_pool": "DIAGNOSTIC",
  "resource_unit": "seconds",
  "available_units": "262.367",
  "minimum_reservation_units": "480",
  "protected_pool": false
}
```

The result's `minimum_extra_for_one_reservation=217.633` is **not** a suggested full project budget and not evidence that an exact additional grant is sufficient for the whole mission. The host may require more execution time for a useful next trial, and any requested larger amount must be justified and authorized explicitly. Do not carry this CARLA number into other projects.

## 3. Evaluate HarrTest itself honestly

Record which **original user-required behaviors** improved on the final executable, not how many files were read or checks were repeated. Success of a bounded offline diagnostic is useful, but it cannot by itself repair a runtime product. For claims of uplift attributable to HarrTest, use a separately authorized, matched no-skill or prior-version evaluation (same goal/source/model/tools/resources/evaluator). Otherwise: `BEHAVIORAL_IMPACT_UNPROVEN`.