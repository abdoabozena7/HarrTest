# V5 Corporate validation — in progress

V5 is a local development candidate. It has not replaced the released 4.1 package
on GitHub or the installed user-global skill. No corporate-readiness or V5 model
quality improvement has been established yet.

## Baseline

The unchanged 4.1 checkout at `6f35b1b` ran 316 tests, four skipped and zero
failures in 79.323 seconds on Windows/Python3.13.7 before V5 integration.
The baseline log is retained in `.runtime-proof/v5-implementation/baseline-tests.log`.
Its scope is controller compatibility, not proof of generated code quality.

The integrated V5 tree at `39d1bb1` ran **473 tests, four skipped, zero failures**
in 245.682s. Its log is in `.runtime-proof/v5-implementation/integrated-tests-r6.log`.
The earlier failed integration runs remain retained. One exposed the root-Team requirement
before fixtures were updated; another imported an evaluator while it was being
edited. They are not replaced or presented as passed. Final live-model comparison
and subsequent session-pinning changes require their own validation.

## Live comparison

Eight development cases and eight separate acceptance cases cover existing
C# service/library, TypeScript CLI/SDK, Python data-processing and C++ library
changes. Acceptance compares no HarrTest, pinned4.1 and pinnedV5 using two fixed
observed Copilot models and two independent repetitions: 96 acceptance attempts.
Models, source packages, toolchains, workload, budgets and independent oracles
must be frozen before generation. All task product changes come from Copilot.
The harness developer supplies general workflow changes and external evaluation,
with no task-specific repairs to generated artifacts.

The frozen acceptance run began on 2026-11-14 using GPT-6 Luna and GPT-6.1 Sol
at low reasoning effort, with the same 2,400-second and 120-AI-credit caps for
each attempt. Independent assessments are recorded as attempts complete.
The local protocol, journal and partial summary are under `output/v5-corporate/acceptance-v5-1/`.

The first matched block used Luna on the Python batch-atomicity request. All
three artifacts passed the frozen executable suite. Independent reviewers
confirmed both control runs and reproduced a V5 case in which a malformed
optional flag led to writes before rejection. The V5 response claimed that
invalid input left state unchanged, so the archived assessor recorded one false
accept. Its separate Team verification failure was disclosed in the response.

| Arm | Independent complete quality | Generation seconds | Copilot AI credits |
| --- | --- | ---: | ---: |
| No HarrTest | PASS | 251.580 | 0.601154 |
| 4.1 | PASS | 344.937 | 0.6370595 |
| V5 | FAIL | 1625.464 | 6.038285 |

The V5 usage receipt reconciled with the parent and its child actors. This block
covers one case, one model and one repetition. The original comparison retains
the measured results. Any further iteration that uses this finding must replace
the consumed case in the next held corpus before measuring improvement.

