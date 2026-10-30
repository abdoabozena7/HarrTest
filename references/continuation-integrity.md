# Continuing existing tasks without creating false success

Use this guide when an agent resumes an existing project, a different session owns the workspace's active harness task, an audit replays recorded data, or a user is evaluating whether a new HarrTest version actually helps.

## 1. Preflight the installed skill and host

Load the `harrtest` skill through the host's real skill mechanism, then run the **read-only** `scripts/version_guard.py --installed PATH` when the user requires latest-only operation and public GitHub is accessible. Require `LATEST_VERIFIED` plus a genuine host invocation. An on-disk match alone does not prove the host invoked the skill. A version number alone is not a match: compare the complete installed source-tree blob identities. The remote authority is the repository's current `main` revision and `VERSION` file, **not** `/releases/latest` (the repository may not publish releases). Record remote revision, installed version, source match, time and any CRLF normalization. Fail closed if the remote cannot be checked, the tree is truncated, or the installation differs. Do not auto-update without explicit user approval; say how to update and restart.

## 2. Resume the correct original task without stealing ownership

Read the original goal and *existing* sealed root contract first. Do not replace the original parent by creating a smaller, easier root contract. When one already exists, verify or resume it; create an additional independent audit binding **only** if required by the current version or original contract format, and preserve the original in parallel. Verify original-root completeness separately.

Before calling `proof.py init`, inspect `.runtime-proof/active.json` and the active task's `context.json`, `blocked.json`, `gate.json` and actual session owner, when present. The current `proof.py init` deliberately refuses to replace an unfinished active task; `--session-id` does not override that protection. If another session has a live unfinished task, never edit its `active.json`, fabricate `blocked.json`, or reassign ownership just to proceed. Prefer explicitly addressed read-only commands against existing task folders, and use a separately scoped, uniquely named audit child only when doing so is permitted by the host/project. If the agent cannot initialize safely, report the collision accurately and stop writes; the original goal remains open. This avoids retrying the same forbidden init command and preserves subagent/resumption integrity.

## 3. Discover evidence schemas and populations before asserting equality

Avoid assumptions such as `archive_count == live_source_count` or `telemetry_rows == driving_decisions`. Inspect actual file manifests, record types, denominators, timestamps, origin/phase/mode labels and hashes. Validate *every file in the declared scope*; a source-specific manifest may legitimately be a strict subset of a fuller archive. Check all shared hashes, enumerate extra or missing entries, and explain each difference; never silently drop unmatched records or accept unverified extras. Different populations can be consistent: for example, 601 driving frames plus 32 hold records can coexist with 633 total controls, but only if identities and phase boundaries prove that partition.

When assessing performance, classify interval boundaries as **disjoint**, **nested**, or **overlapping** before summing. For example, a prediction span already inside `scene_build` or population work inside `before_native` must not be added twice. Distinguish wall-time and thread CPU time. Keep the exact outlier and neighboring frames even if percentiles pass. If a test fails because it confused scopes, preserve the failed receipt, fix the assertion or evidence adapter with proof of semantics, and rerun; do not weaken an original external acceptance threshold.

## 4. Prioritize goal progress over repeated audits

Ask at each milestone: what original required user outcome is now demonstrably improved? Mark **verified diagnosis** separately from **verified product repair**. An offline investigation may legitimately pass as a child while the original goal remains blocked. If a permission/budget ceiling prevents any new real result and available offline evidence cannot resolve the causal hypothesis, stop low-value reruns. Provide one precise unblock request, relevant current-source evidence, and the next authorized action. Extra test counts or a longer report are not goal progress.

## 5. Evaluate a new skill against an independent baseline

To find out whether HarrTest improves coding-agent behavior, compare a HarrTest-enabled run against a **separately authorized no-skill Copilot baseline** or a carefully pinned previous skill release in an evaluation-only fixture. Do not silently run outdated production skills merely for comparison when the user has required latest-only execution. Use the same original request, model, tools, starting repository snapshot, allowed resources, and independent evaluator; run enough independent trials to estimate variability. A single historical session and the latest session are not directly comparable if the project state, model, available tools or resource budgets changed.

Capture for each run: actual loaded version/commit, task start SHA, scope, tool access, real actions attempted, original requirements passed, false success claims, regressions, cost/resource use, and independent runtime evidence. Check for evidence contamination, and compare **original outcomes**, not total tool calls, tokens, tests or number of TODO items. `CHILD_TASK_ONLY` is not `ROOT_GOAL_VERIFIED`. If no paired baseline was measured, report `BEHAVIORAL_IMPACT_UNPROVEN` even if all installed files match the latest source.
