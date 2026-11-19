---
name: harrtest
description: Change software with evidence-based planning, scoped implementation workers and independent quality checks. Understand existing architecture and contracts, preserve behavior, and verify correctness, security, performance and resilience as relevant to the change. Use for implementation, debugging, refactoring and complex coding tasks. Does not apply to conversation-only requests or work that excludes execution.
---

# HarrTest 5

For an implementation request, start as coordinator. Record the baseline and
open the [Team plan](references/production-teams.md) before the first product
edit. Dispatch the actual implementation handoffs to native owners and keep
the coordinator within its integration scope. For substantial work, complete
the [Corporate pre-dispatch seal](references/corporate-workflow.md) first.
When the plan, seal, or native worker capability is missing, keep that work
unverified and continue with authorized discovery and setup.
For a bounded change with one settled responsibility, use the minimal Team
schema-2 path: one owner, integration and independent QA. Do not add a Corporate
root, extra reviewers, or extra project files unless the task needs them.
When the host explicitly supplies `HARRTEST_CORPORATE_GOAL`, use that goal ID
for the reviewed Team and Corporate root. Save the original request in the root
first, then register the Team with `team.py init --request-from-root`. Dispatch
the exact Team plan review and `corporate.py coverage-packet` messages as separate
tasks. Complete the root seal before dispatching implementation or editing.

## Start from the project

Read VERSION and pin the local package for the task. Check upstream only when
the user requests it. Use the current host, approved tools and authentication;
this skill does not grant permission or replace organization policy.

Preserve the exact request. Inspect repository instructions, actual entrypoints,
architecture decisions, public contracts, dependencies, callers and tests.
Distinguish documented intention from observed behavior. Reuse the project's
design and conventions. A new abstraction, dependency or architecture needs a
task-linked reason; do not redesign unrelated code to satisfy a generic style.

Before editing retain a source-qualified baseline: reproduce relevant behavior,
run existing checks, record known failures and measure affected resource limits.
Preserve user changes. A baseline failure is not a new regression, but cannot
silently waive a relevant security or correctness requirement.
Bind the project's explicit read-only contracts, adapters and verification
inputs in Team `validation_context`. Keep them byte-identical; record notes and
diagnostic checks privately when their locations are not authorized deliverables.

Map every requirement to affected contracts/components, risks, owners and
observable acceptance checks. Cite repository paths and exact source identity,
user decisions, real observations or version-matched official sources for
consequential choices. Ask only about unresolved material meaning or external
effects; continue independent discovery while awaiting an answer.

Use measured test duration, dependency impact and observed workload in planning.
Label estimates and assumptions; revise them after the first measured result.
Never fabricate precision or treat an agent's confidence as evidence.

## Choose scopes and execute

For substantial changes follow [the Corporate workflow](references/corporate-workflow.md).
Use a schema-4 root with `protocol: corporate-v1` and a schema-2 Team plan.
Set `root_protocol: corporate-v1` on the reviewed Team plan. Collect the actual
baseline, build the root draft from it, and seal the independently reviewed plan
and checks before requesting implementation packets.
Keep the original verification meaning of existing schema-2/3 roots and schema-1
teams; do not migrate active contracts silently.

Before the first edit, map each requested behavior to an existing responsibility,
the owning files, a stable input/output contract and a check it can pass alone.
One coherent responsibility can use one native implementation owner and a distinct
testing/review worker through Team schema2. Record why the scope cannot usefully
split. Keep its scope, baseline, checks and six layer verdicts in the QA evidence.
Two separately testable responsibility changes require separate implementation
owners and the corporate-v1 root, even when they fit one feature or share an API.
Compare the nearest viable split against real interfaces. A shared end-to-end test
does not make components dependent if they can each pass a check against that interface.
Small changes still require independent testing on the integrated source.

Split along existing component/interface boundaries. Agree on the interface first
so matching implementation scopes can run in parallel. A real dependency waits
for its prerequisite handoff when a stable shared contract cannot resolve it.
Give each worker the original goal, necessary context, read/write scope, lifecycle
invariants, baseline, risks and independent checks. Count implementation owners
by their assigned product changes and actual handoffs.

