# Outcome-first autonomy and interruption handling

Use this when the user wants a hands-off coding agent to **finish the actual original goal** and expressly accepts longer runtimes or higher ordinary model usage, rather than an early stop for convenience. It is the default *optimization priority* for autonomous work, **not** permission to spend money, exceed plan credits, alter protected experimental allowances, or ignore real host policies.

## Goal over agent-created efficiency deadlines

Treat **verified user outcomes** as the optimization objective. Time, tokens and cost are secondary *within existing authorization*. Do not invent a 30-minute, two-hour, fixed-token or fixed-iteration mission cap simply to report completion sooner. A user saying “I can wait two hours” is a willingness to wait, **not** a two-hour cutoff or a blanket authorization for paid external resources. Avoid busywork or repeated uninformative diagnostics: outcome-first does not mean infinite retries or waste.

Use finite **per-command** timeouts/health checks to detect hung programs; those are not whole-goal deadlines. If the command times out, inspect whether the subprocess or service remains healthy, safely stop only owned processes where permitted, adjust the experiment, and try again if evidence supports it. Do not disable actual sandbox, simulator admission, execution watchdog, pricing, quota, privacy, user stop, or safety limits. If the host imposes a nonextendable deadline or turns over the session, checkpoint and request resumption; do not claim background execution unless an actual scheduler exists.

## Optional consultation vs required permission

Separate three facts: **what question was asked**, **whether the UI delivered it**, and **whether the action has existing authorization**. An `Ask User` unavailable/timeout result does not mean the human is absent, disinterested or has declined. It is an interaction delivery failure unless the tool supplies stronger evidence. Never select a default approval option or record a fabricated user reply.

- **Optional leader/reviewer opinion** (e.g. harmless architecture preference, naming, prioritizing reversible internal code edits): if unavailable, record the assumption, choose a reasonable reversible option independently, and continue authorized work. If formal independent review is required for acceptance and genuinely unavailable, use an honest same-agent adversarial review for progress but do not pass a requirement that specifically mandates independence.
- **Required permission or consequential decision** (e.g. new diagnostic budget, production write, real-money spend, protected evaluation, data deletion, external publication): an unavailable dialog is **not approval**. Block **only the gated action**; continue independent already-authorized tasks where useful. Offer one explicit scoped decision and persist an exact handoff. Never silently skip the actual authority check.
- **No genuine user response possible in this host**: use the host's supported follow-up mechanism if available. Otherwise report `ACTION_REQUIRED` with the precise decision. Do not repeatedly call the same unavailable tool or pretend the user is offline.

Do not assume an authorized project-wide goal means unlimited simulator hours. A project's current authoritative resource ledger, expiry and minimum reservation still govern. The user's **time patience** is different from **action authorization** and **budget renewal**.

## Preserve completed work; resume from the first unmet real gate

Write compact durable checkpoints after meaningful progress: original goal, source/config identity, completed evidence-backed subtasks, failed/blocked gates, next authorized action, and which acceptance proofs may become stale if code/harness changes. **Don't restart planning or rerun full diagnostics just because a turn resumed.** Reuse valid retained findings; rerun only affected current-source acceptance after relevant implementation/harness changes. Revalidation of stale proofs does not erase the previously implemented feature.

If work is blocked on a genuine external dependency, keep every other authorized independent workstream moving. If no useful authorized work exists, stop truthfully and preserve an executable resume handoff; the agent must not claim “done”. The goal is to *minimize user interruptions*, not claim infinite execution or hide genuine decision gates.

## Optional deterministic classifier

`scripts/autonomy_decision.py --input interruption.json` accepts a read-only JSON advisory input:

```json
{"event":"OPTIONAL_CONSULTATION_UNAVAILABLE","authorized_independent_work":true}
```

Allowed events: `OPTIONAL_CONSULTATION_UNAVAILABLE`, `REQUIRED_APPROVAL_UNAVAILABLE`, `SOFT_TIME_ESTIMATE_EXCEEDED`, `COMMAND_TIMEOUT`, `HOST_HARD_LIMIT`, `RESOURCE_ADMISSION_DENIED`, `NO_PROGRESS`. Its output can suggest a continuation or handoff **but never grants permission, bypasses a budget, or verifies the root goal**. The event and authority flag must come from real current host/policy evidence; an agent's self-authored JSON does not prove them.

## Final check

Ask: *Did we improve the originally requested observable behavior, or only document another blocked turn?* Report the answer briefly and preserve evidence. Continue autonomously while the host is running, permission exists and a genuine next action is possible. Do not promise to run forever or deliver later from an inactive agent session.