# Changelog

## [2.3.0] - 2026-10-30

- Add independent, fail-closed `scripts/goal_guard.py` for typed outcomes, same-run ordered journey steps, source/target/mode identity and artifact SHA-256 integrity.
- Reject false PASS from contradictory/missing states, stale or tampered artifacts and mixed or incomplete attempts; allow only a complete valid fresh run to supersede a failure.
- Add browser `capture_text`, `expect_text_same`, `expect_text_changed`, and bounded `wait_ms` to detect Pause->Resume style defects.
- Retain full original root requirement IDs while assigning children only scoped obligations; guard is supplemental to sealed root and live acceptance.
- Add negative regressions and browser demonstration. No claim of generalized live model reliability.


## [2.2.0] - 2026-10-30

- Distinguish official minimum reservation, preferred execution length, fixed
  cleanup and scientifically meaningful minimum before asking for additional resources.
- Add read-only deterministic `experiment_budget.py` for bounded planning;
  never infer consent or live admission from successful arithmetic.
- Add conjunctive `strict_gates.py` that fails on any required breached,
  missing, invalid or nonfinite metric rather than accepting good percentiles.
- Add 20 locally passing regression tests for both helpers, including a
  single late outlier after passing p95 and p99.
- Add rules for collecting live visual evidence while product is running and
  preserving exact residual outlier identity before retrying expensive runs.
- Keep original root gates, permission requirements and protected budgets.

## [2.1.0] - 2026-10-29

### Bounded autonomy and failure prevention
- Generalize recovery for quota, authorization, simulator, browser and compute blockers.
- Separate user consent, source-of-truth acceptance, host gates, protected budgets and
  resource arithmetic, without assuming Autopilot or large credits imply permission.
- Add read-only `scripts/admission.py` with 12 executed boundary/negative tests.
- A successful precheck is never native permission: `PRECHECK_OK_NOT_AUTHORIZED`.
- Add failure-to-prevention template and next-unverified-gate restart rules.
- Preserve existing root/child gates and historical evidence; no automatic budget changes.

All notable versions are recorded here. Version 1 follows semantic versioning: `MAJOR.MINOR.PATCH`.

## [2.0.3] - 2026-10-28

### Rebrand: HarrTest
- Canonical public repository: `abdoabozena7/HarrTest`.
- Portable skill ID, install directories and hooks: `harrtest`.
- Updated visual banner, agent metadata, README, installation commands and current documentation.
- Added migration protection for the prior `harrnist` hooks/instructions, preserving earlier `prove-it` and `oh-my-harness` guards.
- Preserved proof schema, root-goal validation and tests without falsely asserting cross-agent execution.

## [2.0.2] - 2026-10-28

### Historical rename: HARRNIST
- Previous repository name: `abdoabozena7/HARRNIST`, skill ID `harrnist`, visible brand `HARRNIST`.
- Rename README, visual banner, skill frontmatter, agent metadata, installer, hooks, examples, and current documentation.
- Refuse silent double installation if `prove-it` or `oh-my-harness` managed instruction blocks or hooks remain; leave old user files and evidence untouched.
- Keep runtime receipt schema, original-goal gate, and evidence validation unchanged.
- Validate local test suite and package the skill.

## [2.0.1] - 2026-10-28

### Branding and repository move
- Historical name at that release: **Oh-My-Harness**, repository `abdoabozena7/Oh-My-Harness`.
- Skill ID, installation directories, agent metadata, README, banner, examples, hook file names, CLI installer, and documentation use the new brand.
- Existing installations must migrate separately: review and remove the previous skill/hook only after confirming the new installation works. No existing runtime evidence format or task schema is renamed.

## [2.0.0] - 2026-10-28

### Root-goal integrity
- Sealed original request and provenance-linked root requirements.
- New `scripts/root_gate.py` separates whole-goal acceptance from child evidence.
- `proof.py` now returns `completion_scope: CHILD_TASK_ONLY` and `root_goal_achieved: false`.
- Missing, stale, wrong-mode, pre-seal or failed child evidence cannot satisfy root coverage.
- Requires separately verified final integration and maintains unresolved blockers.
- Does not grant new simulator permissions or project budgets.

### Validation
- Local development suite: 50 tests run, 49 passed, one browser e2e skipped.
- Native CARLA and installed Copilot hook integrations were not retested for v2.

## [1.0.0] - 2026-10-28

### First public release
- Reusable agent skill for observable, evidence-backed completion of coding tasks.
- Dependency-aware plan, explicit TODO states, safe real subagent delegation and final integration checks.
- Browser, simulation/CARLA, CLI/agent pipeline and API validation playbooks.
- Evidence receipts with source fingerprints, command results, artifacts and conservative stale-evidence invalidation.
- Optional Copilot and Claude stop adapters; optional browser driver and local Python installer.
- Added Mini Hivo-inspired requirement provenance, impact challenge, context preflight, adaptive decomposition, failure classification and verified-memory rules.
- Visual README, compatibility matrix, installation and security boundaries.

### Known limitations
- Skill instructions do not grant host/browser/GPU access or guarantee correctness.
- Host-specific hook behavior must be exercised on the target installation.
- The included quality gate checks declared evidence and task coverage; a self-authored oracle still requires independent review.
- No universal background runner or subagent scheduler is bundled.

### Release checklist
- [x] Validate SKILL.md structure.
- [x] Run bundled standard-library unit tests.
- [x] Build distributable skill.zip.
- [ ] Confirm GitHub release/tag `v1.0.0` if release creation is available.
- [ ] Real-world acceptance on a target agent, headed browser and native simulator.
