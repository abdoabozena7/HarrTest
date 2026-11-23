# HarrTest 5 validation

V5 is available as an opt-in GitHub preview, not a qualified stable release.
Publishing it does not update existing user installations. The frozen results
below measure quality differences for the evaluated changes and environments.

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

The integrated candidate at `74f6283` ran 530 tests in 574.909s with four
skipped and zero failures. The suite includes the shared-baseline check and
unchanged legacy root contract controls. The log is
`output/v5-corporate/next-integrated-tests-r14.log` in the candidate worktree.

After the Copilot follow-up fix and held-case rotation, the local suite ran
532 tests in 524.685s with four skipped and zero failures, using the pinned
local toolchains. The log is `output/v5-corporate/followup-delivery-rotated-full-suite.log`
in the candidate worktree. This validates controller behavior and fixture
controls, not live release qualification.

### Existing-code review loop (unreleased)

On the 5.1.0 checkout at `70c343e`, a disposable CLI change passed the managed
Team structural gate without any explicit quality-layer verdicts. A failed
QA review could also be replaced by a pass referring to the same integrated
check, without rerunning it. Native provenance was not evaluated in this
baseline reproduction.

The candidate adds `integration.quality_review: review-loop-v1` for new
managed existing-code Team plans. The regression cases run actual CLI
processes: no verdict or supporting evidence cannot pass; config changes
invalidate the old check; a source-mutating check stays unusable after
restoration; multiple failed rounds cannot lose findings; and a no-op or
misrouted code repair cannot close a confirmed defect. They also prove that
an evidence-only finding can close on a fresh run without changing code,
and exercise both an original component owner and coordinator-owned glue.

On Windows, 227 tests passed across Mission, Team, Team v2, Corporate, root
gate and Copilot guard. This validates the controller and compatibility with
unmarked plans; it does not qualify this package, measure generated-code
security or performance on a production system, or establish live quality
uplift. A matched comparison needs fresh held-out cases, the same model,
effort and budgets, and independent assessment of both arms.

### Streamlined daily admission and GPT-6.2 Sol upstream trials (unreleased)

In initial `gpt-6.2-sol` (`medium`) trials on `pytest` 9.0.1 and `sqlfluff`
3.5.0 (`output/delivery-sol62`), manual authoring across `proof.py`,
`mission.py` and `team.py` consumed the pre-edit budget before product edits.
Iterative harness tuning introduced `team.py quickstart`, `handoff --note`,
`qa-submit`, `repair --refresh-note`, hashed mission-context offloading, a
compact operational `SKILL.md`, a 4-step 6-angle adversarial `qa_packet`, and
native receipt recognition for PowerShell `& $py` / `Join-Path` invocations,
without relaxing any preservation, review-loop or native provenance gate.

Across R1–R4 on five real upstream Python repositories (`pytest` 37k LoC,
`sqlfluff` 125k LoC, `pallets/jinja` 14k LoC, `pallets/click` 11k LoC, and
`pygments/pygments` 200k+ LoC), the tuned candidate completed implementation,
executed independent adversarial QA, caught and repaired real defects missed
by the matched `gpt-6.2-sol` (`medium`) plain control, and passed full
structural + native `copilot-session-events-v1` `team.py verify` (`passed:
true`) on `pluggy`, `click` (R3), and `pygments` (R4, verified directly inside
the live session). In the cold held-out `pluggy` and `pygments` pairs:

- **`pytest-dev/pluggy` 1.5.0:** Plain failed duplicate-namespace empty
  `sensitive_args` merging and crashed with `ValueError` on >4,300-digit integer
  arguments under `include_args=True`. HarrTest QA caught both defects in Round 1,
  routed repair to `impl`, re-verified 42 authored + 85 upstream tests, and
  passed native `team.py verify` (`0.9899x` baseline 25k-call median).
- **`pygments/pygments` 2.19.1:** Plain broke `-O redact_token_types=...,full`
  and `-O redact_token_types=...,flush` (`ValueError: Unknown token type:
  'flush'` and swallowed boolean flags). HarrTest QA caught that exact CLI `-O`
  preservation defect in Round 1, routed repair to `impl`, passed 5,221 upstream
  + 23 authored tests (`0.9994x` baseline median, 2,055 B peak memory across
  50k streamed tokens), and passed `team.py verify` inside the live session.

Raw traces, patches and evaluator outputs are retained under
`output/tuning-sol62-r1/`, `output/heldout-sol62/`, `output/heldout-r3/` and
`output/heldout-r4/`. These upstream trials establish end-to-end daily
execution and multi-angle QA repair uplift on the tested tasks; formal 96-slot
multi-language release qualification remains separate.

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

