# Goal-grounded verification (v2.3)

## Three separate results
- **Product success:** independently observed intended behavior.
- **Evidence integrity:** coherent typed decisions, source, artifacts, target, run identity and ordered steps.
- **Root completion:** every original user requirement and final integration have current evidence.

Passing a smoke, child receipt, or evidence-format check is never universal product success.

## False-positive defense
Parse typed status and passed, not a prose PASS token. Invalid, contradictory, truncated, old, wrong-target, wrong-mode, missing or tampered evidence fails closed. Never let a newer unavailable or pending result erase an older observed failure. A completely new valid successful run can supersede a failure, but keep failure history. Do not mix steps across runs or reuse previous success for an incomplete latest attempt.

## Child and root ownership
A Child is accountable for its declared milestones, not features assigned to future Children. Unknown assignments are unverified, not silently reduced. The Root keeps the original full request, re-tests previously integrated features on final code, and checks full integrated user journeys. Use the existing sealed root_gate.py as authority; the new guard is supplemental and does not authenticate root sealing.

## Ordered behavioral probes
Observe multi-action transitions, not independent buttons: Start -> Pause -> Resume -> Reset; Save -> Reload -> Read; Failure -> Retry -> Recover. The browser_probe.py actions capture_text, expect_text_same, expect_text_changed and bounded wait_ms assert measured state rather than labels. A negative control that breaks Resume must fail in a disposable workspace. Real browser experiments require Playwright and a browser.

## Read-only integrity check
Run:
python scripts/goal_guard.py --contract goal-contract.json --events observed-events.json --evidence-root evidence --output guard.json

A schema 1 goal contract has scope child/root, source_sha256 (lowercase 64-hex), and requirements with id, target, mode and journeys. Each journey has id and ordered step IDs. Each event has requirement_id, journey_id, step_id, run_id, source_sha256, target, mode, status, passed, observer, evidence_file and evidence_sha256. status is PASS, FAIL, PENDING, NOT_RUN or UNAVAILABLE; passed is true, false or null, and must correspond exactly.

For root scope, provide root_request_sha256 and --root-contract pointing at the v2 root contract; all original root requirement IDs must appear. This proves ID coverage only, not semantic completeness, actual runtime truth, or root seal integrity. Run the existing proof.py and root_gate.py independently. Include event collectors, test plans and verifier code in source fingerprints. Never self-invent events to satisfy this tool.

## Measurement
Separate independent actual product success from verifier decision accuracy (false acceptance and false rejection). Keep replay, offline fixtures, model runs and real-browser sessions in separate denominators.

Adaptation motivation: Mini Hivo Experiment 18 missed Pause -> Resume, Experiment 19 found truncated-output false PASS, and Experiment 20 studied child-scoped versus root obligations. This is an engineering safeguard, not a claim of validated general reliability.
