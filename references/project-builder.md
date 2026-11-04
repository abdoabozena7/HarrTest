# Host-native Project Builder (v3.2)

## Contents
1. Intent and trust boundary
2. Greenfield intake and architecture
3. Milestone registration and first running slice
4. Execution, integration and recovery
5. Cost-aware choices inside the host
6. Validation and honest limitations

## 1. Intent and trust boundary

Use this path for a new multi-component application or a substantial expansion,
not every small bug fix. Keep HarrTest inside the existing coding host. The host
model chooses architecture, writes files and invokes actual subagents/tools. The
new deterministic `scripts/builder.py` checks that its plan is connected to the
original root, gates milestones on fresh cumulative proof, and selects ready work.
It is NOT an LLM, a stack recommender, an external agent server or a scheduler that
continues after the host ends its session. No provider credentials, SDK dependency,
paid API call or new execution permission is added.

A valid architecture document is a recorded decision, not proof that the design is
optimal. Existing resource admission, OS limits, user cancellation, protected
acceptance data and explicit payment requirements remain authoritative. Cooperation
with this controller is not OS isolation: tools used outside it remain outside its
mechanical control.

## 2. Greenfield intake and architecture

Start from the real user's request, not a template app you happen to know. A blank
project has no README or source yet. Preserve the request before scaffolding:

```text
python <skill>/scripts/builder.py --project PROJECT bootstrap --goal mission --request-file ORIGINAL_REQUEST.txt
```

The directory PROJECT must already exist. This command creates only private harness
state under `.runtime-proof` and the existing external HarrTest memory store. It
never invents goals, edits application code, overwrites an existing request, grants
resources or calls a model. Repeating the same intake resumes it; changed text
requires a documented approved goal revision. `--request-file` is an explicit input
file, not a filename guessed from an opaque attachment. Keep `.runtime-proof/`
excluded from Git through the existing reviewed installer/project policy.

The host now inspects actual capabilities and selects a practical architecture:
record runtime, stack, rationale, at least one alternative and tradeoff, constraints,
delivery format, boundaries/interfaces, and major risks with falsifiable early probes.
Prefer the simplest available stack meeting the requirement; validate tool reachability
and supported build commands before large implementation. For games, assets, engine
operation and actual play tests matter; for APIs, durable state and real integration
matter. These are adapters to a generic method, not hardcoded game/CARLA rules.

Create only the minimal setup/scaffold and independent check files necessary to seal
source scopes. Do not call scaffolding verified implementation. Use the original-root
schema-3 coverage/reviewer process when available, preserve genuine legacy roots,
and prepare the actual child contracts before registering the build graph. The user
should not fill JSON by hand; the executing coding agent does that work.

## 3. Milestone registration and first running slice

Adapt `assets/templates/build-plan.json` with the same `tasks`, `root_goal` and
`goal_id` as the v3 workflow format, plus its `build` section. Every root-linked child
appears once. Each milestone has an observable outcome and a live integration child.
The first milestone is a thin vertical slice, not a whole completed frontend with a
mock backend. The final delivery milestone depends on all other milestones and uses
the original root's integrated acceptance child. Intermediate work may be parallel
when interfaces and actual host capabilities permit.

Interface contracts are explicit bounded files, hashed at registration. Consumers
must depend on their declared producer. Changes to the contract need a reviewed
plan revision rather than editing expectations to accept the observed bug. Risk
probes are mapped to milestones so high-impact uncertainty is addressed early.

```text
python <skill>/scripts/builder.py --project PROJECT validate --plan build-plan.json
python <skill>/scripts/builder.py --project PROJECT init --plan build-plan.json
python <skill>/scripts/builder.py --project PROJECT next --goal mission
```

`validate` performs structural and existing-root/child binding checks. `init` stores
the plan transactionally in the EXISTING `.runtime-proof/workflows.sqlite`. Repeated
initialization of the identical plan does not reset work. A changed plan is rejected;
retain history and explicitly create a new reviewed revision preserving original
requirements. This version does not automatically rewrite a running dependency graph.

