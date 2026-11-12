---
name: harrtest
description: Build and repair software with evidence, native implementation teams and independent acceptance. New products use scoped subagents to implement components before the coordinator integrates them. Use for coding, UI, APIs, CLI, simulation and agent pipelines. Preserve the original request, resolve material uncertainty, test the real entrypoint and inspect current results. Does not apply to conversation-only requests or work that excludes execution.
---

# HarrTest 4.1 Gold

## Choose the execution path before editing

Use the installed local version. Read VERSION and pin it for this mission.
Run `version_guard.py` only for an explicit request to check upstream/latest.

**A new product starts with implementation workers.** This includes a small
game, page, app, service or tool built from scratch. The length of the prompt
and the number of existing files do not make a new product a single-file fix.
Create its component boundaries and use the native team path below before
writing application files. Use a direct path for a narrow change in an
existing component when splitting it would leave no independent deliverable.

The coordinator defines interfaces and owns assembly. Give actual production
work to native subagents. Planning, scouting and review do not satisfy an
implementation assignment. Keep the same model and reasoning effort as the
active host unless the user chose otherwise.

Application behavior and presentation are production work too. Assign their
owners before dispatch. Integration imports and connects the delivered
components. Keep core business/game rules, input handling and designed UI in
worker-owned modules rather than collecting them inside the coordinator's
assembly file.

## Native team path

1. Preserve the exact user task. Read only the source and contracts needed to
   understand it. Translate its intended outcome into observable acceptance.
   Ask about material unknowns that change behavior or external effects.
   When the user delegates design choices, choose a coherent design and proceed.
2. Define a small production DAG with explicit outputs, interfaces, dependency
   order and a check for each component. Choose enough owners to give each
   distinct part focused attention. For a new visual product, consider the
   primary subject, environment/layout, interaction/state, and interface.
   A single page/scene container is not a useful visual split when its main
   subject and surrounding structure can be delivered independently. Give
   those distinct visible components separate implementation owners.
   Put the shared visual direction, proportions and meaningful subject detail
   in the contract that every worker receives. Keep the chosen style coherent.
   Specify shared representations, units, lifecycle and boundary invariants
   where components exchange state. Test a producer/consumer example against
   that agreement; matching export names alone does not establish compatibility.
   A leaf can split further when a detail has its own meaningful deliverable.
   Carry supplied runtime, resource and validation constraints into the sealed
   plan's `validation_context` file paths. Every implementer needs those inputs,
   not only the eventual tester. Make the first handoffs a small runnable
   user path with representative work; integrate and measure that checkpoint
   before expanding costly detail. Keep the full requested quality as acceptance.
3. Read [production teams](references/production-teams.md). Create
   `.runtime-proof/team-plan.json` and run `scripts/team.py init` before
   product edits. On Codex, use its returned `task_name`, `fork_turns` and
   `message` in actual `spawn_agent` calls. Dispatch independent ready
   workers before waiting. Reuse the active model and effort for every worker.
   Pass the complete returned message, including its absolute project path,
   contract, file ownership and handoff command. Do not replace it with a
   short role description. If spawning hits the host slot limit, wait for a
   running worker to finish, then dispatch the remaining ready packet. Keep
   the sealed owners; a full slot queue does not transfer their work to you.
4. Each implementer writes and checks only its product files, then executes
   the packet's handoff command. Follow actual handoff evidence. Resolve a
   missing or faulty component with its owner. Ownership continues through
   repairs: even a one-line fix in a worker file goes back to that worker,
   followed by a fresh handoff. The coordinator edits only its declared glue.
   Retain genuine worker IDs and raw traces.
   Wait only for required workers that are still running. If an unchanged
   wait repeats, inspect native agent status, final results and current
   receipts before waiting again. Completed or failed workers need a next
   action, not an indefinite wait for another completion notification.
5. Run `team.py verify --production-only` on completed worker handoffs.
   The coordinator connects the delivered modules through the declared
   entrypoint/glue. Run `team.py integrate` and dispatch its independent QA
   packet. QA executes the public entrypoint, records its output and checks
   the original user journey. Give QA exclusive runtime/browser resources
   during that check; the coordinator can inspect its retained frames.
   Return failures to their owners and reassemble
   after repair. Run `team.py verify` on current files before completion.
   On every QA attempt, including repair replays, pass the full returned QA
   packet again. On Codex, resume an existing named worker with `followup_task`
   rather than inventing a retry suffix and discarding its capability context.
   Include supplied verification-target paths and environment constraints in
   each affected worker/QA handoff; do not leave later clarifications only
   in the coordinator's context.
   A failed review returns work to its named owners. Use `team.py repair` with
   the retained failure evidence and concrete observation; dispatch its complete
   owner packet, then collect a fresh handoff, reintegrate and rerun independent
   QA. A stale handoff is unfinished work, not a reason to omit that owner.

Use the host's actual parallel capacity. With fewer slots, run ready workers
in waves. Keep one owner for shared configuration and exclusive resources.
If native delegation is unavailable, record that observed capability gap,
continue authorized work and leave team acceptance unverified.

For a small new product the team plan, component handoffs and independent
integrated QA form the working path. Start building after those boundaries
are defined. Read the larger workflows only when their conditions below apply.

