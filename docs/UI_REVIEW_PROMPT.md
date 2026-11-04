# Reusable expert review prompt — LogSense AI

Attach the current screenshot and, when available, the current template/CSS.
This prompt requests design assessment and a proposal, not implementation.

---

Act as a senior product designer and enterprise observability UX specialist.
Review the attached LogSense AI interface as a log-anomaly investigation tool
used by operators, DevOps engineers and data engineers.

## Context and constraints

- The project is in UI design. Do not edit application code, add dependencies,
  create new application pages or deploy anything in this review.
- Keep one main workspace: context facets, timeline, investigation table and
  selected-event drawer. Future import/model configuration belongs inline or
  in drawers; do not restore a seven-item module menu.
- Preserve the white background, LogSense AI identity and restrained teal accent.
- The stack remains Flask/Jinja2, HTML/CSS, limited JavaScript and future MySQL.
- Current events and charts are synthetic. The current chart is independent of
  table filters. Treat synchronization as a proposed behavior, not a completed feature.
- Show intelligence through evidence, detector identity, version/provenance and
  useful comparisons. Avoid chatbot additions, sparkles, decorative gradients,
  repetitive KPI cards and unsupported AI claims.
- An anomaly score is not a calibrated probability or proof of root cause.

## Review tasks

1. Identify strengths and specific usability problems, citing the visible
   component or inspected behavior. Distinguish observation from hypothesis.
   Do not infer runtime bugs, contrast compliance or task success from an image alone.
2. Prioritize findings P0/P1/P2. For each, state user impact, proposed change,
   tradeoff and a verifiable acceptance condition. Avoid unsupported numeric ratings.
3. Reduce competing header bands, duplicate host filters and repeated explanations.
   Preserve one unmistakable demo disclosure and all relevant behavior limitations.
4. Define a shared scope for dataset, time, host, service, severity and detector.
   Specify active-filter chips, clear actions, timeline selection, empty results,
   and whether chart selection adds to or replaces existing filters.
5. Make active signals and urgent events prominent. Keep inactive cells quiet.
   Separate priority, anomaly score and selected state. Provide visible non-color
   cues and keyboard alternatives; do not rely only on hover tooltips.
6. Propose readable typography: approximately 13–14px body/table, 11–12px
   secondary labels and 16–18px section headings. These are design targets,
   not claims that WCAG mandates those font sizes.
7. Keep essential columns scannable; move secondary evidence into details.
   Specify meaningful missing-value behavior and detection units.
8. Aim for WCAG 2.2 AA contrast, target size/spacing, focus and keyboard behavior.
   State what must be measured later rather than claiming conformance now.
9. Define normal, filtered, selected, loading, empty and error states. Preserve
   context when the drawer closes. Keep the start of the results table visible
   with the timeline at 1440x900 and 1366x768 where practical, without tiny text.

## Required output

A. Concise assessment and 3–5 strengths worth preserving.
B. Prioritized findings table: evidence, impact, change, tradeoff, acceptance.
C. Keep / simplify / remove / defer matrix for existing components.
D. One recommended annotated wireframe for the same workspace, not multiple pages.
E. Small token proposal for typography, spacing, borders, severity and selection.
F. Interaction specification and verification checklist, with current versus
   proposed behavior clearly separated.
G. Three or four concrete next steps, recommending one first.

Explain decisions in Vietnamese. Keep technical identifiers and repository
documentation in English. Stop after the design proposal and await approval
before implementation. Do not copy the reference screenshot pixel for pixel.
