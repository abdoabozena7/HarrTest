# Turn intent into a finished-result contract

Use this before dividing a new product. Keep the brief compact and proportional
to the request. Its purpose is to stop a plausible placeholder or happy-path
demo from satisfying an undefined quality claim.

## Brief before production

Write `.runtime-proof/quality-brief.md` with:

- The exact original request and the observable result the user should receive.
- Material assumptions and edge cases; distinguish delegated design choices
  from questions that genuinely require the user. Preserve the requested scope.
- The main user path and its end/recovery states.
- A few falsifiable finishing criteria for each consequential component,
  including shared representations, units, scale and state boundaries.
- Supplied runtime/workload limits and the actual evidence that will establish
  each criterion. Describe outcomes and interfaces; workers own implementations.

Adjectives such as polished, detailed, robust or production-ready are not
criteria. Name what an independent observer will see or exercise, and what
would disprove completion. Do not expand a small request with unasked features
to make the checklist look substantial.

For visible assets, distinguish **recognizable** from **finished**. Define the
intended form, structural/secondary parts, material or surface cues and how
they must read at the actual interaction scale. Construction primitives are
useful; the main representation must have an authored finish rather than read
as a generic proxy. A decorative shell cannot compensate for an unfinished
primary artifact. For nonvisual work, apply the same distinction to real
outputs, state changes and boundary behavior rather than a successful demo.

## Independent intent challenge

Give a separate native `intent_review` worker the original request, brief and
supplied constraints before production. Reuse the current model and effort.
Ask it to challenge missing meaning, generic quality claims, inconsistent
interfaces and criteria that could pass while the requested result remains
unfinished. It records specific observations in
`.runtime-proof/quality-review.md` with accept/revise and reasons. This review
does not implement product files or replace implementation workers.

Resolve its material findings, repeating that same review when needed. Do not
ask the user to decide reversible design choices they already delegated. Once
accepted, list both brief and review alongside supplied targets in the Team
plan's `validation_context`. Their hashes and absolute paths then reach every
producer, integrator and tester through the existing packet mechanism.
Retain revised briefs and rejected reviews as separate revisions. Once sealed,
keep the accepted inputs unchanged during production and repair; a changed
acceptance contract needs a newly declared attempt with the old evidence kept.

## Close the criteria with actual evidence

Link each production assignment to its finishing criteria. A syntax/import
check cannot establish a visual or behavioral outcome. Inspect a representative
component output when it can run independently. Otherwise name the pending
checks explicitly and close them at the first integrated checkpoint. Split a
complex component into bounded subassemblies when that creates independently
checkable deliverables; keep one owner per output and agreed interfaces.

Independent QA maps the accepted criteria to observed evidence and gives
functional, workmanship and responsiveness verdicts. A recognizable but
unfinished main artifact remains a quality failure. Inspect the actual output
at its delivered scale, including interaction and end/recovery states. When
motion matters, retain a short real motion recording or equivalent temporal
evidence; still images and callback totals alone do not prove continuity.

After an optimization, compare the named finishing criteria before and after.
Preserve those qualities while reducing measured cost. Retain all failed and
unverified observations and repeat the relevant current-source checks. This
workflow binds and tests cooperative evidence; it does not mechanically decide
aesthetic quality or prove that a reviewer used good judgement.
