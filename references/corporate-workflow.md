# Corporate: change existing software with current evidence

Use this for substantive changes to an existing system. One bounded implementation
owner is valid; independent testing and review remain necessary. Follow the
project's architecture, public contracts and conventions, without imposing a
particular language, application type or deployment pipeline.

## Before editing

Save the exact request with `root_gate.py init --project . --id mission
--request-file request.txt`. Inspect actual code, callers, dependency boundaries,
architecture records and tests. Resolve meaning from controlling contracts first;
ask only about unanswered material choices. Cite exact source versions/excerpts.
Archive needed evidence privately before changes, retaining its original authority.

For new work initialize the
[Feature Preservation Contract and Completion Ledger](feature-preservation-and-completion.md)
using the same goal ID, original request, source scope and proof receipts.
Use `mission_protocol: preservation-v1` on both the Team and root. Keep
preserved behavior and required TODOs mapped through to the root, including
any additional root integration requirement. Do not edit the product while
discovery or an approval for the affected behavior is still unresolved.

Register proof children with `proof.py` contracts. Define preserved-behavior and
requested-change checks with independent oracles, and run baseline checks now.
Keep their original `runs/.../receipt.json` references. Known baseline failures
need actual failed runs and independent acknowledgement; they do not waive relevant
security/correctness requirements. Include implementation, affected consumers,
tests/verifiers, configuration and dependency locks in complete `source_paths`.
Use the identical scope in proof execution contracts. Do not omit deleted paths.
For explicit file roots that may be absent before addition or after deletion,
declare the opt-in child `absent_source_paths` list as a distinct subset of
`source_paths`. Those declared absent paths retain null manifest entries; an
unlisted missing path still fails. This preserves legacy missing-source checks
and avoids silently broadening an exact file scope to its parent directory.

```text
python <skill>/scripts/corporate.py snapshot --project . --source src --source tests
python <skill>/scripts/corporate.py execution-ref --project . --receipt .runtime-proof/verify/runs/baseline/RUN_ID/receipt.json
```

Helper outputs are inputs, not acceptance verdicts. Baseline executions precede
plan creation and sealing. The seal requires current source still match baseline;
a post-change snapshot must never be relabeled baseline.

## Root and plan

Register Team schema 2 with `decomposition: "reviewed-v1"` and
`root_protocol: "corporate-v1"` on this substantive route. Use the same Team
ID and root goal ID. Omit `request` from the Team plan and initialize it from
the saved original request.

```text
python <skill>/scripts/team.py --project . init --plan .runtime-proof/team-plan.json --request-from-root
```

The registered Team state retains the saved request, including trailing whitespace.
The input plan file remains available as the draft. When the integration proof
contract is sealed and the actual baseline checks have run, create the Corporate
drafts from those records.

```text
python <skill>/scripts/corporate.py scaffold --goal .runtime-proof/root-goals/mission --proof-task verify --baseline-check preserved-behavior --author coordinating-planner
```

Repeat `--baseline-check` for each retained baseline run in that proof task,
including applicable measurements. The command copies the exact source scope,
actual receipt references, known task ownership and all six layer names. Fill
the printed missing fields in `root-contract.json` and `corporate-plan.json`.
The scaffold begins with one root requirement ID per Team outcome. Adjust the
mapping if the independently reviewed request requires additional requirements.
The [schema4 template](../assets/templates/root-contract-v4.json) also supports
manual authoring. Each attempt keeps its own original request and artifacts.

After completing the draft, use `corporate.py coverage-packet --goal` for the
independent reviewer. The packet binds the current request, span and acceptance
hashes. Dispatch its `task_name` and `message` exactly. Have the reviewer inspect
the actual request, scope and span mapping and write
`coverage-review.json` in the goal directory. The artifact includes those
hashes, `method`, `planner`, `reviewer`, `unresolved_findings`, `verdict` and
concrete `observations`. Then run `corporate.py bind-coverage --goal` to link
that artifact. Run the returned Team plan review packet before sealing too.

The root and Team bindings have the following shape.

```json
{"schema":4,"protocol":"corporate-v1","mission_protocol":"preservation-v1","production_team":"mission","team_decomposition":"reviewed-v1","corporate":{"plan":".runtime-proof/root-goals/mission/corporate-plan.json","report":".runtime-proof/root-goals/mission/corporate-report.json"}}
```