Use native workers for independently deliverable implementation scopes. Dispatch
ready independent tasks together; dependent tasks wait for current handoffs.
A narrow change has one implementation owner and an independent tester.
Do not invent parallel work or extra files to satisfy a worker count. Split a
complex scope further only when its deliverables can be independently checked.
Reuse the active model and effort unless the user selected otherwise.
Pass those values explicitly to every native worker call when the host exposes
them, including built-in testing/review agents: a built-in agent can have a
different default model from the main session. Check actual configured/invoked
worker metadata, not only a dispatch request or first-dispatched-model label.
If the host cannot honor a required pin, retain the result with that limitation;
do not report it as a same-model comparison.

Keep one writer per file at a time, including configuration. Route fixes to the
existing owner, refresh dependent handoffs and reintegrate. Support real deletions
and renames; integration can be validation-only. Inspect native status and receipts
before repeating waits. Completed workers need a next action, not indefinite waits.
Keep each repair within the reviewed responsibility, even when the same file
contains unrelated behavior. If observed baseline behavior and its documented
contract disagree, record both and resolve the impact on the request before
changing that behavior.

The coordinator resolves interfaces and integrates returned work. Independent QA
exercises actual behavior on current source and does not edit the product.
Independent review checks the diff, evidence relevance and project constraints.
It also checks whether the plan grouped separable work and whether independent
owners actually overlapped when the host had the capacity.
These roles are distinct from the implementer. Record actual worker identities
and capability limits; do not label unsupported host provenance verified.
[Team contracts and host evidence](references/production-teams.md)
For narrow work use that guide's minimal schema2 sequence and actual returned
worker/QA packets. A handcrafted prompt can lose the handoff and verification
contract. Review instructions must allow FAIL and UNVERIFIED findings, as well
as PASS and justified NOT_APPLICABLE; do not bias reviewers toward acceptance.
Select the actual host before sealing the team plan. In Copilot, give the native
`task` tool the exact `task_name` as `name` and the returned `message` as `prompt`.
Use only the description for a friendlier label. The returned testing name is
`qa`. Choose a worker allowed to run checks and save private proof artifacts.
Keep its product scope read-only. If a built-in reviewer forbids all writes,
use another permitted worker type with the same `qa` name. Verify the current
native Team after the testing worker completes.

## Assess all quality layers

Assess each layer for every change. Choose checks from actual impact and project
policy, rather than programming language alone:

| Layer | Reasoning and evidence |
| --- | --- |
| Functionality | Requirement-derived outputs, boundaries and negative cases with independent expected results. |
| Preservation | Existing callers, contracts, old inputs/outputs and relevant before/after regression checks. |
| Architecture | Project conventions, responsibility boundaries, dependency direction, diff review, types and static checks. |
| Security | Changed trust boundaries, input handling, authorization, secrets and dependency risks; misuse tests and analysis. |
| Performance | Relevant latency, throughput, allocation or resources; repeated same-workload measurement with noise and limits. |
| Resilience | Relevant persistence, migration, retries, cancellation, recovery, concurrency and resource lifetime. |