## Quality belongs in the component brief

Give every implementer a specific output and quality criteria, shared with
the integrator. For a visible component, name its purpose, form/material,
useful detail and connection to the rest of the product. Agree on the visual
style and proportions across workers. A separate worker can implement a
complex asset or behavior when it has a stable interface.

Inspect the real integrated output. For UI and games, capture and inspect a
start state, an interaction state, and a recovery/end state. Check composition,
the main subject, scene/layout variety, intentional detail, readable controls
and feedback. If the result is mostly placeholders or omits a requested
interaction, return a concrete observation to the owning worker and repeat
the actual check. A screenshot path alone does not establish visual quality.
Give functionality, visual quality and responsiveness separate verdicts.
An indistinct primary subject, unreadable content or an obstructed view of
the interaction is a visual acceptance failure, rather than a caveat under
a functional PASS. Check detail at the final scale and lighting in real frames.
Check responsiveness as well as detail. When timing affects the task, compare
wall time with observable product progress and retain both. Repair added detail
that makes the requested interaction unusable before accepting the result.
Profile the expensive work before optimizing, keep the quality criteria, and
send measured regressions to the owning implementer. Compare the repaired
result on the same runtime, viewport and inputs.
Check the representative executable path early, while changing its structure
is still cheap. Pass the target workload, timing and resource limits to every
affected owner. Separate the cost of loading, rendering, computation and
interaction using measurements from that runtime. A high idle callback rate
does not establish useful rendered work. Preserve requested detail and behavior
when reducing measured cost; reducing simulation progress or verification
resolution does not repair responsiveness.
When a project supplies a validation target or browser configuration, use it
for verification rather than substituting a default runtime. Preserve the
declared resolution and quality requirements while repairing performance.

Use [web validation](references/web-validation.md) for real browser actions,
[CLI/agents](references/cli-agent-validation.md) for generated programs,
and [simulation](references/simulation-validation.md) for engine experiments.

## Evidence and preservation

Keep the original request and the reason and source behind consequential
scope, interface, implementation and verification choices. Cite authoritative
answers already available. Distinguish user requirements from reversible
design assumptions. Keep dependent work within the agreed interfaces.

When preserving behavior, run the existing entrypoint before editing and
replay the same inputs afterward, including a boundary where the new behavior
differs. Compare the actual output, exit status and persistent state.

Use observe, reproduce, explain, repair, rerun. Preserve each meaningful
failure and failed attempt. Use independent expected outcomes and safe
negative controls. Keep live, offline, replay and fixture evidence distinct.
Check that the running source matches the files being delivered.

When the user requests iterative improvement, a failed attempt is diagnostic
input, not the end of the assignment. Retain its result, identify the specific
missing or ineffective mechanism, make the smallest general harness correction,
then test a new pinned revision. Keep benchmark product edits and task-specific
implementation coaching outside a harness-only experiment. Record the hypothesis,
change, full attempts and before/after observations. Do not silently lower
acceptance, select only a winning retry or claim a general uplift from one case.
An attempt timebox ends that attempt; it does not end an authorized improvement
mission. Continue the next justified cycle while respecting actual user resource
limits, permissions and cancellation. Publication/install still requires the
user's acceptance condition to be demonstrated on the delivered revision.

Team verification checks local native provenance, changed outputs, ownership,
active overlap, integration order and independent QA receipts. Runtime and
visual acceptance must still establish the requested behavior. A passed child
or an agent finishing its turn does not close the original goal.

## Larger and continuing missions

- For cumulative milestones or a resumable multi-stage build, use
  [Project Builder](references/project-builder.md). Seal a schema-3 root with
  `production_team` equal to the team ID and fingerprint the integrated product.
  Direct root verification and the supported active stop callback then require
  Team evidence. Preserve old root protocols and historical acceptance.
- For a formally measured Gold comparison, use the
  [Gold runbook](references/v4-gold.md). Predeclare cases, baseline, conditions
  and numeric thresholds. Retain blocked, failed and missing attempts in the
  denominator. Fixture results measure the controller. Measure live product
  outcomes and visually inspect artifacts before claiming model improvement.
- For ongoing work, use [project memory](references/project-context-memory.md)
  to retrieve source-qualified notes and checkpoints. Bootstrap only from the
  original goal. If external private storage is unavailable, use an authorized
  project-local private path through `HARRTEST_STATE_HOME`.
- Use [Hivo patterns](references/hivo-patterns.md) for intent contracts,
  recursive task boundaries and evidence-directed repair.

Use the current host, authentication, tools and authorized resources.
Maintain exclusive resource ownership and reconcile interrupted side effects
before retrying. Preserve user changes and real safety/budget boundaries.
Record actual limitations when native hooks, browser tools or independent
review are unavailable. Local records are cooperative evidence and can be
rewritten by a workspace owner. See [security](references/security-and-limitations.md).

## Report the delivered result

Give the version, implemented behavior, actual worker contributions, fresh
runtime/visual evidence, current root status and unresolved findings. State
the scope of measurement and retain the raw artifacts. Describe partial
outcomes accurately and continue authorized repair while useful work remains.
