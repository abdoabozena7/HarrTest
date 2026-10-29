# Bounded autonomy, resource admission, and recovery (v2.1)

## General problem this addresses

An agent can make genuine progress while the parent goal stays incomplete because the next real-world verification is disallowed by an expired grant, quota, required reservation, scarce disk, absent tool, or external policy. It is wrong to declare that the goal succeeded; it is also inefficient to repeatedly ask permission without packaging a precise decision. Apply this procedure to coding, simulations, browser accounts, data jobs, deployment, and costly model evaluations.

## 1. Discover the authority hierarchy

Keep separate: (a) user's goal and source-of-truth acceptance; (b) user-approved authorization envelope; (c) host/organization/resource policy; (d) experiment's protected reservation ledger; and (e) current evidence. Higher or more restrictive real policies still govern. A broad command like "finish autonomously" is not a license to override budget guards, destructive-action confirmation, payment restrictions, production access, or safety conditions.

Extract the current permission from a real user message or existing trusted host permission artifact. A file edited by the same agent is **not** authentication of consent. Preserve approval identity/reference, allowed action categories, exact resource limit and unit, expiry, target project/environment, side-effect scope, and stop conditions. Do not invent approval. Don't consume a different phase's resources or renew expired tickets by reusing their identifiers.

## 2. Preflight once per dependency boundary, not every small step

Before a new expensive/native/protected action, snapshot process ownership, active reservations, source/config fingerprint, actual resources, next minimum reservation, and latest required gate. Reuse fresh valid preflight data for independent small steps; recheck after material changes. Attribute each resource measurement to a timestamp/environment; old free disk observations are not a capacity reservation.

If resource admission fails, distinguish **reclaimable environmental capacity** from **authority**. Safe permission-preserving alternatives (close owned process, bounded non-destructive cleanup, lossless relocation with content hashes and consumer checks, reduce incidental diagnostics not user requirements) may proceed if authorized. They do not grant execution authority. Do not delete or thin out acceptance evidence or quality thresholds to make a run fit.

Use `scripts/admission.py` for optional **read-only arithmetic/metadata preflight**. The script never starts a process, changes allowances, issues authorization, or replaces the actual host's admission gate. A positive result is `PRECHECK_OK_NOT_AUTHORIZED` by design. The external host gate and explicit genuine user authority remain decisive.

## 3. Request one useful bounded decision

When only permission is missing, report in a compact, exact form:

- `GOAL`: parent and currently verified child milestones.
- `BLOCKER`: failed gate and exact observed resource shortfall, e.g. 342.997 available vs 480 seconds required.
- `REQUEST`: smallest useful authorized addition, with chosen safety margin explained, exact unit, action category, expiry and source of authority.
- `UNCHANGED`: protected budgets, datasets, holdout boundaries, acceptance criteria and independent review.
- `AFTER_APPROVAL`: first actual command/scenario, required preflight and how results will be verified.
- `IF_DENIED`: specific independent authorized work still possible, or clean blocked stop.

**Never treat silence, empty responses, default selection, Autopilot, Allow All, or an unrelated previous approval as consent.** If the user deliberately sends an explicit scoped grant, record its real provenance; revalidate the actual host ledger before executing. A specified upper bound is a ceiling, not a target to spend. If the requested amount is more than the next minimum, explain what planned attempts justify the reserve.

## 4. Distinguish task work from external permission

Do not create false `TODO` items such as "grant myself new budget". Use:

- `IN_PROGRESS`: authorized steps with runnable next action.
- `BLOCKED_EXTERNAL`: policy, permissions, external credentials or budget source; explicit user/operator action needed.
- `BLOCKED_ENV`: tool/runtime unavailable, host limitation; investigate permitted alternatives.
- `READY_AFTER_PREFLIGHT`: grant recorded, but live runtime gate still untested.
- `VERIFIED_CHILD_ONLY`: child evidence passes; original parent remains open.

These substatuses may be represented in notes if the existing task schema has only `BLOCKED`. Do not rewrite sealed schemas just to add labels. A host UI's `Task completed` banner is never sufficient. `root_gate.py` remains the final parent authority where installed.

## 5. Resume at the first outstanding gate

After a real grant, do not repeat expensive offline checks whose source-bound evidence is still current unless source/contract dependencies changed. Perform the required new preflight and first pending native/integration check. If an authorization mechanism legitimately changes the source fingerprint, disclose and rerun the affected gates; do not exploit changing identifiers to skip an original check. Never run frozen holdout or protected acceptance until their strict prerequisites pass.

A diagnostic result is a hypothesis signal, not approval to promote a candidate to production. For a candidate that differs from baseline output, preserve the diff and assess application-level significance before changing defaults. A faster subcomponent is not a faster full product; measure causal bottlenecks under authorized representative load.

## 6. Prevent repeated failure across projects

Before changing this skill based on a failure, create a **Failure-to-Prevention entry**:

```
Observed repeatable failure:
What requirement was lost / what shortcut passed incorrectly:
Minimal real reproducer and original evidence:
Counterexample that must be rejected:
General root cause (not the project name):
Smallest reusable rule or deterministic gate:
How to test the new rule (including negative control):
What is intentionally not generalized:
Version and verification environment:
```

Add a cross-domain reference/test rather than hardcode CARLA's 480-second reservation or project-specific paths. Avoid an ever-growing mandatory checklist; prefer conditional instructions and targeted scripts. Test the new behavior against one adversarial fixture and one legitimate example. A new rule prevents a **known failure pattern when followed**; no skill can guarantee a mistake will never recur in every future host.