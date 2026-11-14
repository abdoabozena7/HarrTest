# Production teams

## V5: existing-code Team schema2

New Corporate work uses `schema:2`; the existing team.py commands dispatch to the
new schema implementation. Existing schema1 plans retain their original meaning.
Keep original id, kind, request, contract, outcomes, tasks and integration check.
Schema2 permits one owner, sequential dependencies and empty integration.outputs
for validation-only assembly. Optional task deletions/renames bind removed paths
and before/after names. Current manifests retain absence evidence.

Declare actual max_parallel_workers. A serial schedule of independent scopes
needs execution_rationale; do not invent an extra worker or glue edit. Scope and
receipt checks remain distinct from host identity/provenance.

host.kind declares codex, copilot or unverified. Unsupported/unobserved native
formats remain UNVERIFIED and cannot pass full native-Team acceptance. Installation
alone does not prove an adapter works. Inspect actual host-assurance output.
Optional model/reasoning_effort pins are checked against observed worker context.
For Copilot pass `--parent` with the actual Copilot session UUID, not a surrounding
Codex conversation ID. `--sessions` can explicitly identify the Copilot
session-state root; otherwise the adapter uses COPILOT_HOME/session-state or the
user's .copilot/session-state. It reads only the selected session's native events
and keeps actual subprocess output and source hashes separate from host metadata.
See [Corporate workflow](corporate-workflow.md) for the root quality contract.

For a narrow change, the coordinator retains a compact contract/baseline and
dispatches its one implementation packet, then collects the handoff, integrates
without a token glue edit and dispatches the independent QA packet. QA runs the
real old/new checks and records all six quality layer applicability/verdicts with
observations in its evidence. Do not skip the native tester because the fix is
small. Team receipts prove scopes, lifecycle and process results; six-layer
semantic completeness of this lightweight narrative needs actual review.
Use corporate-v1 for mechanically structured six-layer root acceptance.

### Minimal existing-change sequence

Use [the schema2 template](../assets/templates/team-plan-v2.json), replacing its
placeholders with the actual request, interface, owned files and checks. Set
host.kind to the observed host and add actual model/reasoning_effort pins when
required. Include the existing contract/baseline and relevant validation inputs
in validation_context. Keep the plan under `.runtime-proof/team-plan.json`.
Do this before any product edit, including a narrow one-file fix.

When running in Copilot with a known session UUID or the host's explicit
`HARRTEST_PARENT_SESSION_ID`, set `host.kind` to `copilot`. In Codex use `codex`
when the project has access to its native logs. Use `unverified` only when the
native evidence path is genuinely unavailable and record the reason. Resolve
the host before sealing. A successful init does not identify the host for you.

```text
python <skill>/scripts/team.py --project . init --plan .runtime-proof/team-plan.json
```

Dispatch the returned complete ready packet as a native implementation worker;
use its returned task_name exactly so the host adapter can correlate identity.
Pass the actual model/effort explicitly when the native tool supports them.
The worker executes its packet's handoff command after its component checks.
Do not substitute a short handcrafted prompt for the returned contract.
For Copilot's `task` tool, put packet `task_name` in the tool's `name` argument
and packet `message` in its `prompt` argument. The friendly task description
can use other wording. Keep the QA tool name `qa` exactly as returned. Use the
same naming rule for owner repairs. Check both `name` and `prompt` before each
dispatch so a different tool label does not break the evidence chain.

```text
python <skill>/scripts/team.py --project . integrate --team mission
```

Dispatch the returned complete qa packet to a separate native worker named qa.
It exercises the old/new behavior through the finite `check` command, records
the observations and executes its `review` command. Both commands are in that
packet. QA may report PASS, FAIL, UNVERIFIED or NOT_APPLICABLE for a layer; do not
ask it to choose only passing labels. Overall unverified required checks cannot
be a passing review. Do not restrict what defects the reviewer may report.

