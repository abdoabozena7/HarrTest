---
name: harrtest
description: Deliver verified software changes scaled to user intent and task risk: execute ordinary tasks (data fetching, scripts, single-page UI, localized fixes) directly with zero subagent or branch ceremony, and escalate to scoped native implementation owners and independent QA only when requested or when task risk crosses the execution threshold. Does not apply to conversation-only requests.
---

# HarrTest 5

> **Role Check:** If your prompt begins with `You own implementation scope` or `You are independent QA`, you are ALREADY an admitted child worker—**do not** run `quickstart`, `integrate`, or spawn subagents; execute your packet directly.

## 0. Execution Threshold Contract (`execution-threshold-v1` — Evaluate First)

Stay **normal and direct on ordinary daily tasks**. Before creating `.runtime-proof/`, running `quickstart`, spawning **any** `task` subagent, splitting files across owners, or touching git branches/worktrees, evaluate both dimensions ([full contract](references/execution-threshold.md)):

1. **Did the user ask for it? (`user_intent`)**
   - **Branches & worktrees (`false` by default):** **Never** create or switch git branches or worktrees unless the user explicitly requested a branch or worktree.
   - **Direct / simple intent:** If the user asks for something straightforward or says no subagents/ceremony, stay in **`direct`** (`0` subagents, `0` `.runtime-proof` files).
   - **Explicit managed intent:** Escalate on user intent **only** when `HARRTEST_CORPORATE_GOAL` is set or the user explicitly requests subagents, independent QA, Team decomposition, or Corporate root verification.

2. **Does the task itself cross the subagent threshold? (`task_signals`)**

   | Tier | When It Applies | Subagents | Branches / Worktrees | `.runtime-proof` Ceremony |
   | --- | --- | --- | --- | --- |
   | **`read-only`** | Fetching/inspecting/summarizing data without repo edits, code questions, debugging diagnosis, or explicit read-only / single-step plan mode | **0** | **No** | **None** |
   | **`direct`** *(Default for ordinary work)* | Data-fetching/transformation scripts, API/DB queries, single-page or single-component UI, copy/style/config/docs updates, small 1–3 file greenfield prototypes, or localized 1–3 file bugfixes/features without high-risk shared-contract blast radius | **0** *(main agent executes & checks inline)* | **No** *(unless user asked)* | **None** *(no `quickstart`, `mission.py`, or `team.py`)* |
   | **`managed-single`** | Cross-cutting change, shared public CLI/API/library contract with a high-risk domain (`security_boundary`, `destructive_migration`, `concurrency_or_recovery`, `strict_performance_or_streaming`, `visual_craft_system`) or 4+ write files, 2+ intersecting high-risk domains, 4+ file / detail-reviewed greenfield app, or user-requested QA | **1 `impl` + 1 `qa`** *(never split into extra writers)* | **No** *(unless user asked)* | `team.py quickstart` |
   | **`team-parallel`** | User requested team split, **or** 2+ genuinely independent deliverables that **all** satisfy: `disjoint_write_scopes`, `stable_interface`, `independent_checks`, and `estimated_write_files >= 2` | **2+ disjoint owners + 1 `qa`** | **No** *(unless user asked)* | `team.py quickstart` (`tasks: [...]`) or `greenfield` `team.py init` |
   | **`corporate`** | `HARRTEST_CORPORATE_GOAL` set or explicit Corporate / `schema: 4` root request | **`plan_review` + `coverage_review` + owner(s) + `qa`** | **No** *(unless user asked)* | `corporate-v1` root + `team.py` |

- **Optional 1-command threshold check** (for borderline tasks, no temp file needed):
  ```text
  python -B "<skill_base_dir>/scripts/team.py" --project "." threshold --kind <kind> --write-files <N>
  ```
- **Hard anti-bloat rule:** Never split a single page, single data pipeline, or shared invariant across multiple subagents, and never spawn subagents per file or per quality layer.

## Direct Execution Workflow (`read-only` & `direct` — Ordinary Daily Tasks)

