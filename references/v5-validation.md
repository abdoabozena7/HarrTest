# V5 Corporate validation — in progress

V5 is a local development candidate. It has not replaced the released 4.1 package
on GitHub or the installed user-global skill. No corporate-readiness or V5 model
quality improvement has been established yet.

## Baseline

The unchanged 4.1 checkout at `6f35b1b` ran 316 tests, four skipped and zero
failures in 79.323 seconds on Windows/Python3.13.7 before V5 integration.
The baseline log is retained in `.runtime-proof/v5-implementation/baseline-tests.log`.
Its scope is controller compatibility, not proof of generated code quality.

## Planned live comparison

Eight development cases and eight separate acceptance cases cover existing
C# service/library, TypeScript CLI/SDK, Python data-processing and C++ library
changes. Acceptance compares no HarrTest, pinned4.1 and pinnedV5 using two fixed
observed Copilot models and two independent repetitions: 96 acceptance attempts.
Models, source packages, toolchains, workload, budgets and independent oracles
must be frozen before generation. All task product changes come from Copilot.
The harness developer supplies general workflow changes and external evaluation,
with no task-specific repairs to generated artifacts.

Keep failures, unavailable checks and interrupted attempts in the results. Cases
used for refinement become development data and cannot retain a held-out label.
Record source/current-config identities, raw tool results, model/subagent usage,
correct completed tasks, false accepts, regressions, security defects, architecture
violations, resource measurements, elapsed time and cost.

## Current environment observations

CopilotCLI1.0.104 and VSCode1.144.1 are installed. The model catalog advertises
`gpt-6-luna` and `gpt-6.1-sol`; account access still requires an actual probe.
Node22.18.0 and Python3.13.7 are available. An MSVC compiler was found through
Visual Studio Build Tools. A portable SDK10.0.404 is available under the ignored
test toolchains directory, verified against Microsoft's published SHA512. The
system dotnet installation and global PATH are unchanged.

Copilot discovers personal skills from `.agents/skills` as well as `.copilot`.
Plain-arm isolation therefore needs observed disabling of HarrTest; a different
COPILOT_HOME alone is insufficient. A real direct-CLI development probe loaded
the skill despite repository-local disabledSkills. That contaminated attempt is
retained and excluded from acceptance. SDK1.0.33 uses the actual authenticated CLI
with explicit per-session configuration; full policy-preserving discovery and
three-arm isolation are being tested before any held comparison.
No personal skill, policy or authentication settings are changed for comparison.

Detailed local artifacts will remain under `output/v5-corporate/`; private raw
sessions are not automatically published with the skill.
