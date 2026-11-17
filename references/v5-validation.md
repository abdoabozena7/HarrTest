# V5 Corporate validation — in progress

V5 is a local development candidate. The released package and user-global skill
are at 4.1.0. The frozen results below measure quality differences for the
evaluated changes and environments.

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
The first local protocol, journal and final summary are under `output/v5-corporate/acceptance-v5-1/`.

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

The first matrix retained all 96 executable results. The three arms scored
29/32, 31/32 and 30/32 on executable functionality. Median generation times were
61.859s, 81.208s and 653.919s. Their recorded credit subtotals were 122.380940,
234.714506 and 1504.6956735 across 31 available receipts per arm. Independent
reviews identified false accepts and protocol violations. The first pin cannot
qualify under the sealed release rule.
All 96 independent assessments recorded 11/32, 12/32 and 13/32 complete-quality
passes, with 19, 19 and 15 false accepts in arm order. Reviewed security failures
were 2, 4 and 6. The executable results alone would overstate the quality of all
three arms. The first local archive retains the final assessment summary.

### Second frozen comparison

The second comparison froze the V5 package at `a2ae3e8`, used the same two
models, effort, budgets and fixed denominator, and replaced four development-
consumed cases before execution. All 96 outcomes and independent assessments
are present. Four generation outcomes failed and remain in the denominator.

| Measure | No HarrTest | 4.1 | V5 |
| --- | ---: | ---: | ---: |
| Executable functionality | 29/32 | 30/32 | 30/32 |
| Independently complete artifact quality | 12/32 | 12/32 | 18/32 |
| False accepts | 20 | 19 | 4 |
| Regressions | 5 | 2 | 5 |
| Security layer failures | 4 | 2 | 3 |
| Architecture or protected-scope violations | 15 | 16 | 6 |
| Generation median (seconds) | 72.704 | 100.570 | 740.592 |
| Observed Copilot AI credits | 135.254950 | 246.9606825 | 1761.2535515 |
| Complete usage receipts | 32/32 | 31/32 | 30/32 |

Six of the 18 V5 artifacts passed complete quality while their own final
responses reported incomplete acceptance. Of 16 V5 responses claiming full
completion, 12 passed independent artifact review. The four false accepts cover
legacy input acceptance or rejection, a protected file boundary and an original
test oracle. Independent adjudication of both disputed stock review blocks
retained every verdict. The C++ performance workload had three measured passes
in plain and four in each skill arm. One plain attempt had no usable measurement.
The benchmark records 28 reconciled V5 parent/child credit totals.

The fixed release threshold requires zero V5 false accepts, so this package is
unqualified. The latest optional guard was developed on consumed cases after
this matrix was frozen. The matrix cannot establish its impact. The second
matrix's final summary is `output/v5-corporate/acceptance-v5-5/final-summary.json`,
SHA-256 `af67a653e4a87eea48d3d3aacdc96d7e862423bd091bcf4605c08dd8dea0c68a`.
The next comparison moves the three cases that informed corrective rules into
development and freezes replacement cases before Copilot runs them.

### Third frozen comparison

The third comparison used `84ea616` with three replacement held cases and
explicit local V5 guard enrollment on the two predeclared multi-component
cases. The driver and independent reviewers retained all 96 slots. Generation
completed in 13 attempts, including four matched blocks with all arms completed.
The other 83 failed in Copilot's model discovery or response transport. Forty
failed before a native session started. Forty-three failed during model
responses. The diagnostics include DNS, authentication, connection resets,
closed streams and timeouts. They leave the underlying cause undetermined.

Fixed-denominator complete artifact quality was 2/32, 3/32 and 3/32, with 2,
2 and 1 false accepts in arm order. The availability collapse leaves this run
unqualified for release and unsuitable for measuring a comparative gain. The
third summary is `output/v5-corporate/acceptance-v5-6/final-summary.json`,
SHA-256 `f777a3c8c21d6d6ab86b67437ecab3d13e8acf766b3ca57b68cb07000c22b9d`.
The archive includes an independent runtime audit with counts and a protocol
digest. A future experiment keeps these outcomes and uses a new frozen directory.

### Workflow development evidence

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
At `881b2e6`, the integrated suite ran 494 tests in 351.124s with four skipped
and zero failures. It includes the reviewed Team and Corporate seal controls.
At `5492ae3`, the suite ran 495 tests in 331.357s with four skipped and zero
failures. Current reviewed-plan commands passed both actual pinned wrapper and
wrong-script, wrong-team, and late-actor controls.

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

The first development trial of reviewed decomposition passed all nine external
checks. The independent plan reviewer rejected one implementation owner and
Copilot corrected the scope. The reviewer then required overlap evidence before
dispatch, so the revised plan used two distinct owners serially. The final native
gate rejected reuse of an actor that started before the corrected Team's seal.
The next workflow records planned concurrency from available tool capability,
checks observed overlap afterward, and uses a fresh reviewer for a new sealed
plan. A separate native Luna/low capability probe observed 9.672s of overlapping
work between two background workers.

