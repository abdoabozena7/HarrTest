# HarrTest 4.0 Gold: runbook

Use Gold when a task needs independent workers, reviewable decisions and a
measured acceptance gate. The coding host conducts the conversation, dispatches
agents and runs tools. The Python scripts use the host's existing project and
retained evidence; they do not launch agents or grant permissions.

## 1. Understand the request before splitting it

Use `root_gate.py init` to retain the original request. Summarize what the user
will observe for every requirement. Check likely decision points: boundary
values, malformed input, existing data, access, failure recovery, and interaction
with existing behavior. Ask the user about each **unresolved material** case.
Where the user or authoritative repo contract already answers it, cite that
answer. Exclude a case only with a reason and evidence for why it cannot affect
this task. If an answer changes acceptance after sealing, preserve the old
records and register a reviewed revision.

Follow the [schema-3 coverage process](v3-workflow.md#1-bind-the-original-goal).
Set `"protocol": "golden-v1"` on the schema-3 root before sealing. Link all
implementation, independent QA and integration proof children to its requirements.
Keep the exact original request local.

Use this intake structure:

```json
{
  "schema": 1,
  "request_sha256": "<SHA256 of original-request.txt>",
  "interpretation": "Export must preserve the visible columns and their order.",
  "requirements": [{"id": "export", "meaning": "Download the visible columns in order", "evidence": [{"path": ".runtime-proof/inputs/request.txt", "sha256": "<SHA256>"}]}],
  "edge_cases": [{"id": "no-rows", "requirement_ids": ["export"], "question": "What downloads when there are zero rows?", "resolution": "Download a CSV with headers only.", "source": "user", "evidence": [{"path": ".runtime-proof/inputs/answer.txt", "sha256": "<SHA256>"}]}],
  "decisions": [{"id": "headers", "requirement_ids": ["export"], "choice": "Write the CSV header before iterating rows.", "rationale": "The empty export still needs ordered column headers.", "evidence": [{"path": ".runtime-proof/inputs/answer.txt", "sha256": "<SHA256>"}]}]
}
```

Every root requirement needs an interpretation, edge case disposition, and
decision coverage. Allowed edge sources are `user`, `repository_contract` and
`not_applicable`. Keep nonempty, project-relative copies of the exact
source excerpts or observations that supported the decision. The gate verifies
bytes and links; a reviewer must assess whether the evidence supports the
interpretation. A path and hash cannot prove who authored a reply.

## 2. Freeze the comparison and prepare the graph

Choose observable cases and controls. Keep the runner and relevant conditions
matched; for live agent trials record the host, loaded skill, model, inputs,
permissions, run budget and independent evaluator. Include a valid case that
must pass and a faulty or incomplete case that must fail. Put the protocol in
a separate file from the eventual results:

```json
{
  "schema": 1,
  "mode": "fixture",
  "controls": {"runner": "Same public CLI checks and input fixture", "environment": "Same Python runtime and isolated projects"},
  "baseline": {"id": "before-export-fix", "source_sha256": "<baseline source digest>"},
  "cases": [
    {"id": "ordinary", "expect": "accept", "oracle": "CSV includes the agreed header and data."},
    {"id": "denied", "expect": "reject", "oracle": "Unauthorized request produces no downloadable content."}
  ],
  "thresholds": {"min_candidate_correct": 2, "max_candidate_false_accepts": 0, "min_correct_gain": 0}
}
```

Set thresholds for the intended outcome. A gain of zero is useful for a
no-regression release; a claim of improvement needs a positive observed gain
on the measure it names. `fixture`, `offline` and `live` are distinct
evidence modes. Compare the same cases on the pre-change and post-change
sources. Keep both positive and negative controls and raw failures.

Adapt the [workflow plan](../assets/templates/workflow-plan.json) with this top-level
configuration. Use the sealed root's ID as the workflow ID.

```json
"golden": {
  "intake": ".runtime-proof/gold-intake.json",
  "protocol": ".runtime-proof/gold-protocol.json",
  "measurement": ".runtime-proof/gold-results.json"
}
```

Each node declares `prompt` and `execution`. Give each implementation a
small, standalone prompt with the outcome, acceptance, interfaces, and scoped
files. Put only relevant bounded context in `context_files`. Declare actual
native `subagent` execution for implementation and review. The tester uses
`role: "review"` and `reviews: ["implementation-node-id"]`, depends on that
implementation, and has no product write scope. Its child proof fingerprints
the sources it tests. The final integration node follows all other nodes.
Order conflicting scopes and exclusive resources explicitly.

```text
python <skill>/scripts/golden.py --project . inspect --plan gold-plan.json
python <skill>/scripts/workflow.py --project . init --plan gold-plan.json
python <skill>/scripts/workflow.py --project . ready --goal mission
```

Registration freezes the canonical intake and protocol digests with the
original root and child seals. Review the frozen protocol before measuring.

## 3. Dispatch and test through the host

Claim independent ready nodes and send the returned packets through actual
native host invocations without waiting for the first worker to finish.
Use real host worker identities and preserve raw invocation traces and timing.
If the host assigns an identity only after launch, claim with a distinct lease
alias and report the assigned identity in the handoff's `host_worker_id`.
Keep lease tokens private. The packet contains the focused prompt, context and
acceptance checks and can be saved for a worker without coordinator transcript
access. A portable prompt does not imply an offline model is installed.

```text
python <skill>/scripts/workflow.py --project . claim --goal mission --task exporter --worker HOST_WORKER --lease-seconds 600
python <skill>/scripts/workflow.py --project . run-check --goal mission --task exporter --token TOKEN --check CHECK_ID
python <skill>/scripts/workflow.py --project . handoff --goal mission --task exporter --token TOKEN --evidence .runtime-proof/export-handoff.json
python <skill>/scripts/proof.py step --task .runtime-proof/exporter --id STEP_ID --status VERIFIED --note "Observed the agreed output"
python <skill>/scripts/workflow.py --project . verify --goal mission --task exporter
```

Handoff evidence is a JSON file. Record the task ID, generation, packet digest
and worker ID from the claim, and expected and observed results keyed by sealed
check ID. For delegated work retain the host invocation ID, trace and
timezone-aware start/end timestamps for the actual execution. Record each
consequential choice, why it was made, and its evidence paths and hashes.
```json
{
  "task_id": "exporter",
  "generation": 1,
  "packet_sha256": "<packet_sha256 from claim>",
  "worker_id": "<host worker ID from claim>",
  "invocation_id": "<actual host invocation ID>",
  "started_at": "<ISO 8601 start with timezone>",
  "finished_at": "<ISO 8601 finish with timezone>",
  "trace": ".runtime-proof/host/exporter-run-1.txt",
  "observations": {"empty-export": {"expected": "Only the ordered header", "observed": "The CSV contained one header line and no data rows"}},
  "decisions": [{"id": "empty-output", "choice": "Write the header first", "rationale": "Zero data rows must still produce the ordered header", "evidence": [{"path": ".runtime-proof/inputs/answer.txt", "sha256": "<SHA256>"}]}]
}
```

The trace must contain the exact host worker ID, invocation ID, packet digest,
and timestamps. A delegated child plan step also requires its actual
`--agent-ref` and retained `--handoff`, as in the [v3 workflow](v3-workflow.md).
Run checks during that invocation under its current lease. Keep each
generation's handoff and trace in separate files. A review or integration
handoff may have an empty `decisions` list when no new decision was made.

Implementation handoff is followed by a different worker's sealed checks. Test
each child on current source, then execute the end-to-end entrypoint. If testing
finds a failure, preserve the failed check and reopen the affected node and its
dependents with `workflow.py retry --goal mission --task NODE --evidence PATH`.
To relinquish a failed check's still-running lease, add its current `--token`
and record the failure before retrying the implementation.

## 4. Compare and verify the original goal

```text
python <skill>/scripts/golden.py --project . candidate --plan gold-plan.json
python <skill>/scripts/golden.py --project . compare --plan gold-plan.json
python <skill>/scripts/workflow.py --project . root --goal mission
```

The candidate command fingerprints the source scopes, contracts and verifier
dependencies of the sealed proof children and the Gold controllers. Use that identity for the candidate
records. Save the comparison results as schema 1 JSON with `protocol_sha256`
(from `inspect`), `candidate: {id, source_sha256}`, and `attempts`. Each
attempt has `case`, `variant` (`baseline` or `candidate`), `outcome`
(`accept`, `reject` or `error`), `source_sha256` and
`evidence: {path, sha256}` for its own evaluator receipt. The receipt is JSON
with `schema: 1`, the same `case`, `variant`, `outcome` and `source_sha256`,
plus a nonempty `artifacts` list of `{path, sha256}` references to actual
command output or observations. The comparison checks the receipt and raw
bytes against the report so a result cannot be relabelled in the report alone.
Record error attempts as
errors, even for cases that should reject. Do not retry selectively or drop an
arm to improve the reported result.

The root requires fresh original acceptance, strict workflow evidence and a
complete comparison that meets the frozen thresholds. Direct root verification
and a supported active stop hook use the same root gate. A baseline comparison
or a passing child alone cannot authorize completion.

The local registry checks cooperative scheduling, scope, identities declared
in the trace, and evidence consistency. It cannot prove real-world identity,
the completeness of a semantic review, the integrity of an evaluator who
controls the workspace, or improved model quality. For consequential use,
give reviewers independent access to acceptance and keep the evaluator and raw
evidence outside worker write access. See [release measurements](v4-validation.md).