When the threshold resolves to **`read-only`** or **`direct`**:
1. **Inspect concisely (1–3 tool calls):** Read only the directly relevant files, endpoints, schemas, or callers. If the user asked for a read-only plan or single-step plan revision, return only that concise plan or revised step and stop.
2. **Execute directly in the current agent:** Fetch the data or edit/create the target file(s) directly—preserve surrounding behavior, conventions, and error handling without creating `.runtime-proof/` state or spawning workers.
3. **Verify proportionally:** Run the smallest real check covering the result (script/query execution, targeted test, typecheck, or build) and report clearly.

## Managed Workflow (`managed-single` & `team-parallel` — Above Threshold Only)

When user intent or task risk crosses into **`managed-single`** or **`team-parallel`**, start as coordinator. **Do not** waste tool calls reading `VERSION` or reference markdown files unless a specialized mode at the bottom applies (`HARRTEST_CORPORATE_GOAL`, `greenfield` new product, browser UI, or simulation). `team.py quickstart` pins `VERSION` automatically.

### 1. Focused Inspection (2–4 tool calls)
- Read only the affected entrypoints, callers, config/options, and adjacent existing tests.
- Map every requested behavior, error/no-op boundary, security risk (symlinks/hardlinks/aliasing, relative paths/`chdir`, metadata leakage), and performance/streaming invariant.

### 2. One-Command Pre-Edit Admission (`team.py quickstart`)
Before **any** product edit, write `.runtime-proof/quickstart.json` and run:
```text
python -B "<skill_base_dir>/scripts/team.py" --project "." quickstart --spec .runtime-proof/quickstart.json
```
Minimal `.runtime-proof/quickstart.json` (use forward slashes):
```json
{
  "id": "mission",
  "request": "<exact verbatim user request>",
  "contract": "<shared architecture, interface, error-atomicity, security, and performance/streaming invariants>",
  "outputs": ["src/pkg/mod.py", "tests/test_feature.py", "docs/usage.rst"],
  "read_sources": ["tests/test_existing.py"],
  "validation_context": [],
  "baseline_check": {
    "command": ["{python}", "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", "tests/test_existing.py"],
    "stdout_contains": "passed",
    "timeout_seconds": 120
  },
  "acceptance_check": {
    "command": ["{python}", "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", "tests/test_feature.py", "tests/test_existing.py"],
    "stdout_contains": "passed",
    "timeout_seconds": 120
  },
  "preserved_behavior": {
    "path": "src/pkg/mod.py",
    "location": "public CLI/API entrypoint",
    "behavior": "Unchanged behavior, exit codes, and output format when new opt-in is not used."
  }
}
```
- **List every file the implementer will edit or create in `outputs`** (product code, new/updated test files, and docs). `quickstart` auto-detects planned new files as absent at baseline, computes SHA-256s for existing files, seals `proof.py`, executes `baseline_check` on untouched source, initializes the `preservation-v1` ledger, registers the `schema: 2` `review-loop-v1` Team, and returns the ready native worker packet(s).
- Keep **one owner (`"impl"`, default)** for cohesive features sharing an invariant. Pass `"tasks": [{"id": "core", "outputs": [...]}, {"id": "cli", "outputs": [...]}]` only when genuinely disjoint deliverables have a stable interface and independent checks.
- Put read-only contract files that must stay byte-identical in `validation_context`.

### 3. Scoped Native Implementation (`task` -> `handoff --note`)
- Dispatch each ready packet using the native `task` tool:
  - `name`: exact packet `task_name` (e.g. `"impl"`)
  - `prompt`: exact packet `message` (do not summarize or replace it!)
  - `agent_type`: `"general-purpose"`
  - `mode`: `"background"` (retain `agent_id`). **Wait discipline:** When no other ready worker packet exists, **end your turn immediately** after launching `task(mode="background")` to await the completion notification—do **not** run extra searches or poll `read_agent` while waiting; once notified, call `read_agent(agent_id, wait=True)` once.