Use project security requirements first. Apply risk-based design review and
security testing, drawing on [Microsoft SDL](https://www.microsoft.com/en-us/securityengineering/sdl/practices)
where supporting guidance is needed. A scanner cannot prove absence of vulnerabilities.
Missing required tooling is an unverified check, not a clean result.

Check interactions between layers. A restriction, filter, validation, cleanup or
data transformation must both handle its intended target and preserve legitimate
nearby cases. Derive rejected/changed and allowed/unchanged boundary examples from
the contract, including plausible near matches. Removing every sensitive value
does not establish correctness if useful nonsensitive structure or authorized
behavior was lost. Review broad heuristics against the preserved contract rather
than treating a stricter-looking result as automatically safer.
For multi-step behavior, establish the intermediate invariants as well as the
final result. A valid final value or successful final response does not show
that intermediate operations, partial failures or state transitions were legal.
For each affected input boundary, derive checks from the whole relevant contract,
including optional controls and failure triggers. Exercise the valid alternate
values and malformed shapes or types the contract rejects. For a rejected
operation that can cause side effects, assert the before/after state at the
rejection boundary as well as the public response.
When changing operation order, compare old and new paths that do no work
(empty input, early exit, unsuccessful parse or zero iterations). Preserve
their established outcomes without growing the public input domain.
For an affected representation or conversion, check valid boundary values that
still have representable outputs. Cite the accepted input domain and actual
runtime limits. If a runtime cannot honor the contract at that boundary, retain
the failing observation and resolve the contract impact before claiming completion.

Every required layer must PASS. NOT_APPLICABLE requires impact reasoning, cited
evidence and separate review. Missing checks remain UNVERIFIED. A failed major
criterion cannot be offset by an aggregate score. Do not weaken thresholds,
delete useful tests, change an oracle to match an answer or substitute a mock for
the actual integration to pass acceptance.

Use project performance budgets. If absent, establish workload, method and
justified tolerance before optimizing and bind them to the plan. Preserve output
correctness, contracts and resource safety. Separate startup, warm-up and steady
state. Inconclusive measurements require better measurement, not a product change
made on an unsupported hypothesis.

## Evidence before acceptance

Retain requirement -> decision/source -> action -> observation -> assertion ->
artifact -> review. Bind evidence to current content, including uncommitted files,
tests, configuration and dependency locks. Commit identity alone is insufficient.
Keep commands, tool/environment versions, actual exit results and failed attempts.
Limit sensitive capture at the source; record redaction and rebind changed evidence.
Keep private evidence in `.runtime-proof/`, not public project artifacts.

For narrow Team work, run the finite integrated check and verify its current
native QA receipt before spending time on optional diagnostics. For a sealed
root, run checks through `proof.py` and verify with `root_gate.py verify`.
Corporate acceptance binds the plan at sealing and requires
current-source checks and independent review for all six layers. A path/hash
establishes identity, not whether a citation supports a claim: the reviewer must
record that judgment. Local records are cooperative evidence, not a hostile-writer
security boundary. [Limits](references/security-and-limitations.md)

Reproduce, explain, repair with the owner, rerun and inspect. Preserve existing
tests and add meaningful tests for changed behavior; test counts are not quality.
Use [acceptance and test quality](references/acceptance-and-test-quality.md) for
independent oracles and safe negative controls.
For a newly found issue, replay the same observation against the pinned baseline
and the current source. Record its impact on the agreed requirements before
routing repair. Keep inherited out-of-scope findings visible and keep affected
requirements open until their failures are resolved.
For an inherited defect outside the change, cite the unchanged source, compare
its trigger and observable result before and after, and explain why it cannot
affect any changed requirement or trust boundary before accepting the scoped work.
If the change interacts with the defect or project policy disallows it, keep the
affected layer open.

Load domain instructions only when actual behavior needs them:
[visible output](references/quality-intent.md), [browser behavior](references/web-validation.md),
[CLI/agent execution](references/cli-agent-validation.md), or
[simulation](references/simulation-validation.md). Visual/motion evidence applies
only to criteria that need it. For new products establish contracts and intended
quality first; preserve any affected existing behavior explicitly.

For cumulative work use [Builder](references/project-builder.md); for legacy Gold
comparisons use [the Gold runbook](references/v4-gold.md). Retrieve source-qualified
[memory](references/project-context-memory.md) without replacing the request or
carrying stale facts into a new revision.

## Continue until the agreed result is verified

Keep ordinary diagnosis and repair in the active mission. A handoff, failed review
or attempt timebox is not completion. Respect authorization, actual resource
limits, cancellation and host limits. Report missing capabilities honestly while
continuing useful authorized work.
Qualify completion claims to the behavior and inputs actually verified. If an
applicable criterion is still open, report the affected requirement as incomplete
alongside check results already established.

For harness improvement keep product edits and task-specific repair coaching out
of the experiment. Improve the general mechanism, pin a new version and retain
all results. A case used to guide improvement becomes development data; use fresh
acceptance cases. Predeclare comparisons and record cost for every worker.

Report implemented behavior, contributions, current-source layer verdicts,
before/after measurements and unresolved findings. Claim verified only within the
checked scope. Corporate is a version name; evidence establishes its assurance.