The plan is schema1 with request_sha256, author, created_at and source_paths:

Full root acceptance requires the bound schema2 Team, including actual native
implementation and independent QA. Corporate task IDs, output ownership and
dependencies must match it, and verification roots must cover every Team output.
Standalone Corporate quality results cannot substitute for this root requirement.

Map requirements to existing responsibilities before choosing the owner count.
If two scopes can implement and test against an agreed interface with disjoint
write sets, give each its own implementation owner and dispatch both together
when the host has capacity. Sharing a feature, output format, or public contract
does not alone create an implementation dependency. Record a real blocking input
when a dependent worker must wait. For a single owner, cite the shared invariant
or inseparable write scope that makes a split unnecessary. The independent
reviewer compares the decision to the code, contracts, and actual handoffs.
Plan concurrency from the available worker tool and its known limits. Check
actual overlap in the native execution log after dispatch. If ready independent
scopes have to run serially, record the observed host or resource constraint.
Follow the [Team planning review](production-teams.md) before the implementation
owners are dispatched.

| Field | Required content |
| --- | --- |
| context | IDs with architecture/contract/verification roles and citation `{path,sha256,start_line,end_line,excerpt}`. Archive external/user sources with original provenance as contract evidence. |
| requirements | Root IDs, affected `impacts` paths and task IDs. |
| tasks | IDs, depends_on and disjoint production outputs. |
| decisions, edge_cases | Requirement IDs, rationale/resolution and cited context IDs. Separate delegated assumptions from user requirements. |
| baseline | Complete source snapshot, actual checks receipt references, captured_at and reviewed known_failures. |
| layers | Exactly functionality, preservation, architecture, security, performance and resilience. |

Every layer records applicable, rationale, evidence context IDs, criteria and
metrics. Functionality/preservation/architecture are core for existing-code work.
Other non-applicability decisions require separate impact review. Unavailable
required tooling is UNVERIFIED, not NOT_APPLICABLE.

Each applicable criterion has id, requirement_ids, claim, oracle, counterexample,
check and negative_check. Select checks with `{task_id,check_id}`. Meaningful shared
checks can close several criteria; do not create repetitive tests to fill rows.
Negative controls assert the named fault/rejection actually occurred.
For changed validation or side-effecting operations, inventory the affected
input controls from the current contract. Include optional fields, metadata,
configuration and failure signals where they can change behavior. Exercise
distinct allowed values and contract-forbidden inputs. For atomic rejection,
place a rejected input after valid work and assert that the relevant persisted
state, emitted events or external effects remain at the required boundary.

Preservation also declares baseline_check. Its current check must replay the old
command with unchanged assertions, expected exits, mode and role. A feature test
cannot replace an old-behavior replay. The root seal binds child check definitions;
re-sealing a child cannot redefine the original oracle.

Applicable performance declares repeated numeric samples (at least3), matching
profile/unit, JSON pointers into actual captured artifacts, direction and justified
predeclared regression/noise bounds. Cite project SLOs or baseline measurement,
rather than universal FPS/latency limits. High noise is UNVERIFIED; an actual bound
violation is FAIL. Preserve output correctness while reducing measured cost.

Seal while the current source still matches the baseline and the independent
scope review is current. Only then request the substantive Team owner packets.

```text
python <skill>/scripts/root_gate.py seal --goal .runtime-proof/root-goals/mission
python <skill>/scripts/team.py --project . packets --team mission
```

The dispatch check ties the reviewed Team state and actual pre-edit source to
the immutable root, including the proof check and verifier hashes. If the
check rejects the inputs, resolve the reported discrepancy before dispatch.
Every schema-4 seal pins its exact Team state. The Team's owned-file baseline
must agree with the Corporate source baseline collected for the same change.

### Optional Copilot CLI readiness guard

For a session explicitly designated for a substantive Corporate change, generate
a local hook fragment using the checkout, goal ID and Copilot session UUID.

```text
python <skill>/scripts/copilot_guard.py config --project . --goal mission --session SESSION_UUID
```

Save the generated JSON as `.github/hooks/harrtest-corporate-local.json` in
the local checkout through its existing workspace approval process. Start
Copilot CLI with the same UUID via `--session-id`. Keep the fragment local and
remove it when the session ends. Existing hook files and both legacy and narrow
Team workflows use their existing configuration.