### Fourth frozen comparison

The fourth comparison pinned V5 at `1f99aea`. All 96 outcomes and independent
assessments were retained and checked against the frozen evaluator. The five
failed and one timed-out generation remain in the denominator.

| Measure | No HarrTest | 4.1 | V5 |
| --- | ---: | ---: | ---: |
| Executable functionality | 31/32 | 29/32 | 27/32 |
| Independently complete artifact quality | 22/32 | 17/32 | 19/32 |
| False accepts | 9 | 14 | 5 |

This package is not qualified: V5 had five false accepts and did not exceed
the plain control on complete artifact quality. The frozen summary is
`output/v5-corporate/acceptance-v5-7-final-summary.json` in the main worktree,
SHA-256 `01997e97773ed3bf631339702c44e5ed606c433f374c208c0ded4347aacdff5c`.
The original protocol and attempt results are unchanged. This comparison
does not validate the later candidate package.

In block 4, the Luna V5 triage artifact passed all seven external checks and
independent artifact review. Its formal root did not pass. A completed QA
follow-up was followed by a native idle status read with no `wait` argument.
The pinned verifier ignored that otherwise conclusive observation, left the
old follow-up pending, and rejected the next genuine delivery against the
old message. The candidate recognizes post-turn non-waiting reads with the
same actor, idle, an empty queue, and the exact completed-turn count. It
still requires the actual parent message, original dispatch and closed
turns. Read-only replay parses both QA follow-ups, without waiving the
coordinator's out-of-scope test edit or the independent D04 `UNVERIFIED`
finding for missing task-level proof bindings.

The triage case informed the repair and is now development-only.
`ts-pick-list` replaces it in the next held matrix. Its separate typed
consumer checks line merging, package arithmetic and non-mutation; the
unchanged CLI tests the composition and the original checker is replayed.
Fixture controls show that either isolated repair leaves the other
defect detectable. These are evaluator controls, not live held results.

### Development after the preview

The fourth comparison recorded three V5 false accepts with protected file
changes and two with unverified behavior at an evaluation-order boundary.
The next pin states the exact protected files in the exposed fixture contract
for every arm, derived from the same policy the evaluator checks. V5 Team
packets make the approved write scope and read-only inputs visible before
expensive QA, and ask reviewers to replay changed no-work paths. The original
results and qualification thresholds are unchanged.

A bounded development replay of the consumed C# planner, Python retry, and
C++ lookup passed 12/12, 4/4, and 8/8 independent executable checks with no
protected file changes. The C++ candidate's paired median was 0.267 of the
baseline (maximum 0.70). The two Sol runs disclosed incomplete native QA.
In Python, QA could not replay the pinned baseline because Git had normalized
CRLF to LF. The evaluator now verifies the committed Git blobs match the
original fixture bytes. A new Sol/low replay then passed 4/4 external checks,
and its native QA commands exited 0; a final native QA receipt was still absent.
The full updated suite ran 538 tests, four skipped and no failures.

The planner, retry, and lookup cases now belong to development. The next held
matrix retains its size, language balance and separate recovery and scaling
requirements. None of these development observations count toward release.

### Fifth frozen comparison

`acceptance-v5-9` pinned the V5 package at `f828f184`. It retained 78 of 96
declared slots with independent assessments, stopping after the strict
quality condition became impossible. Both controls had 26 complete-quality
passes; V5 had 18 and no recorded false accepts among the reviewed slots.
With six unrun slots per arm, even if all six remaining V5 slots passed,
V5 could reach only 24 of 32. The six unrun slots are still in each
denominator, not excluded or treated as observed failures. This pin cannot
qualify and was not promoted. The retained `unqualified-summary.json` has
SHA-256 `1e0d4771c98921ac2fe4fd068ae7bf8cbe2ac42680fedc8700b398f84c7a7f34`.

The retained Copilot records distinguished request-binding and admission
failures, transport interruptions, and a valid steering message during an
already-resumed QA turn. The original slot outcomes are unchanged. A new
Luna/low diagnostic independently observed the idle follow-up and steering
delivery on the same actor. The repaired adapter closed the original resume;
the previous adapter rejected it. The steering replay does not substitute
for missing QA or root assurance. See the retained
`development-copilot-steering-probe/parser-validation.json` for the live trace
digest and parser results.