The same frozen protocol retained a credit-validation attempt with seven passing
external checks and a passing native Team replay. Both native workers ran at
high effort, whereas the protocol required low for every actor. The attempt
is INVALID in the comparison. A separate disposable Copilot SDK probe confirmed
that a session hook can pin an explicit child override to the declared effort.
The next evaluator uses that transport rule in all arms and checks actual
actor effort after execution. [GitHub SDK hook reference](https://docs.github.com/en/copilot/how-tos/copilot-sdk/hooks/pre-tool-use)

The next candidate adds checks for the full affected input boundary, compares
state before and after rejection, and asks reviewers to reproduce apparent
inherited faults on the baseline. The consumed atomicity case is a development
control with probes for malformed, false and true control values. The credit
case that informed the transport change also moved to development. Two distinct
existing-code cases replace them in the held set. Two more replacements cover
independent implementation scopes after the partitioning observation below.
The schedule still has eight development cases and 96 held slots, with 32 per
arm. The replacement cases await live results.
At `ae28793`, the next candidate ran 477 tests in 259.549s with four skipped and
zero failures. Independent review confirmed the new positive and adverse
controls, the schedule, and the exclusion of the evaluator and corpus from the
generation package.

A Copilot development replay of the consumed case took 1973.437s and 5.443232
credits at Luna/low. The independent reviewer replayed the two partial-write
failures on the frozen baseline. Both rejected without changing stored bytes
on the final Copilot source, and a valid interruption still committed its
checkpoint and retried correctly. The post-repair independent Team receipt was
stale because the synchronous QA worker could not resume. A new development
trial is exercising the reusable native-worker guidance.

The reusable-worker trial passed 9/9 external checks at Luna/low and used an
actual background worker follow-up. This trial exposed two workflow issues.
The plan initially listed an editable test as immutable validation context.
That made the expected edit invalidate the plan. Separately, the local evaluator's
shell filter denied a QA evidence write because its narrative contained the word
`credential`. The next evaluator's permission replay permits the two archived
benign requests and still rejects protected paths and credential-management
commands. The original trial lacks the review receipt and remains incomplete.

At the first matrix snapshot, seven terminal V5 attempts covered two
multi-component existing-code cases. Copilot declared one implementation scope
for both components in all seven. The retained schema2 plans and actual actor
observations support this count. The two cases are now development evidence for
scope planning. Later held comparisons must use distinct replacement cases.
The replacement cases use distinct existing components with stable shared
interfaces. Each component is checked independently, and the composed SDK and
real CLI are checked after integration. The old-component tests replay on the
baseline and candidate.

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
external functional checks. The eight-case V5/Luna run under `development-smoke-2`
used an earlier fixed pin and its retained evaluator. It predates later repairs.
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

The subsequent actual runtime probe and development-smoke4 confirmed required
per-agent session model settings: implementation and independent tester both
configured and invoked gpt-6-luna/low. That fresh C# diagnostic passed all four
external behavioral checks in 133.721s of generation and recorded 1.5523585 AI
credits. It has no formal Team receipts; valid model attribution and artifact
success do not upgrade its durable-workflow status. A later minimal schema2
template and command sequence are being forward-tested as another pinned trial.

The original eight-case development-smoke2 completed, with seven external
functional passes and one failure affected by the disclosed tenant-schema
ambiguity. This is neither a before/after comparison nor full-quality acceptance;
all eight came from the earlier diagnostic V5 pin. Their raw costs and failed
checks remain retained without rescoring under the newer visible contracts.
Independent review identified two defects the earlier automated checks missed.
One redaction implementation also removed valid non-sensitive fields. One C++
total used an intermediate signed sum that could overflow for representable final
totals. The latter finding comes from source analysis. The skill now asks reviewers
to check legitimate near matches and intermediate contract invariants.

Development-smoke5 stopped before generation when the native session header
arrived after the SDK create call. The next runner waits up to 15 seconds for the
actual header and checks the requested ID and workspace. Development-smoke6
confirmed the session binding and all three actual actor contexts at gpt-6-luna/low.
It completed in 232.694s and passed all four external checks. Copilot recorded
implementation, integration, test execution and QA review receipts. The plan set
host.kind to unverified and the native labels differed from the sealed labels.
Native verification reported UNVERIFIED. The frozen runner also marked the
attempt INVALID when Python generated five import caches. The next runner
suppresses imports' bytecode writes and distinguishes ordinary caches from
mutations of source, settings or policies. The historical classification remains.

Development-smoke7 completed in 197.359s, consuming 2.1149445 AI credits. All
three actors used gpt-6-luna/low, the four external checks passed, and independent
replay authenticated implementation provenance. Full Team verification failed
because the reviewer was unable to write the required private receipt.

Development-smoke8 selected a reviewer that could write private evidence. All
three actors used gpt-6-luna/low. The attempt completed in 348.622s, consuming
3.8278575 AI credits, with four passing external checks. The QA worker ran the
targeted checks; the coordinator replayed the existing test. In a resumed QA
turn the worker inspected that replay and wrote a review receipt. Native Team
verification failed because the adapter could not read the resumed worker turn.
Independent replay with the updated adapter recovered the resumed turn and
correctly rejected the coordinator's check as evidence of independent execution.

Development-smoke9 timed out at 630.21s. It recorded owner and integration
receipts and passed four external checks. Its QA run failed because the worker's
shell resolved a different .NET installation, and no QA review receipt was
recorded. The next pinned fixture keeps the existing check assertions and runs
them with the declared .NET executable and a workspace-local scratch directory.
This fixture setup applies equally to each arm. The evaluator also replays the
original checker on source-qualified baseline and candidate copies separately.

Development-smoke10 used that pinned checker. QA independently ran the existing
check and recorded exit 0 on the integrated source. Copilot's SDK did not reach
idle within the 900s session limit and the trial ended without an independent
review receipt. All five external checks, including the old checker replay,
passed. The model run remains a failure in the development record.

The schema2 log adapter independently passed a long-session compatibility probe
and replay controls for real model/effort changes. The old 4.1-pinned production
audit reported that its native log exceeded its size limit. Independently tested
controls also enforce the frozen evaluation order. Each acceptance block rotates
three arms within a case, model and repetition. Evaluations require the matching
terminal generation record. Reports retain invalid, timed-out and missing trials.

The synthetic cases share related language-specific codebases. The held corpus
contains two multi-component changes and six bounded changes, including a measured
resource case. Public input and output contracts are supplied to every arm. This
measures the defined tasks on those families. Broader reliability needs additional
representative evidence.

Detailed local artifacts will remain under `output/v5-corporate/`; private raw
sessions are not automatically published with the skill.
