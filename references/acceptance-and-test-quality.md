# Acceptance and meaningful tests

## The core question

For each check ask: **Could the requested feature be broken while this check
still passes?** If yes, identify the blind spot and add a behavior-level check.
Do not delete useful unit tests; limit what their success is allowed to claim.

## Build independent oracles

Derive expected behavior from the user's requirement, an approved specification,
a trusted reference, an independently calculated example or a known invariant.
Do not copy the implementation into the test, derive the expected answer from
the returned answer, or make a model grade its own prose as the sole authority.

Good acceptance: click Save -> see a successful real request -> reload or
restart -> retrieve the persisted value from the real system. Bad acceptance:
assert the click handler exists or mock Save to return success.

Good simulation acceptance: a full recorded native route satisfies the original
physical criteria with measured terminal outcome. Bad acceptance: assert that
`drive()` returned, GPU memory increased, or the scenario configuration requested
three overtakes. Requested events are not observed events.

Good agent-pipeline acceptance: send a real prompt, inspect plan/tool behavior,
run the generated artifact and independently verify its requested functionality.
Bad acceptance: search the generated files for the word "button", trust the
worker's tests, or grade the fluent final response.

## Required coverage mapping

For every requested outcome define inputs, preconditions, controls/modes, expected
observable results, source/environment, evidence and likely failure modes. Map
requirements to checks and TODO tasks. Keep untested rows visible. "All modes"
means the named inventory was exercised; it never means all conceivable states.

For small changes, test the changed behavior and adjacent regressions. For a
whole site, inventory important pages/controls, states, roles and breakpoints.
For higher-risk changes, expand coverage deliberately. Do not exhaustively
click destructive actions on real accounts merely to fill a matrix.

For selective rules, include both intended targets and legitimate near matches;
removal/rejection alone can hide overbroad loss of valid behavior. For multi-step
calculations or state changes, check the contract's intermediate invariants and
failure boundaries as well as final outputs. Distinguish an inherited limitation
outside the changed contract from a new or requested behavior defect. Performance
and resilience checks follow actual impact and budgets, not an assumption that
all persisted collections must have constant space or every refactor must add
unrequested input modes.

## Verify compatibility for existing code

- **Preserved behavior.** Select relevant old successes and rejections at the
  affected public entrypoint. Record their expected outcomes from the existing
  contract and baseline, then replay the same inputs on the candidate. Include
  nearby cases the change could accidentally admit or reject. Compare the
  result, exit status or state that callers depend on, with diagnostic text only
  when it is part of the contract. Cite the authority for any intended change
  to these outcomes.
- **Protected project boundaries.** Cite the repository rules, contracts or
  approval that govern the affected paths and interfaces. Review the full diff
  from the baseline for changes outside that authority, including new, moved
  and deleted files. When a rule requires particular files to stay
  byte-identical, compare their digests as well.
- **Existing test oracles.** When tests change, trace the previous inputs and
  assertions for preserved behavior to their current equivalents. Replay the
  original checker or an equivalent check on the candidate. In a disposable
  copy, confirm that the current check fails when the retained invariant is
  violated.

In the [managed mission review](feature-preservation-and-completion.md), assess
each inventoried behavior and changed or deleted test on current source. Bind
the review to actual proof receipts. A changed test hash requires independent
review, but neither a changed nor an unchanged hash establishes the strength
of an oracle. Reject any non-equivalent replacement for preserved behavior.

## Negative controls and anti-theater checks

Use safe negative controls to establish that a meaningful failure is detectable:
invalid user input, rejected unauthorized requests in a test account, a deliberately
wrong expected value in an isolated verifier, a known disconnected demo button,
recorded collision fixture for a scoring rule, or a malformed generated artifact.
Expected failure must be asserted explicitly; a crashing checker is not success.

Prefer targeted temporary fault injection in a disposable copy, not modifications
to production or a shared experiment. Restore/check the baseline afterward. Never
change protected datasets, holdouts, resource ledgers or safety mechanisms. A
negative control is not a second chance to tune on acceptance data.

If unsafe or disproportionate, state a specific exception and use another source
of assurance. The script enforces presence of a concrete rationale, not its wisdom.
An independent reviewer must reject weak exceptions.

Reject or repair tests that:
- Assert only truthiness, file existence, build exit code or a canned success line.
- Mock the exact integration under test and then claim native completion.
- Compute expected results by calling the function being tested.
- Swallow exceptions, accept missing artifacts, skip critical checks or reuse old logs.
- Change thresholds or snapshots only because the actual behavior failed.
- Assert that an action was requested instead of verifying its actual consequence.

A unit test with a narrow correct claim is valuable. A large suite with an unjustified
product-level claim is not. Keep failure cases after a fix as useful regressions.

## Evidence chain

Preserve requirement -> input -> action/tool invocation -> observation -> assertion
-> artifact -> source/environment identity -> review. Capture failures too.
Use runtime timestamps and unique run IDs. Distinguish wall-clock duration from
simulation time, startup from steady-state time and GPU load from model training.

Freeze source for final evidence. Include configuration, lockfiles and verifier
code in the fingerprint. Bind relevant dataset/model identifiers explicitly.
Do not store secrets or large weights in the source scan. Local files may change
without a Git commit, so a commit hash alone is insufficient.

The collector rejects stale or tampered receipts/artifacts and missing required
checks. It cannot independently know that an arbitrary script's measurements
are truthful or the supplied oracle is correct. Prefer independently observed
state changes and reviewer-run checks over producer-generated success booleans.

## Visual and behavioral review

Open the image/video/trace, not just the filename. Check clipping, states,
hierarchy, contrast, focus, responsiveness and actual user actions as relevant.
Inspect multiple frames or a video for motion; do not infer a full route from
a screenshot. Record concrete observations and exact artifact paths. If image
inspection is unavailable, label it unverified instead of writing a visual review.

A fresh-context reviewer is useful, but another language model is not guaranteed
independent evidence. Record whether the review was same-agent, fresh-context,
human or an external verifier. The bundle requires review for web/simulation
requirements but cannot force the reviewer to perceive correctly.

## Final claims

Only use VERIFIED_WITHIN_SCOPE for the declared scope actually covered by current
evidence and inspected outcomes. Keep false positives, retries, skipped cases and
limitations in the final report. PARTIAL, FAILED and BLOCKED_UNVERIFIED are valid
honest outcomes; they are never aliases for done.