The third guarded development replay reached plan and coverage review but
recreated the enrolled request with different line endings. Its result stayed
`INVALID`; the SDK did not reach idle and the original source passed 5/10 checks.
The next pin preserves request bytes at initialization, allows an exact retry
without changing an existing draft, and requires the enrolled Team to bind to
that request from registration. The fourth guarded replay preserved the request
and passed independent plan review without configuration drift. Independent
coverage review still found missing assertions for `cue_count` and
non-mutation. The SDK reached its idle deadline before admission or product
edits; the baseline passed 5/10 checks. The request repair therefore does not
establish end-to-end guarded acceptance. Both attempts remain in the
`development-v5-release-boundaries-r3` and `development-v5-release-boundaries-r4`
archives.

The fourth development pin also passed the full compatibility suite:
542 tests ran with four skips and no failures. This establishes controller
compatibility, not qualification of the Copilot output or of the release.

### Guarded C# development after plan rejection

The consumed studio-cue case exposed a pre-seal stall: a reviewer rejected
one owner for two independently callable components, but the coordinator
could not replace the rejected plan under the enrolled goal. The same-goal
revision now retains the original request, baseline and rejected review,
and requires a fresh native approval. R7 registered the corrected plan but
changed wording in the copied dispatch, so the exact-message gate denied it.
The short revision-bound dispatch let a new native reviewer retrieve the
complete brief and approve the split. R6 and R7 remained unchanged at 5/10
frozen executable checks. The first continuation also stopped before
implementation; those outcomes are retained separately.

The next continuation used the read-only draft preflight to catch incomplete
request mappings and source bindings before review. The eventual independent
coverage verdict was `covered`, with no unresolved findings, but that phase
timed out before sealing. A separately bounded Luna/low continuation of the
same reviewed draft sealed and admitted both native owners. They changed only
`CueOrder.cs` and `CueCoverage.cs`, overlapped, and passed native Team QA.
The frozen evaluator passed **10/10** checks on the unchanged evaluated bytes.

The Corporate root still returned `ROOT_GOAL_UNVERIFIED`. The sealed child
source-scope check raised a `NameError`, the report check embedded an incorrect
baseline hash, and the original CLI/build receipts had not been refreshed on
current source. No Corporate report was accepted. None of those failures
were waived on the strength of the executable or Team result. The terminal
continuation is in `output/v5-corporate/cue-build/`; its independent root replay
has SHA-256 `69e4db578fb23f0462c601d9c14ece7052145dd6135d4f7071d0b2efa5e033dc`.

The local candidate compatibility suite ran 551 tests, with four skips and
no failures. This assisted development sequence is not a new held matrix.
The original stable condition remains: all 96 declared slots independently
reviewed on the exact candidate, zero V5 false accepts, and more complete-quality
passes than either control.

### Beacon Courier visual development

The same small 3D driving task was given to GitHub Copilot GPT-6 Luna at
**low** reasoning effort, with and without HarrTest. The task makes the
quality of independent deliverables visible: the rover, road, environment,
gate markings, drive state and HUD must work together on the real screen.
The benchmark operator changed the harness, not the game source.

Both arms received the same local Three.js and original product prompt.
R2 and later share the expanded finishing brief. HarrTest was disabled
in the plain arm; other normal skill discovery was not disabled. The staged
HarrTest arm received an operator-supplied Team draft, and R3 onward are
adaptive treatment replays, not new matched control runs.

| Retained attempt | Plain Copilot | HarrTest 5 candidate |
| --- | --- | --- |
| R1, cold | App present; SDK idle timeout; no gate reached in 25 s | Timed out in intent review, no app |
| R2, shared brief | App delivered; all three gates and restart observed | Timed out after intent review and Team registration, no app |
| R3 | Not rerun | Reviewer rejected an unobservable blue-hour criterion |
| R4 | Not rerun | Reviewer rejected grouping gate visuals with scenery |
| R5 | Not rerun | Reviewer rejected grouping scenery with the route and asked for the HUD scope rationale |
| R6 | Not rerun | Reviewer rejected unsupported six-wide dispatch and unclear integration ownership |
| R7 | Not rerun | Reviewer accepted two-wide capacity and coordinator ownership, then rejected missing separate coastal scope |
| R8 | Not rerun | Plan approved; six of seven owner handoffs completed before the deadline, no public entrypoint |
| R8 continuation | Not rerun | Same native session finished seven handoffs and assembly. Native QA used hardware WebGL and recorded FAIL; separate software-WebGL observation passed its measured journey. |
| R8 QA follow-up | Not rerun | Same parent reconnected but the host could not resume the original QA worker. No new QA verdict or product change. |
| R8 QA recovery | Not rerun | One fresh native QA worker verified SwiftShader and completed both runs. Full Team replay passed on unchanged game source. |