- **Coordinator rule:** Never edit worker-owned product files directly.
- **Worker rule:** Use native editor tools (`apply_patch` / `edit` / `create` — never shell redirection) so native `fileEdits` provenance is recorded; run both new and existing tests; fix any warnings-as-errors or test-helper signature bugs; finish with `team.py ... handoff --team mission --task <owner> --note "<summary>"`.

### 4. Integrate & Run Independent 6-Angle Adversarial QA (`integrate` -> `task(qa)` -> `qa-submit`)
- Run:
  ```text
  python -B "<skill_base_dir>/scripts/team.py" --project "." integrate --team mission
  ```
- Dispatch the returned `qa` packet via `task` (`name: "qa"`, `prompt`: exact `qa.message`, `agent_type: "general-purpose"`, `mode: "background"`), **end your turn immediately** to await notification, then call `read_agent(qa_agent_id, wait=True)` once.
- Independent `qa` keeps product files strictly read-only, inspects `git diff HEAD`, writes & runs an independent adversarial probe in `.runtime-proof/qa_probe.py` covering all **6 layers** (`functionality`, `preservation`, `architecture`, `security`, `performance`, `resilience` + upstream test-suite validity), writes `.runtime-proof/teams/mission/qa-summary.json`, and runs `team.py qa-submit --team mission --summary ... --verdict pass|fail -- <ACTUAL_ARGV>`.

### 5. Owner Repair Loop & Final Verification (`repair` -> `verify`)
- If `qa` returns `fail`, do **not** stop or edit code as coordinator. Run the printed repair command:
  ```text
  python -B "<skill_base_dir>/scripts/team.py" --project "." repair --team mission --task <owner> --evidence .runtime-proof/teams/mission/qa-evidence.json --observation "<scoped fix plan>" --refresh-note "<source diagnosis>"
  ```
- Send the returned `packet.message` to the original owner's `agent_id` with `write_agent` + `read_agent(wait=True)`, re-run `integrate`, and send the fresh `qa` packet to the original `qa` `agent_id` with `write_agent` + `read_agent(wait=True)` so `qa` re-runs fresh checks and resolves every prior finding ID. (For evidence-only blockers with `owner: null`, resume `qa` without dummy product edits.)
- Finally run:
  ```text
  python -B "<skill_base_dir>/scripts/team.py" --project "." verify --team mission
  ```
  Claim verified completion **only** when `verify` returns `"passed": true` and all required checks pass on current source.

## Quality & Preservation Invariants
- **Preservation:** Replay unchanged paths, empty inputs, and rejected/error operations; partial failures must leave existing files/state byte-identical and clean up temporary files.
- **Security:** Enforce destination symlink/hardlink/alias rejection, relative-path anchoring against initial invocation directory, and strict schema non-leakage.
- **Performance:** Zero extra traversal or I/O when an opt-in is unused; for streaming features, flush incrementally per item without O(N) serialized buffering.
- **Anti-Theater Tests:** Derive expected results from the contract, not the implementation; verify newly added upstream tests actually pass under project warning/runner settings without broken mocks or signatures.

## Specialized Modes (Load Reference Only When Needed)
- **Enrolled Corporate Root (`HARRTEST_CORPORATE_GOAL` set or explicit schema-4 Corporate request):** Read [corporate-workflow.md](references/corporate-workflow.md). Save/reuse original request, use `decomposition: "reviewed-v1"` and `root_protocol: "corporate-v1"`, run `plan_review` and `coverage_review`, and `root_gate.py seal` before `team.py packets`, then `root_gate.py verify` at completion.
- **New Product from Scratch (`greenfield`):** Read [quality-intent.md](references/quality-intent.md) and [production-teams.md](references/production-teams.md). Use `kind: "greenfield"`, `decomposition: "reviewed-v1"`, and `integration.detail_review` for visual/consequential details.
- **Browser / Simulation / Multi-Stage Builder / Memory:** Read [web-validation.md](references/web-validation.md), [simulation-validation.md](references/simulation-validation.md), [project-builder.md](references/project-builder.md), or [project-context-memory.md](references/project-context-memory.md).
