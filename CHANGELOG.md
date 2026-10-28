# Changelog

All notable versions are recorded here. Version 1 follows semantic versioning: `MAJOR.MINOR.PATCH`.

## [2.0.1] - 2026-10-28

### Branding and repository move
- Official name: **Oh-My-Harness**; canonical GitHub repo: `abdoabozena7/Oh-My-Harness`.
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
