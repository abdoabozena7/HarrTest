# Experiment economy, tail criteria and live-evidence lifecycle

Use this reference when an agent runs costly tests, a simulator, long browser runs,
paid inference/training, or a protected validation sequence with limited capacity.
These rules apply **in addition to**, not instead of, actual host admission,
trusted user consent and the root contract.

## A. Before asking for more resources, compute the *true* minimum

1. Locate the **actual current policy** (code/CLI/config/API), not the agent's
   previously chosen duration. Record the specific source and revision. Identify
   its minimum/maximum execution duration, fixed cleanup or startup reservation,
   allowed granularity, phase-specific allowances and all immutable windows.
2. Independently identify the **minimum meaningful duration** from the original
   experiment's unchanged measurement/coverage requirements. A shorter legally
   admissible run may be scientifically useless. Do not infer meaningful scope
   only from what fits in the wallet.
3. Distinguish **policy floor**, **meaningful floor**, **preferred plan**, and
   **actual remaining unprotected allowance**. These are four different facts.
   Include any required safety margin; use the host's actual preflight as final
   authority. Read-only arithmetic is not approval or resource reservation.
4. Recompute after each budget charge or rule/source change. Explicitly state
   the **minimum single-run shortfall**, not misleadingly present it as a total
   funding estimate for the user's entire goal. Never borrow a protected holdout
   or change already-charged reservations to make a candidate fit.

`scripts/experiment_budget.py policy.json experiment.json` performs arithmetic
only. Inputs MUST be independently checked against real project/host policy and
original requirements. Its successful result is
`CANDIDATE_READ_ONLY_NOT_AUTHORIZED`, never a permit.

### Read-only cross-domain example

- Host policy minimum execution: **180 s**; fixed cleanup reserve: **300 s**.
- Scientific minimum: **240 s**; preferred execution: **300 s**.
- Actual free diagnostic allowance: **550.070 s**; 10 s conservative margin;
  one-second granularity; shorter-than-preferred is explicitly allowed by the
  original scientific goal.
- Legal policy minimum: `180 + 300 = 480 s`.
- Meaningful minimum: `240 + 300 = 540 s`.
- Preferred plan: `300 + 300 = 600 s` (too large).
- Candidate `240 + 300 = 540 s` fits as arithmetic with 10.070 s remaining;
  the actual host **must separately admit** it.
- With only **262.367 s** remaining, legal single-reservation shortfall is
  **217.633 s**; the meaningful shortfall with 10 s margin is **287.633 s**.
  Neither amount is an estimate to complete a multi-stage research program.

This pattern also applies to cloud-test minutes, GPU slots, API quotas,
expensive deploy previews and nondestructive integration tests. The specific
numbers above are illustrative, not global HarrTest defaults.

## B. Hard gates are conjunctive, not a dashboard score

If the original contract requires p95, p99, **and zero late frames**, success
requires **all three**. One failure in the tail rejects the whole declared
acceptance despite passing percentiles. Do not skip the outlier, raise the
limit, substitute another scenario or reinterpret all-of requirements as
"mostly good". Report complete sample count and worst instance identity.

Use `scripts/strict_gates.py contract.json readings.json` for a **read-only,
unauthenticated arithmetic helper**. The independently preserved contract must
name **every required gate**; absent, duplicated or nonfinite measurements fail
closed. The helper cannot know whether the contract is complete or whether the
values come from the real test. The project evaluator/root gate stays authoritative.

When one outlier remains, preserve its complete identity, clock alignment,
source, environment, observer overhead and neighbouring samples. Determine if
it reflects a real deadline miss, timing instrumentation, transport, scheduling
or a measurement defect **without discarding the original sample**. Justify
one falsifiable change and negative control before spending another full run.

## C. Make costly tests information-rich rather than repetitive

- First reproduce failure using existing saved evidence where that evidence is
  valid for diagnosis. Use bounded offline microbench/replay and fresh-context
  review before native expense; never claim offline replay proves real driving.
- Before changing source, account for any **mandatory requalification cost**
  from fingerprints, safety gates and frozen protected sequences. Bundle related
  independently justified changes only when their contracts allow it. No
  source-change trick may evade requalification.
- Prefer the minimum **scientifically meaningful** experiment that can decide
  a falsifiable hypothesis; preserve hard acceptance unchanged. Diagnose
  whether monitoring or instrumentation perturbs the outcome. Correlate clocks
  without summing overlapping counters or treating throughput as renderer FPS.
- On failure, inspect the real raw log and decide whether the *same* unmodified
  trial could add information. If not, do not repeat it. Record measured effect
  and remaining tail rather than only "tests passed" or percentiles.

## D. Capture ephemeral evidence while the product is alive

A stopped simulator or closed browser cannot provide **live** visual proof.
When approval allows a live run, acquire and inspect authorised camera/UI/
network/sensor artifacts **during** the run, under the same owned session and
without interfering with its critical timing. Preserve asynchronous monitoring
failures separately so one observer exception does not silently invalidate or
terminate the user task. A screenshot/video after teardown is historical
recorded evidence, not live visual acceptance. Don't launch a fresh expensive
run merely for a screenshot without a meaningful, authorized test purpose.

## E. Resumption and funding request template

Report: original root goal; confirmed child results; current source hash;
first unmet *original* gate; its exact failure and **all** hard thresholds;
proposed offline falsification; policy floor vs meaningful floor vs preferred
budget; actual unprotected resource balance; projected source requalification;
required permission/phase/maximum/expiry; what happens if denied. **No response
means no new consent**. Keep previous grants, charges and original evidence.