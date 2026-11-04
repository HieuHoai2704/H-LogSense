# Timeline V2 UI design review

Status: **Historical design proposal**, reviewed on 2026-11-03.
The subsequent implementation request is recorded in
[Investigation V2 implementation report](../INVESTIGATION_V2_IMPLEMENTATION.md).
Actual application screenshots are in `implementation-v2/`; images below are
the original static design sheets. Their verification reports describe the
design-stage snapshot, before application implementation.

The original design artifacts below were created before application implementation.
Their source-integrity reports describe that earlier snapshot. Current code and
test status are recorded in the implementation report linked above.

- [UI specification and source audit](TIMELINE_V2_UI_SPEC.md)
- [Desktop, 1440px](timeline-v2-desktop.png) · [editable SVG](timeline-v2-desktop.svg)
- [Compact, 1024px](timeline-v2-compact.png) · [editable SVG](timeline-v2-compact.svg)
- [Selected bin and linked results, 1440px](timeline-v2-selection.png) · [editable SVG](timeline-v2-selection.svg)
- [Evidence panel, 1440px](timeline-v2-evidence.png) · [editable SVG](timeline-v2-evidence.svg)
- [Volume, coverage and request states](timeline-v2-states.png) · [editable SVG](timeline-v2-states.svg)
- [Artifact verification](VERIFICATION.md)

The principal wireframes use the existing six synthetic anomaly records, at their
existing timestamps. The separate state sheet illustrates proposed UI states;
it is not a report about source availability or measured performance.

Review decisions: information hierarchy, compact layout, selection and zoom
semantics, and separation of severity from volume. Approving these designs does
not imply that backend scalability or accessibility has already been verified.
