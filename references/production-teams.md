# Production teams

## V5: existing-code Team schema2

New Corporate work uses `schema:2`; the existing team.py commands dispatch to the
new schema implementation. Existing schema1 plans retain their original meaning.
Keep original id, kind, request, contract, outcomes, tasks and integration check.
Schema2 permits one owner, sequential dependencies and empty integration.outputs
for validation-only assembly. Optional task deletions/renames bind removed paths
and before/after names. Current manifests retain absence evidence.

Set `max_parallel_workers` to the planned width supported by the host's native
dispatch and known limits. When only a smaller width is evidenced, run the
ready owners in waves; the number of owners need not equal simultaneous slots.
The coordinator consumes the handoffs and owns only the integration outputs.
Serial independent scopes need `execution_rationale`
with a documented host cap, rejected simultaneous dispatch or another observed
constraint. Native overlap is checked after dispatch. A narrow one-owner change
can integrate with no coordinator-owned output.

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

Team receipts establish scopes, lifecycle and recorded process results. Review
the meaning of the six-layer QA evidence against the task's actual requirements.

### Require review of specific details

For visual work, and for important nonvisual details that a generic PASS
could hide, declare stable IDs and observable criteria in the schema-2 plan:

```json
{
  "detail_review": {
    "wheel_fit": "Inspect the near wheel and hub in idle and steered gameplay; neither hub may float or clip through its mount.",
    "wheel_motion": "Compare consecutive gameplay frames or a short clip: the wheel rolls while the vehicle moves and stops rolling at rest."
  }
}
```

Put this object inside `integration`, alongside `check` and `outputs`.
Map all consequential details from the [finishing brief](quality-intent.md)
before registration. A single ID should not let one good feature hide another
unchecked detail. The plan reviewer challenges what's missing before production.
For a service, the same structure could require a captured state comparison
after a failed migration, separately from the successful migration.

The independent QA worker uses the returned `check` command to run the real
journey. For a plan with detail review, the command supplies a fresh
`PROVE_IT_OUTPUT_DIR`; write the observations there as flat files. The check
receipt lists their digests as `detail_artifacts`. Open the actual captures in
the sibling directory named after the retained `check-*.json` file without
its `.json` suffix. Then use `review` with the returned `qa-evidence.json` path:

```json
{
  "check_sha256": "<current check receipt sha256>",
  "observations": "<concrete runtime and quality layer findings>",
  "details": {
    "wheel_fit": {
      "verdict": "pass",
      "observation": "<what is visible in each inspected state>",
      "artifacts": ["idle.png", "steered.png"]
    },
    "wheel_motion": {
      "verdict": "pass",
      "observation": "<what the rolling and stopped samples show>",
      "artifacts": ["wheel-motion.webm"]
    }
  }
}
```

Use `fail` or `unverified` for a detail not demonstrated; submit the overall
review as `fail` and retain the evidence. A passing review requires exactly
the sealed IDs, a concrete PASS per detail and at least one captured artifact
from the current check per row. Reintegrate and recapture after repairs.
The verifier checks coverage, evidence identity and native QA attribution.
It cannot tell whether an image really shows the claimed detail; QA must
inspect it. Plans without `detail_review` keep their existing receipt format.

### Minimal existing-change sequence

Use [the schema2 template](../assets/templates/team-plan-v2.json), replacing its
placeholders with the actual request, interface, owned files and checks. Set
host.kind to the observed host and add actual model/reasoning_effort pins when
required. Keep the plan under `.runtime-proof/team-plan.json`.
Do this before any product edit, including a narrow one-file fix.

Use `validation_context` for unchanged inputs such as the existing contract,
runtime instructions, explicitly protected adapters and retained baseline
evidence. Every listed file must stay byte-identical. If an owner will edit a
checker, give them the checker path and record its original source hash and
baseline result separately. Use the independent QA packet's sealed file scope
as a starting point for the full diff review, not as proof that no other file
changed.

When a baseline replay needs the original files, retain their exact bytes
before editing. Confirm that Git objects match the recorded working-tree
hashes before substituting them: line-ending and checkout filters can differ.

For narrow work with one coherent responsibility and settled scope, record the
source-backed reasoning and omit `decomposition` and `root_protocol`. `init`
returns the single native owner packet directly. After integration, independent
QA runs the relevant old and new checks and records all six quality layer verdicts.

The template defaults to `decomposition: reviewed-v1`. Define each implementation
responsibility, existing interface, independent check and `scope_evidence`.
Evidence paths must refer to existing owned files or unchanged validation
inputs. Multiple files may belong to one coherent artifact: explain the
shared contract in its responsibility or brief. Use the plan's `scope_rationale`
when the entire change has one implementation owner. Give truly separate
responsibilities their own owners. For each `depends_on` entry, record what needed result makes
the dependency necessary in `dependency_rationale`. Use independent owners in
parallel when worker capacity allows.

For a new product, set `kind: greenfield`, seal the proposed finishing brief
in `validation_context`, and use those immutable inputs for `scope_evidence`.
The independent `plan_review` records both the intent counterexamples and
the decomposition verdict before dispatch. Start before owned paths exist.
Challenge the smallest meaningful split inside each major scope: an
independently inspectable vehicle asset, course, and interaction state can
have distinct owners. Explain what the separate handoff adds over a focused
check. A wheel that shares geometry and transforms with the vehicle can stay
with that owner; its fit or motion can go to a detail reviewer. Apply the same
distinction to migration, API and recovery work.

