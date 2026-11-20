# Feature preservation and completion

Use `preservation-v1` for every new implementation mission, including narrow
fixes and greenfield work. It extends the existing Team and root gates, receipt
collector, and private project memory. It does not create workers or change
their write scopes.

## Before the first product edit

1. Retain the **exact original request**, including constraints and acceptance
   criteria. Use a stable goal ID, shared with the Team/root when applicable.
   In an existing project, follow the actual entrypoints and symbols through
   affected callers and dependencies. Read applicable tests, configuration,
   optional modes, permissions, persistence and error paths. Identify public
   contracts, internal invariants and adjacent behavior that the change could
   break. Documentation and prior chat are leads, not proof.
2. Record the smallest sufficient set of actual files and their SHA-256s. Include
   the affected code, callers, check implementations and config/locks that
   affect its behavior. Name planned additions as absent. Keep unrelated code,
   secrets and generated dependencies out of the scope.
3. Give each relevant behavior a stable ID, location, observable result,
   contract and basis (`documented`, `observed`, `implementation_detail` or
   `assumption`). Include material dependencies, old test paths, planned effect,
   uncertainty and proof checks. Concrete implementation details are not
   automatically permanent compatibility promises. Missing docs or tests are
   not authorization to remove a working behavior. Investigate unknowns before
   attempting any destructive change.
4. Map every requirement to one or more TODOs with one owner, dependencies,
   explicit Definition of Done and sealed `proof-task/check` selectors. Include
   old and new behavior, regression controls and integration as applicable.
   Use the same requirement IDs on the ledger, Team outcomes and root.
   Include integration requirements in those maps. A small mission can be
   one TODO and a few checks. For genuine greenfield scope with no existing
   behaviors, explicitly record why the inventory is empty.

Use existing `proof.py` task contracts to define checks and run each replay
against the original source before mission initialization. For preserved
behavior, replay the same command and assertions on candidate source. Keep a
small independent oracle rather than relying solely on tests an implementation
worker may change. The agent creates and maintains records in private state;
the user does not fill out JSON. Adapt the [mission template](../assets/templates/mission.json).

```text
python -B <skill>/scripts/mission.py --project . --goal mission snapshot --source src/file --source tests/check
python -B <skill>/scripts/mission.py --project . --goal mission init --plan .runtime-proof/mission-draft.json --request-file REQUEST
python -B <skill>/scripts/mission.py --project . --goal mission status
```

Seal the existing [Team plan](production-teams.md) with
`"mission_protocol": "preservation-v1"` and, on the root route, the same field on
the [root contract](corporate-workflow.md). For standalone work use
`pre-edit --owner OWNER` on the mission CLI before edits. In Team and Workflow
dispatch use the actual returned packets; do not replace them with a summary.

## Classify effects and obtain scoped decisions

| Effect | Meaning |
| --- | --- |
| `PRESERVE` | Default. Replay old behavior; use for unmentioned supported behavior. |
| `EXTEND` | Add capability and replay the old behavior on the candidate. |
| `MODIFY_EXPLICITLY_REQUESTED` | Change only the named behavior; retain the exact authorizing request excerpt and test the new outcome. |
| `REMOVE_EXPLICITLY_REQUESTED` | Remove only the named behavior; excerpt and checks must bound the effect. No redundant question. |
| `POTENTIAL_COLLATERAL_CHANGE` | A material unresolved conflict. Record alternatives, why they cannot meet the contract, the exact planned effect and its impact. |
| `UNVERIFIED` | Evidence is insufficient. Reinspect/resolve before editing the affected scope. |

Split explicitly changed behavior from retained parts of the same interface.
For example, retiring one flag is not authorization to remove the CLI's exit
contract or other flags. Refactoring is fine when behavior remains compatible,
including callers, data, input formats and failure behavior. A planned compatible
move must still replay the old behavior. Keep the original test assertions unless
an intentional change or independently verified equivalent justifies updating them.

Attempt a reasonable behavior-preserving implementation first. Ask the user
one specific question only when a material conflict remains. Identify the
exact behavior, code evidence, reasonable alternatives and likely user/caller
impact. Bind the actual reply to the affected feature before acting, for example:

```text
python -B <skill>/scripts/mission.py --project . --goal mission decision --feature legacy_mode --verdict approve --response RESPONSE --origin USER_TURN
```

