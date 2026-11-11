<img src="visual/banner.svg" alt="HarrTest 4.0 Gold. A request branches into independent work, passes separate checks and converges on final verification." width="100%" />

# HarrTest 4.0 Gold

HarrTest is a skill and local workflow coordinator for coding agents. Gold
preserves what the user asked for, ties consequential decisions to evidence,
and requires independent testing before accepting the integrated result.

[Install](#install) · [Start a task](#start-a-task) · [Gold runbook](references/v4-gold.md) · [Measured results](references/v4-validation.md)

## What Gold requires

| Stage | What the workflow keeps |
| --- | --- |
| Understand the request | The original wording, interpreted outcomes, material edge cases, and user answers when a decision needs clarification. |
| Justify the plan | Evidence for consequential choices, linked to the relevant original requirements. |
| Divide the work | A dependency graph and a focused, self-contained prompt for each worker, with file scope, interfaces, and expected checks. |
| Run independent branches together | Separate native host invocations for ready tasks with compatible scopes. The coordinator tracks ownership and shared resources. |
| Test each implementation | A distinct testing agent runs the agreed checks after the implementer hands off and records the observed result. |
| Verify the whole task | Integration runs against current source and checks the original outcomes. Gold also requires a comparison with the baseline. |

For example, a request to add CSV export could leave the delimiter, encoding,
and permission rules unclear. Resolve the choices that affect acceptance
before dividing the work. Once the interface is agreed, separate workers can
implement the exporter and integrate the download action in parallel. Their
testers exercise the agreed cases, and the integration check downloads and
inspects the resulting file through the real entry point.

## Install

The skill ID is **`harrtest`**. The local scripts use Python 3.10+ and the
standard library. Use your host's skill installer, or install from the repository
through the Agent Skills CLI:

```bash
npx skills add https://github.com/abdoabozena7/HarrTest --skill harrtest -g
```

Select your coding host, reload its skill discovery, and have it confirm which
version it actually loaded. Pin active missions to the version that sealed
their contracts.

From a checkout of this release, the bundled installer can also set up
project instructions and supported optional hooks. For Copilot on Windows:

```powershell
py -3 .\scripts\install.py --agent copilot --scope user --project C:\path\to\repo --instructions --hooks --update --dry-run
py -3 .\scripts\install.py --agent copilot --scope user --project C:\path\to\repo --instructions --hooks --update
```

Review the dry run before installing. The installer merges existing project
instructions and retains backups. Automatic stop enforcement requires a
supported hook that the host actually invokes.

## Start a task

Give your host the original task together with a request to use Gold:

```text
Use HarrTest 4.0 Gold for this task. Capture my original request and ask about
material edge cases you can't resolve from the available evidence. Tie key
decisions to their sources. Give independent work to parallel native workers
with focused prompts, and have a different agent test each implementation.
Verify the integrated result and show the measured baseline comparison.

Task: [your original request]
```

The host prepares the contracts and plan. A Gold workflow declares
`golden: {intake, protocol, measurement}` in its plan and sets
`protocol: "golden-v1"` on its schema-3 root. That binds Gold checks to the
root even when a verifier calls it directly. The coordinator uses the host's
actual workers and tools.

```text
python <skill>/scripts/golden.py --project . inspect --plan gold-plan.json
python <skill>/scripts/workflow.py --project . init --plan gold-plan.json
python <skill>/scripts/workflow.py --project . ready --goal mission
# Dispatch the ready work, collect handoffs, and run the independent checks.
python <skill>/scripts/golden.py --project . candidate --plan gold-plan.json
# Record the candidate measurements against the returned source identity.
python <skill>/scripts/golden.py --project . compare --plan gold-plan.json
python <skill>/scripts/workflow.py --project . root --goal mission
```

Each worker receives a scoped task packet. Its handoff ties the packet to the
native invocation, retained trace and observed checks. Use the real entry
point for acceptance, such as a browser
journey, a public API call, or the generated program running in a fresh
process. The runbook covers each command and the evidence it expects.
[Gold runbook](references/v4-gold.md)

## Measure before and after

In 12 matched local CLI cases, correct gate decisions rose from **4/12 on
v3.2.2 to 12/12 on Gold**. False accepts fell from **8/9 to 0/9**. A separate
live intake probe scored **4/6 on both versions**. [Cases, raw evidence and reproduction](references/v4-validation.md)

Predeclare cases, baseline and success thresholds. Keep failed, blocked and
missing attempts in the comparison. The local cases measure controller
behavior; the single live probe cannot establish an improvement in agent
quality or workplace outcomes.

Run the regression suite from the repository:

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

## Existing workflows and project tools

- Existing v3 workflows retain their contract and evidence history. Keep old
  seals and receipts when upgrading. [Migration](references/v3-migration.md) · [v3 workflow](references/v3-workflow.md)
- Project Builder coordinates runnable milestones for a new product and
  verifies their cumulative behavior. [Project Builder](references/project-builder.md)
- Project Memory keeps source-qualified facts and task context in
  `~/.harrtest/projects/`, outside both the project and the installed skill.
  [Project Memory](references/project-context-memory.md)
- CI exercises Windows and Linux and packages the complete installable skill.
  [CI](https://github.com/abdoabozena7/HarrTest/actions/workflows/verify.yml)

## Trust boundaries

Gold enforces its declared checks inside the workflow and root verifiers.
Coordination and provenance depend on the host and the people or agents
recording evidence. The quality of an interpretation, the completeness of the
edge cases, and the identity behind a worker record require independent
review. Use a trusted evaluator and evidence store outside worker write
access when the result has production consequences. [Security](SECURITY.md) · [Capability boundaries](references/security-and-limitations.md)

[Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
