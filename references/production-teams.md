# Production teams in HarrTest 4.1 Gold

Use this path when at least two independently implementable parts contribute
to the requested product. Give each part a concrete output, one owner, a
stable interface and an observable check. Give the coordinator the small
integration surface. Match the split to the work. For example, a browser app
can have a data layer and a view with an agreed API. A 3D scene can have
separate model, track, scenery and interaction owners. A leaf can delegate
a further bounded piece when its interface is stable and host capacity allows.
Retain that deeper trace as supporting evidence. The v4.1 gate verifies the
direct production workers sealed in its plan.

Use the user's actual requirements. For example, split identity, roles and
protected routes when the request includes them. Preserve the simple scope of
a demo when it asks for local play. Ask about decisions that would change
acceptance, shared interfaces or external effects. Record reversible design
choices and proceed when the prompt delegates them.

## Codex quick start

The coordinator writes the following compact JSON under
`.runtime-proof/team-plan.json`. The user supplies the task and the agent
fills in the plan. Keep `request` equal to the original request body.

```json
{
  "schema": 1,
  "id": "mission",
  "kind": "greenfield",
  "request": "The exact user task goes here.",
  "contract": "Define exports, data, ownership and how the entrypoint connects them.",
  "validation_context": [".runtime-proof/validation-target.json"],
  "outcomes": {
    "data": "Describe the observable behavior of the data component.",
    "view": "Describe what the user can see.",
    "interaction": "Describe the state changes produced by user input."
  },
  "tasks": [
    {"id": "data", "brief": "Implement the data component and exercise its contract.", "outputs": ["data.js"], "depends_on": [], "outcomes": ["data"]},
    {"id": "view", "brief": "Implement the visible component against the agreed contract.", "outputs": ["view.js", "style.css"], "depends_on": [], "outcomes": ["view"]},
    {"id": "interaction", "brief": "Implement input handling and state transitions using the data and view interfaces.", "outputs": ["interaction.js"], "depends_on": ["data", "view"], "outcomes": ["interaction"]}
  ],
  "integration": {
    "outputs": ["index.html", "main.js"],
    "check": "Serve the public page, exercise the requested journey and inspect the result."
  }
}
```

Use `kind: "change"` for existing code. The gate snapshots the existing
files before work. Use exact product file paths. If the split would cause
shared writes, put that interface or glue under one owner.
`validation_context` is optional for existing plans. When the project supplies
runtime profiles, workload bounds or validation targets, list their existing
local files there. The gate binds their hashes and includes their absolute
paths in implementation, QA and repair packets. These are shared constraints,
not files for the implementers to change. Omit the example field if no such
file exists; do not create an invented acceptance target just to fill it.

```text
python <skill>/scripts/team.py --project . init --plan .runtime-proof/team-plan.json
python <skill>/scripts/team.py --project . packets --team mission
python <skill>/scripts/team.py --project . verify --team mission --production-only
python <skill>/scripts/team.py --project . integrate --team mission
python <skill>/scripts/team.py --project . verify --team mission
```

1. Call `init` before edits and pass its ready packets to native
   `spawn_agent`. Use the exact packet `task_name`. Start the ready wave
   before waiting. `packets` shows new work when dependencies finish.
2. Each worker writes its own declared files with the native patch tool.
   It checks the result and runs the packet's `handoff` command, which
   records current file hashes. Resolve failures with the assigned owner.
3. After verified production handoffs, the coordinator writes the declared
   integration files and uses `integrate` to freeze the assembled source.
   Start the returned `qa` packet as a separate native worker. The worker
   runs the public check through `team.py check -- COMMAND ARGUMENTS`,
   retains observations and uses `review`.
4. Run `verify`. For visual work, also retain inspected real frames before
   and after interaction. Look at composition, the main subject, purposeful
   detail, feedback, and whether the actual product can be used. For a
   formal Builder or workflow root, set `"production_team": "mission"` on
   its schema-3 root and fingerprint the complete integrated product.

After a repair, pass the complete new integration/QA packet again. On Codex,
use `followup_task` to resume an existing named implementation or `qa` worker.
Keep the exact packet name and its runtime-discovery instructions. A short
replacement such as "review the fix" loses the project, tools and evidence
contract. Inspect final native status and current receipts before repeating
a wait; a completed or failed worker will not produce a new result unaided.

## Early measurement and failed acceptance

Schedule an early executable checkpoint with representative work, not all
polish followed by the first runtime check. Each owner initially delivers a
coherent component for the requested user path, with a stable interface and
the supplied resource constraints. Assemble those first handoffs, measure the
main interaction in the declared environment, and then deepen the result.
An early checkpoint is development evidence; placeholders, reduced quality
or missing outcomes cannot become the final acceptance.

After a failed independent review, keep its evidence and route the concrete
observation to the responsible implementer:

```text
python <skill>/scripts/team.py --project . repair --team mission --task view --evidence .runtime-proof/teams/mission/qa-evidence.txt --observation "The measured main interaction violates the retained target; diagnose the cost and preserve the requested output."
```

Dispatch the complete returned native worker packet. The implementer diagnoses
and repairs its files, performs a focused check and hands off again. Collect
all affected owners, reassemble, run `integrate` and give the full current
packet to independent QA. A previous receipt cannot hide changed source or an
outstanding repair. Failed QA commands/reviews remain in history and do not
mean the original user goal is complete.

When improving this skill, separate development cycles from a frozen comparison.
End and retain a timeboxed failed trial, improve the general mechanism from its
observed failure, then start a new pinned trial. Do not rewrite the old result
or resume a held test under a changed package and call it the same experiment.

The coordinator can prepare its HTML/CSS or configuration scaffold while
the implementers work. The native record must show actual assembly work
after the first production handoffs. After a component repair, `integrate`
records the updated input receipts even when the assembly file needs no edit.

## What the gate measures

The Codex adapter looks for durable local host rollouts for the parent and its
named direct children in the same workspace. Use a session that retains those
logs. `verify --parent THREAD_UUID` selects the exact parent when the current
shell lacks `CODEX_THREAD_ID`. A successful verification remembers the parent
for later root checks. Logs stay in the host store and the registry is local
under `.runtime-proof/teams/`. The gate connects native successful patch
events and handoff command output to current file hashes. It checks distinct
workers, actual overlap of independent tasks, dependency order, integration
after production and an independent QA receipt on the integrated state.

Other hosts can follow the same division with their native tools. This
mechanical adapter checks the supported Codex rollout format. Its provenance
is local and cooperative. A user with control of the logs and workspace can
change the evidence, and shell edits outside audited patch events are not
intercepted. Team verification covers production ownership and QA ordering.
Product correctness and visual quality still require real independent checks.
Previous roots without the production team marker keep their original
verification protocol.

The split follows the local Hivo/OrchCode Studio patterns of an intent
contract, scoped implementation packets, dependency-aware dispatch and review
of actual execution after the workers return. The [Hivo notes](hivo-patterns.md)
describe the reusable parts.