## 4. Execution, integration and recovery

Use `builder claim`, not a direct workflow claim, for build-mode work so prerequisite
milestone gates are checked. Each claim includes the original goal, current task
context, architecture and relevant interfaces. The host then executes the real
worker/tool calls and preserves their evidence. No agent is created by a packet.

```text
python <skill>/scripts/builder.py --project PROJECT claim --goal mission --task T1 --worker ACTUAL_HOST_ID --lease-seconds 600
python <skill>/scripts/workflow.py --project PROJECT heartbeat --goal mission --task T1 --token TOKEN --lease-seconds 600
python <skill>/scripts/workflow.py --project PROJECT run-check --goal mission --task T1 --token TOKEN --check CHECK_ID
```

The lease is renewable coordination, not a mission deadline. Choose it based on real
operation duration and renew through existing host execution. Keep tokens private.
After actual implementation and inspection, use the existing workflow handoff and
proof step/review commands. A handoff is IMPLEMENTED, not VERIFIED.

```text
python <skill>/scripts/builder.py --project PROJECT checks --goal mission --milestone M1
python <skill>/scripts/builder.py --project PROJECT gate --goal mission --milestone M1
```

`checks` does NOT execute tools: it separates missing/failed/stale checks from fresh
checks that can be reused, and from remaining review/progress problems. Re-run only
required current-source checks with `proof.py run`, inspect evidence and update proof
progress. Gates check this milestone AND predecessor milestones on current source.
Thus a new component that passes alone cannot hide a broken older path. The final
gate separately executes the original root verifier. Only that combined success
returns `root_goal_achieved: true`.

A changed source can require revalidation without discarding implemented work. If
an actual failed gate requires code repair, retain its evidence, state a falsifiable
hypothesis, and reopen the responsible task:

```text
python <skill>/scripts/builder.py --project PROJECT reopen --goal mission --task T1 --evidence .runtime-proof/T1/runs/CHECK/RUN/stderr.log --reason "Actual reproduced cause and intended corrective experiment"
```

The repair path rejects active affected workers and unknown operation effects,
preserves historical handoffs/receipts, and never changes acceptance. A recorded
repair may address a regression in an earlier stage without deadlocking on that
failed stage; it is NOT permission to advance or declare success. All cumulative
gates still need to pass afterwards. Expired workers and uncertain side effects use
the existing workflow recovery/reconciliation protocol first. A real external blocker
still requires a scoped decision; do not invent policy to keep the agent busy.

## 5. Cost-aware choices inside the host

The controller recommends serial execution when native delegation is unavailable,
and selects nonconflicting ready tasks only up to the declared actual host capacity.
The runtime's cooperative ownership checks remain authoritative at claim. Do not
force five agents for a small tightly coupled task. A stronger model is suggested
only for hard unresolved architecture/review questions when already available and
authorized in the host; the helper never routes model requests itself.

Local deterministic diagnostics first, targeted context second, real integration
at meaningful milestones, and reuse of fresh receipts reduce pointless repeated
work. This is not a token cap or a justification for lowering quality. Record actual
host cost/usage when exposed; unknown usage is unknown, not zero. The local demo's
zero *paid model calls* is not a universal prediction about real coding tasks.

## 6. Validation and honest limitations

Run `python examples/builder_demo.py --output NEW_DISPOSABLE_DIRECTORY` to reproduce
a blank-project intake, actual HTTP service, restart-persistence failure and repair,
cumulative regression rejection, clean-directory package execution and resumed
milestone selection. The scenario is a scripted deterministic fixture. Its code and
architecture are supplied by the example author, NOT autonomously generated by a
model. It exercises the controller and actual local runtime, not Copilot quality.

The helper cannot guarantee a complete game in one night, optimal architecture,
semantic acceptance completeness, uninterrupted host execution or a given model's
performance. Measure those separately with authorized matched live-host trials.
There is no automatic paid benchmark, deployment or simulator launch in installation.