Use the literal user reply and its actual provenance, not a planner's rationale,
an inferred yes, or a team role as a substitute for approval. A reply of
`approve FEATURE_ID` or `deny FEATURE_ID` is unambiguous after presenting the
exact proposed change. The gate also accepts `I approve: ` or `I deny: `
followed by the exact recorded `planned_effect`. A reply that merely mentions
the feature does not authorize the effect. Denial or no answer keeps dependent
work `BLOCKED_APPROVAL`. Continue independent authorized
scopes, do not edit the affected behavior, and don't mark the original goal
complete. Harmless internal changes, compatible refactors and already
authorized removals need no question.

## Progress, QA and recovery

- Record each concrete TODO as `IN_PROGRESS` when working and `IMPLEMENTED`
  only once its own deliverable exists. Use `mission.py ... step --task ID
  --status STATUS --note OBSERVATION`. An owner handoff supplies evidence, not
  progress for forgotten items. Team integration moves eligible items to
  `VERIFYING`; for standalone work use `mission.py ... integrate`.
- Run the required candidate checks using `proof.py` on current source. Use
  `mission.py ... review-input` as the structured QA input. Give each TODO,
  old behavior, and changed/deleted protected test an independent observed
  verdict. Check against the original code and baseline; use old inputs and
  independent assertions, including nearby options and relevant rejection
  paths. Inspect the old test and its replacement or replay oracle if a test
  was weakened, moved or removed. `oracle_paths` can pin files that must not
  change; use frozen or independently retained oracles, not candidate-only claims.
- In Team use the existing independent QA `check` and `review` commands and
  provide the structured review as `--evidence`. For a managed standalone root
  submit the reviewed artifact with `mission.py ... review --evidence FILE`.
  Root satisfier proof tasks must name this root via `proof.py init --root-goal ID`.
  The ledger reaches `VERIFIED` only with a passing current structured review
  and every required passing execution. A child pass or handoff does not mark
  a root verified. After reopening an item, rerun its affected proof tasks
  and collect a new independent review even if the source is unchanged.
- In a fresh session, use `mission.py --project . list` if the goal ID is
  unknown. Match the stored original request rather than choosing an
  unrelated goal or starting over. Check the same mission with `mission.py ... status` and
  `project_memory.py ... brief --goal-id ID` in a fresh session. The exact
  request, feature IDs, ownership, TODO history and Definitions of Done are
  stored locally. Compare source identities (including uncommitted content)
  and reopen stale verification with Team repair or `mission.py ... reopen`.
  Re-read changed or missing affected source
  and dependencies, then run `refresh --note OBSERVATION` to bind that inspection;
  it does not overwrite the baseline or make a check pass. Resume the next
  authorized unfinished scope. Resolve assumptions before freezing a contract.
  If new inspection contradicts a frozen baseline contract or the bound record
  is missing, recover the original evidence or create a new reviewed attempt
  retaining the original requirements and unfinished work. Never silently
  replace a seal with a weaker one.
- Record real external blockers as `BLOCKED_ENVIRONMENT`, failures as `FAILED`,
  and explicit user cancellations as `CANCELLED_BY_USER` (`step` with the
  literal `cancel ID` reply file as `--evidence` and actual `--origin`).
  These are not verified results for the original goal. After an external
  blocker is resolved, use `reopen` and obtain fresh admission.
  Before reporting, reconcile every mandatory item and run the original Team
  and/or root verifier. Report partial, cancelled and blocked work honestly.

## Enforcement and compatibility

Managed gates deterministically reject missing contracts/ledger items, unknown
or uncovered checks, illegal transitions, stale source/executions, missing
decisions and changed pinned oracles. They require current independent review
coverage for preserved behavior, tasks and changed tracked test assertions.
The reviewer, not a hash or test count, judges discovery completeness,
authorization meaning, hidden collateral loss and equivalence of rewritten tests.
Cooperative records cannot authenticate who authored a local user response or
stop a same-user writer from rewriting state; retain the actual host provenance.

The gates are active when using the managed Team/Workflow commands and root
verifier. The existing optional Copilot CLI hook blocks supported editor and
dispatch tools before Corporate admission when enrolled. This does not block
arbitrary shell, MCP or manual writes, nor inspect every action on every host.
Unsupported native hosts can use the local evidence but cannot claim supported
native acceptance. No hook or skill can continue a terminated host process.
Existing unmarked plans, schemas and pinned seals retain their previous
verification meanings. Do not silently migrate an active mission.
