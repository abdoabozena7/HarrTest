# HarrTest 4.0 Gold validation

The release benchmark exercised actual workflow CLI decisions on the same
small arithmetic project with v3.2.2 and Gold. It froze 12 cases, their expected
outcomes, and the release thresholds before running either version. The two
versions received the same plans, commands, fixture sources, and independent
literal assertions. The v3.2.2 arm ran from Git commit
`6151b68f1abf16edb0e71170a4084013b31ee2cb`.
The recorded Windows run used Python 3.13.7 and candidate source fingerprint
`ed49c0989c37b258fbf6effdc8dbd9eb85b69ccddf7457bd20a275d3aefdffae`.
All 24 transcript hashes matched the report.

| Metric | v3.2.2 | 4.0 Gold |
| --- | ---: | ---: |
| Correct decisions across all planned cases | 4/12 (33.3%) | 12/12 (100%) |
| Accepted when the oracle expected rejection | 8/9 | 0/9 |
| Rejected when the oracle expected acceptance | 0/3 | 0/3 |
| Execution errors or missing results | 0/12 | 0/12 |

| Case | Expected | v3.2.2 | 4.0 Gold |
| --- | --- | --- | --- |
| Complete intake | Accept | Accept | Accept |
| Unresolved signed input edge case | Reject | Accept | Reject |
| Decision with no cited evidence | Reject | Accept | Reject |
| Changed bytes in cited evidence | Reject | Accept | Reject |
| Implementation with no scoped prompt | Reject | Accept | Reject |
| Implementation without QA assignment | Reject | Accept | Reject |
| Overlapping writes at plan registration | Reject | Accept | Reject |
| Two disjoint tasks hold live leases | Accept | Accept | Accept |
| Handoff with passing runtime evidence and matching metadata | Accept | Accept | Accept |
| Handoff with no invocation ID | Reject | Accept | Reject |
| Implementer claims its own QA assignment | Reject | Accept | Reject |
| The process exits successfully but returns 13 instead of 12 | Reject | Reject | Reject |

The overlap case measures whether the coordinator rejects conflicting scopes at
plan registration. The v3.2.2 coordinator also checks conflicts when workers
claim tasks. The valid parallel case checks that both leases were live at the
same time. The suite separately tests the final root and recorded overlap.

Run from the source checkout with Python 3.10 or newer and the v3.2.2 commit
present in local Git history:

```bash
python -B scripts/golden_benchmark.py --output output/v4-comparison
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

Use a new output directory for each run. `protocol.json` records the assigned
cases and bounds. `report.json` records both source fingerprints and all 24
outcomes with references to the retained per-case transcripts. Each trial
directory also retains the input plan, proof contracts, and any actual runtime
receipts. The benchmark checks that the candidate source fingerprint stayed
stable and returns failure if an attempt is missing, a tool error prevents
classification, or the candidate misses a frozen threshold.

The worker identities and native trace fields in this benchmark are fixture
data. The subprocess execution, CLI decisions, and numeric oracles are real.
These observations cover the exercised controller decisions for one local
project.

A separate live intake probe assigned the same ambiguous finance CSV request
to two isolated read-only projects in Codex CLI 0.165.0 with `gpt-6.1-sol`
and low reasoning effort. Each project had its own packaged version and the
same fixture source and predeclared rubric. The host blocked the command to
read the packaged skill in both turns. Skill load was confirmed in 0/2 turns
and both attempts remain blocked in the denominator.

The probe then ran two fresh turns with each exact version's skill text and
the same repository excerpts supplied through project instructions. Both
versions scored **4/6** on the declared rubric. Both asked about refunds and
CSV columns and attempted no edits. Gold also asked about one row per order
versus aggregate rows and how to invoke the export. Both missed the empty
month and the required source citation for fixed behavior. The single paired
prompt covers clarification only. General model performance, live-worker
throughput, and workplace outcomes still need separate evaluation.
