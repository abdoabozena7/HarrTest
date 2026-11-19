# HarrTest 5

HarrTest is one installable coding-agent skill: **`harrtest`**. The Corporate
workflow is part of version 5, not a separate skill or edition. It starts with
the existing project's architecture, contracts, and measured baseline. It
assigns independent changes to native implementation owners and uses separate
QA to verify the integrated result on current source.

Check the GitHub release notes for the release channel and the
[validation record](references/v5-validation.md) for measured results and
limits. The initial V5 preview did not meet the stable release criteria.

[Install](#install) · [Start a task](#start-a-task) ·
[Corporate workflow](references/corporate-workflow.md) ·
[Changelog](CHANGELOG.md)

## Install

Download the single installable `skill.zip` for your chosen HarrTest 5 release
from [GitHub Releases](https://github.com/abdoabozena7/HarrTest/releases).
Extract it to get the `harrtest` folder, including its Python 3.10+ scripts
and references. If you already use HarrTest, update your existing installation
instead of adding a second copy.

To install from `main` with the Agent Skills CLI:

```bash
npx skills add https://github.com/abdoabozena7/HarrTest --skill harrtest
```

For a project-scoped Copilot install on Windows, run from the target project
using the bundled installer from the extracted folder:

```powershell
py -3 C:\path\to\harrtest\scripts\install.py --agent copilot --scope project --project . --update --dry-run
py -3 C:\path\to\harrtest\scripts\install.py --agent copilot --scope project --project . --update
```

Review the dry run before installing. Reload skill discovery and confirm
that your host loaded `harrtest` version `5.0.0`. Keep active missions pinned
to the version that sealed their contracts. Optional instructions and hooks
are described in the [workflow guide](references/corporate-workflow.md).

## Start a task

Give your host the original task and invoke the skill:

```text
$harrtest
[your original request]
```

Use the [Corporate workflow](references/corporate-workflow.md) for substantial
existing-code changes and [production teams](references/production-teams.md)
for scoped native handoffs. Independently check functionality, preservation,
architecture, security, performance and resilience as applicable. A required
check without evidence stays unverified; an aggregate score does not waive it.

## Compatibility and project tools

- Existing v3 and Gold workflows retain their contract and evidence history.
  Keep old seals and receipts when upgrading.
  [Migration](references/v3-migration.md) · [Gold runbook](references/v4-gold.md) · [4.1 results](references/v4.1-validation.md)
- [Project Builder](references/project-builder.md) coordinates and verifies
  runnable milestones for a new product.
- [Project Memory](references/project-context-memory.md) keeps source-qualified
  facts and task context outside installed skill files.
- [CI](https://github.com/abdoabozena7/HarrTest/actions/workflows/verify.yml)
  exercises Windows and Linux and packages the skill.

Run the regression suite from the repository:

```bash
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

## Trust boundaries

HarrTest verifies declared evidence; it does not sandbox agents, grant
permissions, or guarantee an independent evaluator. Keep production acceptance
evidence outside implementer write access. See [Security](SECURITY.md) and
[capability boundaries](references/security-and-limitations.md).

[Contributing](CONTRIBUTING.md) · [MIT license](LICENSE)
