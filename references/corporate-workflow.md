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
python <skill>/scripts/root_gate.py seal --goal .runtime-proof/root-goals/mission
```

Helper outputs are inputs, not acceptance verdicts. Baseline executions precede
plan creation and sealing. The seal requires current source still match baseline;
a post-change snapshot must never be relabeled baseline.

## Root and plan

Use [the schema4 template](../assets/templates/root-contract-v4.json). Keep root
coverage, request spans, separate coverage challenge and integration child from
schema3. Register the Team and complete its scope review before sealing the
Corporate root. The root seal pins the Team plan, baseline and accepted review.
Set `schema:4`, `protocol:"corporate-v1"` and the
following fields.

```json
{"production_team":"mission","team_decomposition":"reviewed-v1","corporate":{"plan":".runtime-proof/corporate-plan.json","report":".runtime-proof/corporate-report.json"}}
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

## Execute, review and verify

Use [Team schema2](production-teams.md) for bounded owners and actual host capacity.
Parallelize independent ready scopes, serialize dependencies and shared resources,
and route failures to existing owners. Integration can be validation-only.
Run changed-behavior and preservation checks through the proof collector.
If QA finds an apparent inherited fault, replay the same condition on baseline
and candidate without changing the oracle. Record the affected requirements and
evidence. Record unrelated existing findings with their limitations and keep
the repair scope guided by the request and project policy.

The mutable report contains schema1, plan_sha256, current source, executions and
review. Execution references are `{receipt:project-relative-path,sha256:digest}`.
The gate rechecks captured outputs/artifacts/assertions and current check identity,
rather than trusting a passed boolean. A later run supersedes old candidate evidence.

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