The corrected workflow then passed read-only native verification of planning
and production on two development projects. In C#, the Rules and CLI owners
overlapped by 91.871s. In TypeScript, the SDK and CLI owners overlapped by
96.868s after a fresh reviewer rejected the initial single-owner plan. Both
probes ran all implementation actors on Luna/low. These production-only replay
results establish actual partitioning and overlap. Final QA and Corporate root
status are tracked separately. The next frozen 96-attempt comparison began
after the C# overlap was observed.

The final pinned Team verification passed on both development projects, including
independent QA. TypeScript passed 9/9 frozen executable checks in 2241.647s at
7.1119710 AI credits. C# passed 13/13 in 2190.709s at 6.9551730 AI credits, with
the same owner and QA actor resuming after repair. Both used Luna/low. Neither
produced a complete Corporate root contract and seal. Independent review found
that the TypeScript CLI accepted malformed UTF-8 bytes, and the C# repair also
changed an unrelated inherited tenant lookup. These are retained development
limitations, including where the narrower native Team gate passed.

The next implementation added a draft scaffold from real baseline receipts and
checks the exact Corporate root seal at first implementation admission when the
Team plan opts in. A local schema-4 CLI control refused early dispatch, then
admitted it on the original baseline and bound the handoff to the seal. The
first live trial invoked the pinned project skill and passed the executable
checks. Its coordinator nevertheless edited the project directly and created
no Team or root. The admission check was never reached in that trial. The result
documents a workflow bypass, rather than a Team or Corporate pass.

Two further trials on the same consumed TypeScript development task exercised
the Copilot CLI 1.0.104 runtime with Luna/low. The second text-only trial used
one native implementer for both components and a separate QA worker. The pinned
Team replay passed, as did all 9 external checks in 267.132s at 3.2532295 AI
credits. The run registered no Corporate seal.

The first explicitly enrolled trial passed 9/9 external checks in 480.585s at
6.0701035 AI credits. Its one implementation worker made four product patches
from a child session with a different UUID. The parent editor guard did not
cover those calls. The next pin checked the parent `task` call before a child
could start. Copilot reported two review-dispatch denials and one product-edit
denial. No child started and product source stayed byte-identical. That run
passed the 5 preservation/control checks out of 9, took 200.384s and consumed
1.8306245 AI credits. It finished without implementation or root acceptance.

Read-only replay showed the later review attempt copied the exact registered
packet. The saved original request contained one extra trailing newline, so
Team binding rejected it before review. Guide and hook revisions preserve exact
identity, expose the unmet precondition and reuse the authoritative snapshot.
The mechanism is opt-in for the enrolled checkout and parent session. These
observations cover native editor and `task` calls; shell and MCP continue under
host permissions. The two terminal runs and projected evidence are retained in
`development-corporate-guard-{1,2}/` and
`development-review/corporate-guard-native-routing.json` under the local output
directory. They are development evidence and excluded from the held matrix.

In the third enrolled trial, Luna corrected the request binding, completed a
native scope review, sealed a schema-4 root, and received owner admission before
the first product patch. It passed 9/9 external checks in 1721.567s at 18.3884765
AI credits. It still used one implementation owner for independently testable
components and amended an existing test. Strict TypeScript checking failed on
an unassigned variable and the frozen artifact guard rejected the result. The
QA worker recorded inherited failures and unmeasured performance; the root
remained `ROOT_GOAL_UNVERIFIED`. The coverage review required a separate native
task, which the enrolled parent could not start before admission in that pin.
The next revision provides exact scope and coverage review packets and asks the
scope reviewer to check the smallest viable split against actual interfaces.

In the fourth enrolled development trial, Luna's first native plan reviewer
rejected a single implementation owner. The model registered two independent
owners and a fresh plan review passed. Six successive request coverage reviews
did not approve the draft within the generation budget. No implementation
worker started, no product changes landed and 5/9 external checks passed.

The fifth trial used a consumed C# project. Luna sealed the root and admitted
implementation before two owners started 2ms apart and overlapped 61.367s.
Separate QA and final evidence reviewers ran. All 8 external checks and the
artifact guard passed in 2286.388s at 43.1642975 credits. Root verification
reported two issues: native nested reviewer tasks lacked origin handling, and
baseline/candidate replay used identical executed commands and assertions with
different normal check roles. The nested parser was tested on the full
20,986,008-byte persisted native journal. It retained two nested helpers and
all four private edits. The replay validator accepts matching normal check
roles without waiving differences in command, mode, assertions or exit codes.
The original development result remains `ROOT_GOAL_UNVERIFIED`.

The sixth trial loaded the nested-task and preservation fixes. It reached
native plan and coverage review, then ended on a model-response DNS error.
The Corporate seal was absent and no implementation worker started. The
retained baseline passed 3/8 external checks. This outcome cannot measure the
effect of the two fixes on completed Copilot work.

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
