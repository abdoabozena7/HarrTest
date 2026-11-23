# Execution Threshold Contract (`execution-threshold-v1`)

HarrTest scales execution ceremony to **explicit user intent** and **actual task risk**.
Ordinary daily work stays fast and direct—zero subagents, zero unrequested git
branches/worktrees, and zero `.runtime-proof/` state files.

## 1. Two Mandatory Questions Before Any Ceremony

Evaluate both dimensions before spawning workers, creating `.runtime-proof/`, or
splitting files across owners:

1. **Did the user ask for it? (`user_intent`)**
   - **Branches & worktrees:** `needs_branch` and `needs_worktree` are **`false` by default**.
     Never create git branches or worktrees unless `requested_branch` or
     `requested_worktree` is explicitly requested by the user.
   - **Direct override:** When the user asks for a quick/simple pass or says no
     subagents (`forbid_subagents: true` or `explicit_mode: "direct"`), stay in
     **`direct`** mode unless an external `HARRTEST_CORPORATE_GOAL` gate is active.
   - **Managed opt-in:** Escalate on user intent only when the user explicitly
     requests subagents, independent QA, Team decomposition, or Corporate root
     verification (`explicit_mode` in `subagents`, `team`, `corporate`, or
     `HARRTEST_CORPORATE_GOAL` set).

2. **Does the task itself require subagents? (`task_signals`)**
   - **Ordinary work (`read-only` / `direct`):**
     - `read_only`: data inspection, queries, codebase questions, debugging
       diagnosis, or staged read-only planning (`0` writes, `0` subagents).
     - `data_or_script`: fetching/transforming data, API/DB scripts, notebooks,
       one-off CLI helpers, or small pipelines without high-risk shared public
       contracts (`direct`, `0` subagents).
     - `single_surface`: single page, single UI component/view, single endpoint,
       copy/styling polish, config, or docs (`direct`, `0` subagents).
     - `localized_change`: cohesive 1–3 file bugfix or feature with no high-risk
       shared public-contract blast radius (`direct`, `0` subagents).
     - Small `greenfield_product` (1–3 files, single cohesive deliverable, no
       `visual_craft_system` detail gate): `direct`, `0` subagents.
   - **Substantial single-owner work (`managed-single`):**
     Crosses the threshold when modifying a `cross_cutting_change`, a
     `shared_public_contract` combined with a high-risk domain or 4+ write files,
     a `destructive_migration`, 2+ intersecting high-risk domains
     (`security_boundary`, `destructive_migration`, `concurrency_or_recovery`,
     `strict_performance_or_streaming`, `visual_craft_system`), or a 4+ file /
     detail-reviewed `greenfield_product`. Uses **1 `impl` owner + 1 `qa` worker**
     (`max_implementation_owners: 1`).
   - **Parallel multi-owner work (`team-parallel`):**
     Allowed **only** when `independent_deliverables >= 2` **and all four**
     splitting invariants hold:
     1. `disjoint_write_scopes: true`
     2. `stable_interface: true`
     3. `independent_checks: true`
     4. `estimated_write_files >= 2`
     If any invariant is missing, `split_allowed` is `false` and ownership stays
     consolidated on **1 owner**.

## 2. Deterministic CLI Check

Evaluate from flags (no temporary file needed) or from a JSON file matching
[execution-threshold.json](../assets/templates/execution-threshold.json):

```text
python -B <skill>/scripts/execution_gate.py --kind data_or_script --write-files 1
python -B <skill>/scripts/team.py --project . threshold --kind single_surface --write-files 2
python -B <skill>/scripts/team.py --project . threshold --spec .runtime-proof/threshold.json
```

When `.runtime-proof/quickstart.json` includes an optional `"threshold"` object,
`team.py quickstart` validates it before creating any proof or Team directory:
- Rejects `read-only` and `direct` tasks cleanly so ordinary work is never
  forced through subagent ceremony.
- Rejects multi-owner `tasks` lists whenever `split_allowed` is `false` or
  `len(tasks) > max_implementation_owners`.