For that checkout and session, the hook denies supported native editor actions
on product files and parent `task` dispatch until `team.py packets` admits the
reviewed Corporate root. Use the same pinned HarrTest package for the hook and
the Team commands. Before sealing, dispatch the exact `plan_review` and
`coverage_review` packets as separate reviewer tasks. Use a supported built-in
review worker (`general-purpose` or `task`) that can save private evidence. The
coordinator's direct inspection and private `.runtime-proof` writes continue
through normal permissions. The installed Copilot CLI 1.0.104 Explore profile
also exposes shell tools, so it needs the same admission as other worker tasks.

The hook compares fixed admission documents in the enrolled parent session.
Child sessions have separate native identities. The Team and root commands
verify child work, source, selected checks, real ownership and QA. Shell, MCP and
manual writes follow their host permissions. The hook depends on Copilot loading
the local fragment and returning a decision before its timeout. Copilot timeouts
proceed through the normal permission flow. [GitHub Copilot hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference)

## Execute, review and verify

Use [Team schema2](production-teams.md) for bounded owners and actual host capacity.
Parallelize independent ready scopes, serialize dependencies and shared resources,
and route failures to existing owners. Integration can be validation-only.
Final root verification compares the baseline and candidate inside the declared
source paths. Every changed file in that comparison needs a sealed Team owner
or a declared integration output. Review the full project diff as well so a
file omitted from the declared source paths can still be found.
Run changed-behavior and preservation checks through the proof collector.
The mission review records inventoried behavior, TODOs and changed tests with
current check evidence; it does not replace the six-layer Corporate report or
native QA. The root must pass both the managed ledger and the existing gates.
If QA finds an apparent inherited fault, replay the same condition on baseline
and candidate without changing the oracle. Record the affected requirements and
evidence. Record unrelated existing findings with their limitations and keep
the repair scope guided by the request and project policy.

The mutable report contains schema1, plan_sha256, current source, executions and
review. Execution references are `{receipt:project-relative-path,sha256:digest}`.
Once the planned checks run on the final source, use
`corporate.py report-scaffold --goal .runtime-proof/root-goals/mission` to collect
their actual latest receipts. The command prints missing or stale checks and
binds the new report for review. It preserves any existing report. Archive an
earlier report in the private evidence directory before issuing a new one after
repair. The gate rechecks the captured outputs and assertions. A later run
supersedes old candidate evidence.

An independent reviewer differs from author, declares human/fresh-context-agent
method, and binds source_digest, plan_sha256 and report_sha256 (report excluding
review). Review time follows execution. Record decision/edge-case observations
and every layer/criterion verdict. Judge citation relevance, old/new behavior,
test strength, architecture and applicability. The gate checks declared review
structure; it cannot authenticate local identities or automate semantic judgment.

Follow the project's security policy and record which existing trust boundaries,
permissions, data and dependencies the change affects. Refer to the design review,
threat modeling and security testing practices in [Microsoft SDL](https://www.microsoft.com/en-us/securityengineering/sdl/practices)
when choosing risk-specific checks. Capture commands, runtime/tool versions, real
outcomes and limitations.
Minimize sensitive capture; document redaction and rebind changed evidence.
For selective rejection/removal/transformation, test both the intended target and
legitimate near matches. Connect the security outcome to preservation criteria:
overbroad restrictions or loss of nonsensitive values/structure are defects even
if a secret/invalid-input detector reports success. Use requirement-derived
counterexamples rather than producer-selected easy examples alone.

```text
python <skill>/scripts/proof.py verify --task .runtime-proof/verify
python <skill>/scripts/root_gate.py verify --goal .runtime-proof/root-goals/mission
```

Every required layer must PASS. Reviewed inapplicable layers are NOT_APPLICABLE;
FAIL/UNVERIFIED prevent root acceptance. Preserve ordinary failures, repair and
repeat. Changed acceptance/context requires a new declared revision retaining old
evidence, not editing a seal to pass.

Schema2/3 roots, golden-v1 and Team1 retain their meaning. Unsupported host traces
leave native provenance UNVERIFIED; structural receipts cannot prove delegation.
Read [test quality](acceptance-and-test-quality.md) and
[security limits](security-and-limitations.md). Verified means the declared current
checks passed, not a promise about every future input or a hostile-writer boundary.
