# v3.0.0 validation and limits

Baseline: official v2.6.1 at `04d968681226778b97511bfd6024272eac19fb9f`.
Implementation date: 4 November 2026. No user CARLA project files were modified.

## Executed locally
- Baseline suite: 147 tests, 146 passed and one optional browser test skipped.
- v3 suite: 214 tests, 213 passed and one optional browser test skipped, including the old regressions and new integrity, coordination,
  request-coverage, evaluation and actual CLI workflow cases. See GitHub Actions
  for the independently executed result on each CI operating-system/Python matrix.
- New tests exercise real SQLite transactions, concurrent connection claims,
  process-level CLI reopening, stale tokens, resource/read-write conflicts,
  event history, unknown-effect reconciliation and current-source verification.
- Original-root stop tests reject a passed child with incomplete integration,
  preserve historical gate bytes, and honor explicit cancellation/forced-stop safety.
- Schema-3 coverage tests reject uncovered restart text, unmapped requirements,
  stale/tampered reviews and undeclared self-review. These are synthetic review
  fixtures, NOT real independent model or human judgments.
- A real CLI persistence example initially acknowledges Save without writing data.
  Separate-process Read returns null, and an independent assertion fails. After
  the actual write is repaired, save/read/restart and integration pass. Every
  coordinator CLI command reopens the database; the task state survives. A later
  source edit invalidates old successful acceptance. Raw failure/success receipts
  are retained in the demo's chosen output directory.

Reproduce:

```text
python -B -m unittest discover -s tests -p 'test_*.py' -v
python examples/workflow_demo.py --output /path/to/new/disposable-directory
```

## Explicitly not certified
No live Copilot Desktop/CLI session, real hosted-model delegation, CARLA simulation,
GPU training, production deployment, remote signed evaluator, security accreditation
or model-improvement benchmark was executed during local authoring. Optional
browser dependencies are not installed by this package, and skipped browser checks
must never be reported as successful visual validation.

The release does not claim the research roadmap's 10-point completion increase,
30% intervention reduction or 144/1080 live-model trial campaign. `evaluation.py`
helps summarize controlled measurements; it does not manufacture them. A working
fixture or increasing helper-test count is not evidence of stronger LLM performance.

## Trust boundaries
The workflow store coordinates cooperative actors. File leases do not enforce OS
write isolation. Hash chains detect inconsistent history but are not a defense
against an administrator rewriting the DB and all hashes. Imported reviewer IDs,
process-inspection reports and operation outcomes require real provenance review.
The collector's argv execution still uses the host's existing permissions. For
consequential enterprise use, isolate the evaluator/contract and execution resources
from the implementer's unrestricted write access.

## Installation acceptance still required on your host
Confirm actual skill loading, complete-source version verification, tool availability,
native subagent discovery when used, real hook invocation and unchanged model/provider.
Test a small real task before long native work. The installer's successful file copy
is not proof of the installed agent following the skill.