For substantial work, set `root_protocol` to `corporate-v1` in the Team plan.
After the plan review passes, seal the schema-4 Corporate root with the same ID
before running `packets`. The first `packets` command compares the live baseline
and records admission against that seal. Later packets and repairs use the
same seal as the source evolves. Native verification checks the seal and
admission time against implementation and QA. See [Corporate workflow](corporate-workflow.md).

When running in Copilot with a known session UUID or the host's explicit
`HARRTEST_PARENT_SESSION_ID`, set `host.kind` to `copilot`. In Codex use `codex`
when the project has access to its native logs. Use `unverified` only when the
native evidence path is genuinely unavailable and record the reason. Resolve
the host before sealing. A successful init does not identify the host for you.

```text
python <skill>/scripts/team.py --project . init --plan .runtime-proof/team-plan.json
```

For `reviewed-v1`, dispatch the returned `plan_review` packet to a native
`plan_review` worker separate from implementation and QA. It needs command
execution and private evidence writes. In Copilot, use an available
`general-purpose` agent if the built-in `task` worker restricts writes.
The reviewer records concise source-backed findings in the packet's evidence
path, within the printed character limit. Then run its exact `review-plan`
command separately and wait for the reviewer to finish. A failed review stays
with its registered plan. Before editing product files, use a fresh native
`plan_review` actor for the corrected plan. For an enrolled Copilot Corporate
goal, use `revise-plan` as described in the [Corporate guide](corporate-workflow.md#root-and-plan).
Other paths use a new Team ID. After a passing review (and Corporate sealing
when applicable), retrieve the packets:

```text
python <skill>/scripts/team.py --project . packets --team mission
```

Native verification checks that the `review-plan` receipt came from the
separate reviewer and its turn completed before implementation started.
Existing schema2 plans without the policy retain their original dispatch path.

Dispatch the returned complete ready packet as a native implementation worker;
use its returned task_name exactly so the host adapter can correlate identity.
Pass the actual model/effort explicitly when the native tool supports them.
The worker runs the documented component checks and executes the handoff
command from its packet. Use the printed script path and flags.
Do not substitute a short handcrafted prompt for the returned contract.
For Copilot's `task` tool, put packet `task_name` in the tool's `name` argument
and packet `message` in its `prompt` argument. The friendly task description
can use other wording. Set the initial QA worker's `name` to `qa` as returned.
If the original owner or QA may need a follow-up, initially dispatch each with
`task` and `mode: background`. Retain the returned `agent_id` and wait for that
ID with `read_agent` and `wait: true`. The same ID receives later packets.

```text
python <skill>/scripts/team.py --project . integrate --team mission
```

Dispatch the returned complete qa packet to a separate native worker named qa.
It runs the actual old and new behavior through the finite `check` command,
records the observations and executes `review`. Use the exact commands in the
packet. Supply the documented check's executable and arguments after `--`. The
collector launches that process directly from the project and manages its own
subprocess. Use the workspace scratch directory authorized for that project.
Track and release separate resources only if the worker started them.

QA can report `PASS`, `FAIL`, `UNVERIFIED` or `NOT_APPLICABLE` for each layer.
Retain observed failures and blockers. Accept a passing review only after all
required checks pass and any exclusions have supporting evidence.

Confirm the QA worker type can run checks and write the private evidence file.
Give it the documented runtime and any approved workspace-local temporary
paths it needs to rerun the project's existing checks on the integrated source.
Independent QA itself must run the check that backs its current review.
In Copilot, use an available `general-purpose` worker when the built-in `task`
worker's instructions prohibit file writes. The QA packet still prohibits
editing product files. Pass the `--evidence` path exactly as printed in the packet.
It is relative to the project and uses forward slashes, including on Windows.
If the host denies the command or private evidence write, retain the exact error
and keep the review unverified until an authorized path can run it.

```text
python <skill>/scripts/team.py --project . verify --team mission --parent ACTUAL_PARENT_SESSION_UUID
```

For Copilot use its actual session UUID. Verification reads native tool/worker
records, so handoffs, check and review must finish in the corresponding native
turns. This command verifies current receipts and provenance; narrative six-layer
meaning still requires inspecting the recorded QA evidence. A missing receipt
keeps acceptance open. Use the host's actual worker status and check exit/output
to decide whether to wait, retry the command, or record a blocker. Team exposes
`packets` for dispatch and `verify` for verification.

### Repair and review again

Record the failed review and run `repair` for the responsible owner using the
current evidence and a concrete observation. Send the full returned repair
packet to that original native worker. When the owner returns a current
handoff, run `integrate` and send the full current QA packet to the original
independent QA worker. Repeat the affected checks on the integrated source.

In Copilot, use `write_agent` with the original worker's `agent_id` and the
complete packet `message`. Use `read_agent` with `wait: true` for that ID to
observe whether the worker finished. The native verifier checks follow-up
delivery, worker identity and completion. It also recognizes a native
non-waiting `read_agent` that starts after the follow-up turns have closed
and confirms idle with an empty queue and the expected completed-turn count.
Prefer waiting before sending another message. Copilot can also deliver a
message as steering during a resumed interaction. The verifier binds that
delivery to the original parent send and the receiving turn, and still
requires the resumed interaction to finish.
In Codex, use `followup_task` for
the original worker. If Copilot reconnects and native `write_agent` reports
that the completed QA actor was not found, keep the old review and dispatch
one new read-only actor named `qa-recovery` with the full current integration
QA packet. That actor must run the current finite check and write its own
review. The verifier binds the replacement to the observed reconnect,
unavailable original actor and current integration. This does not replace an
implementation owner or turn an old failed check into a pass. For other
unsupported or unobserved recovery paths, keep acceptance unverified.

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
