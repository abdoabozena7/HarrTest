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

Use one row per consequential production component:

| Component and owner | Minimum functional/recognizable draft | Chosen finished result | Observable distinction at delivery scale | Evidence and rejection condition |
| --- | --- | --- | --- | --- |
| Name the bounded output | Describe a plausible crude implementation | Choose the actual form, structure, surfaces, layout or boundary behavior | State what the draft lacks that the delivered result must visibly or behaviorally demonstrate | Name the real view/action and what would fail |

A parts inventory is not a finishing contract. Listing a subject's main parts,
surroundings, labels or happy-path states can all describe a rough draft. Choose
specific relationships, transitions and useful secondary detail that make the
requested artifact intentional at its actual delivered scale. A blanket adjective
or an extra decorative shell cannot fill the finished-result column. Apply this
to each major requested artifact; one strong component cannot hide an unfinished
neighbor. A small stylized result can meet these criteria without photorealism,
more features, a larger asset count or excessive rendering cost.

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

Require a counterexample challenge for every row: describe a plausible crude
implementation that satisfies the words of the brief, then identify the exact
criterion that would reject it. If that counterexample is still an unfinished
answer and no criterion rejects it, return REVISE. A reviewer that only checks
controls, interfaces or feature presence has not reviewed finishing intent.
Retain the row-level challenge and resolution, not just an overall ACCEPT.

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

For a consequential visible component that can run in isolation, its owner
renders a private preview and actually opens the captured image before handoff.
Inspect both the component's form and how it reads at the intended scale. Bounds,
mesh counts, imports and syntax establish structure only. Keep preview scaffolds
under private evidence, separate from the delivered product. If the component
genuinely needs its consumer to be visible, mark that visual check pending and
close it on the first integrated capture rather than claiming it passed.

Treat the first runnable handoffs as a draft checkpoint. After checking basic
usability and resource cost, inspect the integrated output against the chosen
finish for each major component. The owner refines concrete failed distinctions
and hands off again; do not spend the rest of the mission merely rechecking a
recognizable draft. Compare the real current output with the retained draft and
name what changed. Extra tiny parts, repeated geometry or a prettier status panel
do not establish refinement of the requested primary artifact.

## Focused review of the actual draft

Before visual acceptance, use a separate native `finish_review` worker with the
current model/effort. Give it the accepted brief, actual draft captures and
delivery scale. It opens the images before reading implementation descriptions;
filenames and a producer's description are not visual evidence. Keep this task
focused on workmanship while independent QA handles runtime and behavior.
It may inspect already captured frames concurrently with other work, without
launching a second browser during another worker's measurements.

For every major component, it records recognition/function separately from
finishing in `.runtime-proof/finishing-review.md`: the actual visible distinction
from the minimum draft, evidence of the chosen finish, concrete defects and
accept/revise. Inspect spatial and structural relationships, intentional form
and surface cues, scale, joins/intersections, clipping, hierarchy and whether
the primary result reads as an assembled placeholder. Do not infer finishing
from the number of named parts or from an adjacent finished component.

Record the inspected image paths and current component/integration fingerprints.
The coordinator routes failed rows to their existing owners with the retained
evidence, collects fresh handoffs, reintegrates and repeats this focused review
on current captures. Give independent QA the current finishing review alongside
its complete packet; it cannot replace runtime or user-path verification. A
missing/failed row for a major component leaves visual acceptance open.

Do not review only the overall silhouette or palette. For every major visual
component, inspect a normal full frame and a focused native-resolution detail
capture chosen by the reviewer. Use the real browser's element/region capture;
retain the full-frame pair and region coordinates. Do not upscale, generate or
retouch evidence. Check surfaces, boundaries and joins in more than one public
interaction state, including a foreground/detail view when available. A broad
combined row must not let a finished subpart excuse an unfinished neighboring
subpart; report their finishing separately when needed.

Persistent stray lines, speckling, broken faces, unstable depth/overlap, clipping
or discontinuities are rendering defects to investigate, even when objects are
recognizable and the art direction is coherent. Distinguish intended facets and
ordinary edge aliasing from those defects by comparing actual views and source
structure. An ACCEPT needs inspected evidence of clean, stable relationships,
not an assertion that every primitive fits the style. If the broad review misses
a defect, narrow the next review to the component and its observable surfaces;
keep production repairs with that component's existing owner.

Independent QA maps the accepted criteria to observed evidence and gives
functional, workmanship and responsiveness verdicts. A recognizable but
unfinished main artifact remains a quality failure. Inspect the actual output
at its delivered scale, including interaction and end/recovery states. When
motion matters, retain a short real motion recording or equivalent temporal
evidence; still images and callback totals alone do not prove continuity.

QA reports each row's recognition/function verdict separately from its finishing
verdict, cites the actual output and explains how it differs from the minimum
counterexample. Merely naming the parts seen in a frame cannot establish finished
workmanship. Missing or failed finishing evidence for a major component returns
to that component's owner, even when the full user path works.

After an optimization, compare the named finishing criteria before and after.
Preserve those qualities while reducing measured cost. Retain all failed and
unverified observations and repeat the relevant current-source checks. This
workflow binds and tests cooperative evidence; it does not mechanically decide
aesthetic quality or prove that a reviewer used good judgement.