R3–R7 ended SDK turns, not app deliveries. R7 also attempted to submit a review
over the existing 8,000-character limit before successfully recording its
rejection. The next pin states that limit in the packet and reports actual
and maximum lengths on rejection; the receipt and admission requirements did
not change. A separate owner needs a concrete reason beyond what a focused check
can establish. The coast revision distinguishes near built structures from
independently authored water and shoreline; the wheel fit remains a focused
quality check, not another write scope.

R8 records seven separately checkable scopes, with up to two active
implementation owners. The accepted plan left wheel geometry and animation
with the rover owner and grouped HUD markup and CSS under one owner. Native
rover/route, depot/coast, and gates/drive work overlapped. The first R8 phase
timed out after **2,430.250 s** including shutdown handling. No coordinator
assembly had been delivered. The same parent session resumed and delivered
the HUD and current assembly in a separate **2,391.948 s** generation. An
initial continuation setup failed before launching Copilot because the cold
fixture expected a fresh scratch directory; the next setup used private
continuation scratch without removing the retained previews. The original
R8 working tree and pre-resume native journal were retained unchanged.
An independent production-only replay passed on the continued source, with
distinct native handoffs from seven Luna/low owners and evidence of overlap.
That replay did not require a passing QA receipt and is not a full Team pass.

The independent observer served the unchanged generated bytes over loopback
in both arms: Edge 157.0.4341.60, 1440 × 900, DPR 1 and ANGLE SwiftShader.
It observed gate counts `0 → 1 → 2 → 3` and finish in **23.661 s** in R2 plain
and **7.053 s** in the R8 continuation, both within the requested 4–25 s.
Braking reduced the visible speed from **7 to 5 m/s** and **8.2 to 3.7 m/s**,
respectively. Both reset mid-run and drove again after resetting a finished run.
No browser errors or blocked requests were captured by this observer. It did not
measure a second complete finish, wheel motion continuity or comparable FPS.
Different in-game pacing makes the completion times a task check, not a
rendering-performance result.

The native QA worker observed two completed runs on **hardware** WebGL and
correctly withheld acceptance because it could not verify the required software
renderer. The independent browser run does not replace that native QA receipt.
The first read-only follow-up supplied the approved software launcher, but
the host returned `Agent not found` for the previously completed QA actor
after reconnect. That attempt still failed. The recovery replay used a new
verifier pin and, after observing the native unavailability again, assigned
the full current QA packet to one new Luna/low actor. The replacement verified
SwiftShader on the active game canvas and observed finishes at **7.022 s**
and **7.077 s** after the two starts. It checked mid-run reset, braking and
out-of-order, reverse and out-of-lane gate boundaries. Its two failed wrapper
runs and the scoped browser-default `/favicon.ico` 404 are retained. The
original failed QA receipt and narrative remain in the history. The final
native Team replay passed on byte-identical product source. This does not
reclassify the earlier attempts or qualify Corporate.

The [web validation guide](web-validation.md) checks the renderer on the
real page before running the long journey. The recovery records are under
`output/v5-corporate/luna-low-visual-pair-r8-qa-recovery/harrtest/`. The
independent Team replay has SHA-256
`225237eb816838673088c14154ad2ab88b313badf5a0d0164088ac4c70695e89`.

The treatment frame shows clearer gate numbering, a distinct coast behind the
near yard and more visible body and cabin detail, at the cost of a smaller,
darker rover in the straight chase view. Fixed stills do not establish wheel
animation quality. The R2 plain generation took **2,360.958 s** and reported
**2.1344885 Copilot AI credits**. Generation time and assistance were not matched.

The observations and unchanged PNGs are retained privately under
`output/v5-corporate/luna-low-visual-pair-r2/plain/browser/` and
`output/v5-corporate/luna-low-visual-pair-r8-continuation-r2/harrtest/browser/`.

| Retained frame | `index.html` SHA-256 | Gameplay PNG SHA-256 |
| --- | --- | --- |
| [Without HarrTest](../visual/comparison/beacon-courier-plain.png) | `fa55a83221b9ce10dede90bcec01f1a269f887d81d69220970f3f4bb7b1ec9c4` | `256f074384dd3debce31bd4259c2d5f0e9d2fabe514afbcaa21916b8fe774b8d` |
| [With HarrTest 5](../visual/comparison/beacon-courier-harrtest.png) | `7bc084279e9b322908c211206deda5526a3a56a0c04b697e8cb8786ec5424bd7` | `0183a414512b9d55e30d5a4c997aa45ac68c74d8028190a2232e35c875c75bb8` |

