# HarrTest v3: execution, not another model client

## Scope
The skill drives the existing coding host. `workflow.py` is a standard-library,
SQLite-backed cooperative coordinator. It schedules ready tasks, protects declared
file/read/resource scopes, fences worker handoffs, preserves history and connects
real child proof to original-root acceptance. It does not spawn LLM agents, modify
billing, install SDKs, issue grants or sandbox arbitrary processes. Native host
subagent calls remain real host calls, with actual identities and tool traces.

## 1. Bind the original goal
Preserve the exact request using `root_gate.py init --project . --id mission
--request-file REQUEST.txt`. Do not replace an existing root with a smaller goal.
New root contracts use `assets/templates/root-contract-v3.json`; v2 remains supported
and explicitly labelled legacy coverage. Generate full-text spans with:

```text
python <skill>/scripts/root_gate.py inventory --goal .runtime-proof/root-goals/mission
```

Map every non-whitespace span to requirement IDs or justified context. Require a
real separate reviewer to inspect original text versus outcomes and failure cases.
The review artifact uses `assets/templates/coverage-review.json`. Bind request bytes,
segments, and `{requirements,integration}` with SHA-256 of canonical JSON (UTF-8,
sorted keys, compact separators, ensure_ascii=False). `coverage.py` validates the
review and span mapping during schema-3 root seal and verification. Placeholder
identity labels are not an actual independent review. Scope semantics cannot be
proven by character coverage; human/independently controlled evaluation is needed
for consequential work. When no separate reviewer exists, disclose the limitation
and use explicitly labelled legacy self-reviewed coverage, not fake schema-3 data.

## 2. Create actual children without stealing active sessions
Use `proof.py init --project . --id CHILD --goal "specific outcome" --kind cli
--root-goal mission --detached`. Populate and seal its real requirements/checks and
plan. The detached option creates a new child only; it never reassigns `active.json`.
Activate the coordinator's intended child with `proof.py activate --task PATH` when
appropriate. Its context retains the root ID for stop-hook decisions.

Preserve existing write restrictions and worktree policy. A new v3 installation is
not permission to replace another active session. A root revision must retain the
original request/requirements and history; it cannot rewrite an old seal in place.

## 3. Register the execution graph
Adapt `assets/templates/workflow-plan.json`. Every node links one existing sealed
child. Cover every child linked by the root. Mark the actual root integration child
as `role: integrate` and make it depend on all other contributing nodes.

```text
python <skill>/scripts/workflow.py --project . init --plan workflow-plan.json
python <skill>/scripts/workflow.py --project . ready --goal mission
python <skill>/scripts/workflow.py --project . claim --goal mission --task backend --worker ACTUAL_HOST_WORKER_ID --lease-seconds 600
```

The 600 above is an example coordination lease, not a mission deadline or resource
grant. Choose and renew based on observed task duration. `claim` returns a unique
worker token and context packet. Keep the token out of public logs. Pass the packet
to the real host worker. The host retains authorization of every actual tool call.
Select serial execution when there is no real delegation tool or dependencies are
tightly coupled; use independent workers for genuinely independent substantial
nodes. File scopes are explicit paths/prefixes, not globs. Resource names such as
`gpu:0`, `carla:2000` and `database:test` are exclusive within the same registry.

```text
python <skill>/scripts/workflow.py --project . heartbeat --goal mission --task backend --token TOKEN --lease-seconds 600
python <skill>/scripts/workflow.py --project . run-check --goal mission --task backend --token TOKEN --check REAL_CHECK_ID
```

`run-check` executes the sealed child's actual command through the existing collector.
External native browser/tool sessions can instead follow the existing evidence
adapter. Do not fabricate receipts to fit the schema. Context files are explicit,
UTF-8, source-hashed and bounded; narrow context rather than silently truncating it.

## 4. Handoff, verification and integration
Save a genuine worker handoff as a nonempty project-relative artifact. Complete
actual proof checks and required inspection/task progress through `proof.py`.

```text
python <skill>/scripts/workflow.py --project . handoff --goal mission --task backend --token TOKEN --evidence .runtime-proof/backend/handoff.md
python <skill>/scripts/workflow.py --project . verify --goal mission --task backend
python <skill>/scripts/workflow.py --project . root --goal mission
```

Handoff releases cooperative ownership and marks IMPLEMENTED, never VERIFIED.
Verification calls the real child gate. The root command reruns original-root
verification. Stored task states are scheduling history; they are not fresh root
acceptance when the product changes. Reverify relevant children and final integration
on current source. Avoiding duplicate work must not become reuse of stale proof.

## 5. Interruptions and uncertain side effects
An expired worker token cannot hand off or renew. Locks are NOT automatically stolen
on expiry: the old process may still run. Inspect actual process ownership and
source/effects, save that evidence, then use `recover --goal ID --task ID --evidence
PATH`. This is a coordinator action and a truthful attestation, not an OS proof that
the worker died. Cooperative actors must respect the registry. Outside writers are
not controlled by SQLite; use separate sandboxes/permissions for stronger isolation.

Before an externally observable operation, call `operation` with a stable key and
SHA-256 of canonical input. A new key yields `execute: true` but NO permission grant.
After an interruption the key remains UNKNOWN_EFFECT; a repeated key never executes
blindly. Inspect the real downstream state and use `reconcile --key KEY --outcome
OBSERVED_DONE|OBSERVED_NOT_DONE --evidence PATH`. Even observed-not-done does not
automatically retry; choose a new explicitly linked attempt after review. Original
approval and host admission still govern. This is not universal exactly-once delivery.

## 6. Audit and host conformance
`workflow.py audit --goal ID` exports hash-linked events without worker tokens or
raw prompts. SQLite triggers make events append-only through normal operations;
a database owner could still rewrite the database, so this is not signed evidence.
Keep the registry local and outside public commits. An independent enterprise gate
needs a trusted evaluator/store and access controls outside the implementer.

Validate the installed host separately: real skill read, fresh version attestation,
actual tools, real worker dispatch, tested hook callback, and unchanged provider.
No Copilot Desktop/CLI/VS Code API integration is asserted simply because this
script exists. `install.py` installs the existing supported hook adapters, and the
updated callback provides root-aware decisions when the host invokes it.