Confirm the QA worker type can run checks and write the private evidence file.
Give it the documented runtime and any approved workspace-local temporary
paths it needs to rerun the project's existing checks on the integrated source.
Reviewing an earlier coordinator run does not establish independent execution.
In Copilot, use an available `general-purpose` worker when the built-in `task`
worker's instructions prohibit file writes. The QA packet still prohibits
editing product files. Pass the `--evidence` path exactly as printed in the packet.
It is relative to the project and uses forward slashes, including on Windows.

```text
python <skill>/scripts/team.py --project . verify --team mission --parent ACTUAL_PARENT_SESSION_UUID
```

For Copilot use its actual session UUID. Verification reads native tool/worker
records, so handoffs, check and review must finish in the corresponding native
turns. This command verifies current receipts and provenance; narrative six-layer
meaning still requires inspecting the recorded QA evidence. Ordinary failures go
back through `repair` to their owner and fresh integration/QA. A missing receipt
is unfinished evidence, not permission to skip the worker or invent an ID.

When `HARRTEST_PARENT_SESSION_ID` is available, `verify --team mission` can select
that session directly. Invoke Python commands with `-B` to avoid writing import
caches into the pinned skill package.

A host integration may expose `HARRTEST_PARENT_SESSION_ID` in the Copilot process
environment. Schema2 can use that explicit session selector when no parent flag
or cached binding is supplied; the actual native header and workspace must still
match. A surrounding Codex thread ID is never a Copilot parent. This variable
selects evidence and does not authenticate it or grant access to unrelated logs.
When it is absent, obtain the exact ID from the host and use `--parent`; do not
guess a UUID or choose whichever session directory was modified most recently.

## Legacy schema1 (4.1)

The remaining instructions describe schema1, including its minimum-worker and
changed-glue rules; do not apply those constraints to schema2 changes.

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

For a new product, complete the independent [quality-intent challenge](quality-intent.md)
first. Add the accepted quality brief and its review to `validation_context`
alongside any supplied runtime files. Production assignments inherit those
observable finishing criteria; a review-only role cannot satisfy production.

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
   First load the entrypoint, enter its main interaction and sample decisive
   runtime/resource constraints. Fix a clearly unusable result before spending
   a long test on its end state. Cover the control/outcome matrix in the final
   current-source check. Retain raw measurements through the check command or
   explicit private artifacts, not a manually copied value alone.
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
The CLI allows a five-second grace for the native completion record after a
handoff. `verify --wait-seconds 0` checks immediately; the maximum grace is
30 seconds. A still-open receipt turn returns `pending-native-turn` with
`passed: false` and `mission_complete: false`. Check the actual host status:
wait for a running owner or resume an interrupted owner with the full packet.
Elapsed grace never substitutes for the required completed native record.

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

Keep Team commands in purposeful native invocations with literal command
arguments. Code-mode command results may be plain stdout or a structured exec
envelope. Preserve a yielded command's session ID and matching poll/wait;
do not discard a running result and repeat the product test to recover its
receipt. Let the invocation return before verifying it in another call. The
adapter follows supported command/session/cell continuations and rejects
unrelated output or receipt text printed as JavaScript source. It is a bounded
native adapter, not a JavaScript interpreter. New reviews retain an immutable
content-addressed copy of the supplied QA narrative, so later report edits
cannot erase the previous review's evidence.

Prefer one Team command per invocation; a long preceding report can push the
receipt out of a small display budget. The adapter also reads supported native
`CommandExecution` completion records: actual three-element shell argv, scoped
workspace and full retained stdout. Literal PowerShell evidence here-strings
are data, not executable command mentions; expandable bodies remain unsupported.
An unchanged receipt keeps its first genuine completion proof. Reprinting it
does not turn unchanged source into a new integration or invalidate earlier QA.

The split follows the local Hivo/OrchCode Studio patterns of an intent
contract, scoped implementation packets, dependency-aware dispatch and review
of actual execution after the workers return. The [Hivo notes](hivo-patterns.md)
describe the reusable parts.
