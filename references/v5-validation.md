# V5 Corporate validation — in progress

V5 is a local development candidate. It has not replaced the released 4.1 package
on GitHub or the installed user-global skill. No corporate-readiness or V5 model
quality improvement has been established yet.

## Baseline

The unchanged 4.1 checkout at `6f35b1b` ran 316 tests, four skipped and zero
failures in 79.323 seconds on Windows/Python3.13.7 before V5 integration.
The baseline log is retained in `.runtime-proof/v5-implementation/baseline-tests.log`.
Its scope is controller compatibility, not proof of generated code quality.

The integrated V5 tree subsequently ran **430 tests, four skipped, zero failures**
in 185.190s. A later focused31-case evaluator run also passed, including strict
JSON type equality and an actual TypeScript compiler check. The earlier failed
integration runs remain retained: one exposed the intentional root-Team requirement
before fixtures were updated; another imported an evaluator while it was being
edited. They are not replaced or presented as passed. Final live-model comparison
and subsequent session-pinning changes require their own validation.

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

## Independent controller review

An independent reviewer reproduced six concrete defects in development. All six
were subsequently rerun and closed on the repaired source, within the tested scope:

| Original defect | Closure checked independently |
| --- | --- |
| A declared output could sit outside verification roots. | Directional containment rejects uncovered outputs/impact paths before sealing. |
| Exact rename/delete scopes failed through the old collector. | Explicit absent_source_paths supports real baseline/candidate runs, with stale/resurrection/midrun-change rejection. |
| A schema4 root could close without native implementation/QA. | Full root requires a matching schema2 Team; missing marker, QA, identity or ownership prevents completion. |
| A timed-out comparison arm could never receive a failure review. | Reviewed failed attempts stay failed in the fixed denominator; a VERIFIED claim cannot turn them into success. |
| Frozen experiments did not bind every declared toolchain artifact. | Changes to executable/setup/dependency identities invalidate that experiment. |
| The package filter removed production validation guides. | Explicit report/corpus exclusions preserve the actual CLI/browser/simulation workflow references. |

Original reproductions and before/after controls remain under
`output/v5-corporate/independent-review/`. This is controller evidence, not a live
model quality improvement. Native-format unit fixtures are explicitly synthetic;
real CLI/SDK parser observations are reported separately from full native acceptance.

## Live development, not final acceptance

Two model accounts have been observed through the actual Copilot runtime:
gpt-6-luna and gpt-6.1-sol. The SDK isolation probe explicitly enables ordinary
configuration discovery, skills, file hooks and host Git operations in every arm.
It observes HarrTest disabled in the plain session and the exact project package
selected in each skill session, while retaining normal non-HarrTest discovery.

The first bounded development task completed through Copilot/Luna and passed its
external functional checks. A new eight-case V5/Luna development run is in flight
under `development-smoke-2`, with its older complete pin and retained evaluator.
It predates later controller repairs and is diagnostic, not final acceptance.
Functional success, workflow compliance and independently reviewed full quality
are separate outcomes; none is silently substituted for another.

A fresh narrow-routing probe observed the requested implementation worker and
a separate native tester, successful external behavior and reviewed applicability
verdicts. It still lacks formal Team receipts and is **invalid for same-model
comparison**: the built-in tester selected gpt-5.6-luna while the session and
implementer used gpt-6-luna. The SDK's session allowedModels setting did not prevent
that built-in default. Actual configured/native model metadata controls this
classification, rather than the dispatch label. Its result and cost are retained
without upgrading it to a valid final attempt. Per-agent pinning must be observed
for every arm before the held comparison begins.

The initial synthetic cases share related language-specific codebases. Final
comparison is therefore an unseen-task/outcome comparison on related families,
not unseen-family generalization. Two acceptance tasks are being expanded into
multiple interacting components before any held model outcomes are observed.
The remaining tasks cover bounded bugs and resource behavior. This mixed corpus
does not establish enterprise-wide reliability or superiority to all harnesses.

Detailed local artifacts will remain under `output/v5-corporate/`; private raw
sessions are not automatically published with the skill.
