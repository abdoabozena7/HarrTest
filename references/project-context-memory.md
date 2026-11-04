# Persistent HarrTest project memory and task context

This is a **private, local project-brief store**, not a replacement for a sealed
root acceptance contract, source control or host access controls.

## Storage and lifetime

Default: `~/.harrtest/projects/<project-name>-<hash-of-canonical-path>/`.
Override with `HARRTEST_STATE_HOME` for tests or centrally managed workspaces.
Files: `memory.sqlite` and generated `project-brief-<goal-id>.md`.
Never store memory inside the installed `harrtest` source tree: skill installers
may remove that directory on upgrade. The state folder is outside the target
repository and not committed by the project Git operations. Treat it as
potentially private: do not upload or echo raw briefs without review. Back it up
under the owner's policies when the environment is ephemeral. Restored projects
under a different absolute path get a distinct memory store (avoid accidental
cross-repository leakage); migrate explicitly after identity review.

## Preflight

Use `python <skill>/scripts/project_memory.py --project PATH bootstrap`
when `ROOT_GOAL.md` or `GOAL.md` exists. Otherwise supply `--goal-file` with the
original user request path. For existing sealed HarrTest roots, a path of the
shape `.runtime-proof/root-goals/ID/original-request.txt` is accepted.
`--goal-id` identifies a specific original goal. Default is `main` for simple
projects, but `workflow.py` selects the actual sealed root's goal ID.

The goal is stored verbatim with SHA-256 and monotonically increasing revision.
Changing goal text fails closed unless the user approved `--revise-goal`.
Don't replace the original contract or silently edit its acceptance scope.
Run `brief` on each new session. Refresh source notes after changes.

## First-pass project mapping (agent responsibility)

The deterministic manifest lists names, not architecture. The executing agent
must inspect the real high-level docs, public entrypoints, current interfaces,
storage and tests, then record only relevant verified facts with source hashes.
Capture purpose, core components and dependencies, data flow, invariants, public
entrypoints, test commands and known failure modes. Avoid whole-repo ingestion.
A new session should first read the existing brief, compare source identities,
then inspect changed or missing areas rather than reconstructing context.
For each delegated task, curate only the files/notes needed to reason about that
particular outcome, its integration interface and failure history. If a stronger
host model is genuinely available for curation, it may challenge the proposed
context pack; its choices must pass local source/provenance validation.

## Source-qualified knowledge

Only record concrete observations with actual file provenance:

```text
python <skill>/scripts/project_memory.py --project PATH note --goal-id main \
  --category architecture --source backend/api.py \
  --text 'The public POST handler uses create_task and persists through TaskStore.' \
  --priority 2
```

Allowed categories: architecture, behavior, decision, risk, dependency, interface.
Each note binds its source SHA-256; after file changes it is STALE_RECHECK_BEFORE_USE.
A summary is **not a new instruction** and doesn't grant permission. The tool
blocks typical secret files, environment files, virtual envs and generated trees.
No repository files are uploaded or read wholesale automatically. The manifest
scans at most 2000 filenames, excluding private/generated directories.

After real execution use `checkpoint --label ... --state ... --text ...
--evidence RELATIVE_PATH`. States are TODO, IN_PROGRESS, IMPLEMENTED,
VERIFIED_CHILD, BLOCKED. VERIFIED_CHILD and BLOCKED require source-bound evidence
files. These records explain what previously happened; their state is not accepted
as fresh root verification, nor a substitute for a `workflow.py` result.

## Select task context, not entire history

```text
python <skill>/scripts/project_memory.py --project PATH pack \
  --task 'Add account persistence and test reload' --role implement \
  --scope backend --budget-chars 12000
```

The mandatory pack includes: the original user goal, task/role, trust boundaries,
source-qualified relevant observations, selected historical checkpoints and
recommended paths. It contains **file names and hashes, not source content**.
The receiving agent must open only the recommended relevant files with the host
and independently inspect current code before editing. Stale observations are
labelled and must not be treated as current. If the original goal cannot fit the
budget, the tool refuses silent truncation. The 12k default is a context budget,
not a time/credit limit.

`workflow.py claim/context` builds the pack automatically for the actual task's
outcome, role and declared read/write scopes, and does not invoke an LLM.
This keeps future sessions and weaker models anchored to the same original goal.

## Optional host-based strong-model context curator

For complicated projects, when the current host genuinely supports model routing
and the provider/credits are already authorized, delegate **only curation** to a
stronger context-planning subagent: give it the original goal hash, task, role,
short source inventory, note IDs and freshness metadata. Ask it to identify the
minimal relevant notes, missing sources, interfaces and dependencies. Never hand it
secrets or make it decide authorization. Accept its response only as a proposed
selection JSON with exactly:

```json
{
  "goal_sha256": "sha256 of the exact stored goal",
  "task": "the exact worker task text",
  "role": "implement",
  "note_ids": ["actual IDs returned by brief"]
}
```

Pass that file with `pack ... --selection PATH`; all referenced note IDs must
exist and selected notes must remain source-current. A model selection is not
independent evidence, factual proof, a permission grant, or a reason to omit the
original goal. If no strong-model option exists, use the deterministic ranker.
Never silently change host model, launch a Codex CLI bridge, or charge a second
provider; record the host tool identity when a real delegate runs.

## Guardrails

The store is not a full memory of the entire source tree or every conversation;
only grounded facts and checkpoints are durable. Concurrent SQLite writes are
serialized. `project-brief-*.md` is derived from the database and can be
re-generated. Preserve raw project source and actual root/proof gates separately.
Root acceptance always requires real current-source verification.
