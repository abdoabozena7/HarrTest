# Upgrading from v2 without losing history

The package ID remains `harrtest`. Upgrade the entire skill, not one script. Preserve
old project tasks, receipts, logs, requests, grants and active ownership. Do not run
two competing legacy skill hooks. The installer preserves project instructions and
backs up replacements; npx installation does not automatically reconfigure hooks.

## Evidence compatibility
The product version now comes from VERSION. Receipt format remains schema 1; root
schema 2 remains readable with LEGACY_DECLARED_COVERAGE. New roots can use schema 3
full-text mapping plus a declared separate reviewer. No automated parser proves
natural-language completeness or authenticates that reviewer.

v2 seals hash all helper scripts. They are not silently accepted by the changed v3
engine. Keep them as historical facts. If a task needs current acceptance, create
a documented child/root revision retaining the same original request and every
original requirement, link the previous revision, and execute the required current
checks. Do not overwrite the old seal or erase useful diagnosis. Real live acceptance
cannot be manufactured by resealing an old recording.

New v3 child fingerprints include the collector, planner, strict reader and explicit
harness dependencies. Direct `{skill}/...` command files are included automatically;
list additional imported/transitive verifier files in `harness_dependencies`. A
version-lookup or unrelated installer edit no longer changes the child fingerprint
unless the check actually declares that dependency. Changes to relevant source,
checks, collector or verifier dependencies still invalidate acceptance. Root coverage
is reevaluated separately. Historical progress and current acceptance are different.

## Planning and concurrency
New parallel plans must use explicit scoped paths, not wildcard write scopes. Add
ordering or separate ownership for overlapping read/write surfaces or resources.
Detached child initialization does not move the active task. Keep one coordinator
per goal, and use one runtime database per checkout for shared-resource coordination.

## Pinning and update policy
Latest-only checking happens at mission start; keep that verified installation
unchanged through the mission. A user who explicitly requires newest-on-resume can
recheck and request update, but the agent must not self-update silently. An approved
offline enterprise pin is a distinct policy, not a claim that current main was checked.

## Research roadmap vs this release
Implemented: root-aware stop decisions, strict input boundaries, dependency-aware
fingerprints, scope-conflict checks, whole-request review binding, SQLite task/lease
coordination, operation reconciliation, focused context packets, evaluation summaries,
and a real local subprocess repair/resume demonstration.

Not claimed: automatic LLM-based requirement compilation; proof of semantic coverage;
remote signed evaluator service; actual hosted-model subagent scheduling; autonomous
approval of sensitive actions; empirical improvement on the research plan's 144/1080
live-model trial campaign; native CARLA verification. Native delegation remains in
the host, and this release coordinates it through tools/instructions. Enterprise
certification and improved model completion rates require separate measured acceptance.