All attempts, including the rejected reviews, stay in the local archive.
This exercise does not count toward the held Corporate matrix or establish
an expected gain on other tasks.

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

The seventh trial also reached independent plan and coverage review. Copilot
did not reach session idle within the 2400-second cap, no root was sealed, and
the unchanged project passed 3/8 external checks. Its recorded result is a
development failure. The third and fourth held comparisons use distinct frozen
directories and retain their own runtime interruption evidence.

The eighth guarded trial used the repaired package with the consumed C# stock
case and the original task prompt. Copilot did not establish the required
independent reviews and hit the pre-admission product edit guard. The unchanged
project passed 3/8 external checks. The attempt retained its final incomplete
claim; generation reported completed transport, not completed product work.

A separate disposable Luna/low SDK probe delivered two messages to the same
native worker after its prior turns were idle and observed all three requested
worker outputs. The original parser left the last resume pending after the
automatic `read_agent`, whereas the repaired parser recorded all three closed
intervals with no pending resume. The actual probe took 43.713s and used
0.4612105 AI credits. Raw and derived records are under
`output/v5-corporate/development-copilot-followup-probe/` in the main worktree.
This tests the native delivery mechanism, not the Corporate root.

The ninth guarded trial used the same candidate and consumed C# case with an
explicit development-only workflow prompt. It sealed a schema-4 root, was
admitted, and ran the two owner scopes in parallel with 101.769s of overlap.
Only the projection worker changed product source. The SDK did not reach idle
within the 2400-second cap; it returned `FAILED`, with no independent QA or
owner handoff receipts. The partial result passed 4/8 external checks and
used 38.546648 AI credits. A read-only root replay exited 1 with
`ROOT_GOAL_UNVERIFIED`: the plan's `projection_source` citation was bound to
the pre-edit `StockProjection.cs`. The replay does not establish a successful
end-to-end Corporate root. The full terminal records remain under
`output/v5-corporate/development-corporate-guard-9/` in the main worktree.

The staged disposable picker then validated the repaired package from the
Corporate seal through parallel owner dispatch, independent QA, and root
verification. Its first revision was rejected at coverage review for missing
weekday classes and capacities. Its second sealed but was interrupted by
duplicated reviewer dispatch because owner packets inherited coordinator
instructions embedded in the request. Both attempts remain retained.

The third revision supplied stronger oracles, kept the product request
separate from coordinator instructions, and cited unchanged contracts rather
than editable source. Luna/low implemented only `src/day.py` and
`src/boxes.py` through distinct owners overlapping by 42.261s. Native QA ran
all four sealed checks and completed two follow-ups on the same actor. A
separate native Corporate reviewer supplied the current verdicts and fixed
an omitted criterion-list field without changing those verdicts. Read-only
replay exited 0 with `ROOT_GOAL_VERIFIED`, Team `PASS`, and Corporate `PASS`.
The original fourth-comparison adapter rejected the exact same native log
with its follow-up delivery error. The run took 1138.221s and used 10.271688
AI credits. The replay is retained as
`output/v5-corporate/development-corporate-followup-e2e-r3/independent-root-replay.json`,
SHA-256 `747a7bcec7b3d38f5d4edcc5df67c26f8f4ca5bbe81a63903a89e50970816b8b`.
This controlled run verifies the native mechanism and end-to-end workflow;
it does not replace a held acceptance matrix or qualify a release.

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

### First matrix results

All 96 attempts and executable evaluations were retained by November 16, 2026.
The denominator includes the timeout, transport failures and a V5 attempt with
unmatched reasoning effort. One timeout's observed elapsed time includes a
long execution gap. The original timeout record remains unchanged.

| Arm | Executable functionality | Complete quality | False accepts | Median generation seconds | Reported Copilot AI credits |
| --- | ---: | ---: | ---: | ---: | ---: |
| No HarrTest | 29/32 | 11/32 | 19 | 61.859 | 122.380940 |
| 4.1 | 31/32 | 12/32 | 19 | 81.208 | 234.714506 |
| V5 | 30/32 | 13/32 | 15 | 653.919 | 1504.6956735 |

Each credit subtotal covers 31 attempts with complete usage receipts. V5 usage
reconciled parent and child totals in 29 attempts. All 96 quality assessments
are recorded. The sealed assessor includes protected-contract and generation
validity rules in the table. Its reports also distinguish product defects from
protocol violations. Independent reviews identified 3, 5 and 3 preservation
failures, 2, 4 and 6 security failures, and 11, 12 and 8 architecture failures
in arm order. The first pin is disqualified by its 15 false accepts. The final
local summary is `output/v5-corporate/acceptance-v5-1/final-summary.json`.

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
