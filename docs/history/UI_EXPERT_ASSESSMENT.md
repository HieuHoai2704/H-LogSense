# Expert UI assessment — single monitoring workspace

Date: 2026-11-03. Scope: supplied screenshot, current Jinja2 template/CSS and
documented behavior. This is a design review, not a user study or accessibility
conformance certification. No application code was changed for this assessment.

## Direction

Keep one white, compact investigation workspace. Express AI through detector
identity, scoring provenance, reference comparisons and inspectable evidence.
Retain the earlier decision to avoid generic AI marketing, chatbot panels,
decorative gradients, invented health percentages and unnecessary navigation.

## Findings and changes proposed

| Priority | Evidence / concern | Proposed revision | Acceptance condition |
|---|---|---|---|
| P0 | The current table filters do not update the independent activity matrix | Define one filter scope for dataset, time, host, service and detector | The visible selection and resulting chart/table population agree; until implemented, retain the explicit limitation |
| P0 | Score and severity appear together without immediate scoring context | Label ranking score separately from operational priority; show detector, unit, model version and evidence in details | No score is presented as probability or confirmed root cause |
| P1 | Multiple header/notice/summary/filter bands delay the main investigation content | Compact heading, one concise demo disclosure, one toolbar | At 1440x900 and 1366x768, show timeline and the beginning of the table at 100% zoom without shrinking core text |
| P1 | Body and metadata text remain very small despite stronger chart colors | Target 13–14px table text, 11–12px secondary text and 16–18px section headings | Verify actual browser size, contrast and legibility rather than estimating from the screenshot |
| P1 | Host filtering exists both in the left panel and top dropdown | Keep host/service facets on the left; put time, severity, detector and search in toolbar | No duplicate host control; active selections and clear actions remain visible |
| P1 | Time is a static badge rather than an explicit selectable scope | Design a time-range control and timezone label | Every result has an unambiguous time context; do not show a fake functioning selector |
| P1 | Heat cells communicate severity primarily through color | Design keyboard-accessible detail and visible non-color selection/severity cues | Users can identify severity and selection without relying only on hue |
| P1 | Important rows look almost identical to low-priority rows | Use restrained emphasis for Critical/High, selected row and event identity | Priorities are easy to scan without coloring entire rows red |
| P2 | Counts such as detector/host totals compete with task context | Keep event count and priority count; move secondary inventory counts into context | Every prominent count helps decide the next action |
| P2 | Demo/fixture explanations recur in several sections | Keep one clear disclosure and move technical detail to help | Never imply live data; remove duplicate text only where no behavior limitation is lost |
| P2 | Every inactive timeline bin has a visible outline | Soften inactive grid, retain strong signal cells and time guides | Active signals stand out without a noisy checkerboard |

The screenshot's right edge is cropped. This alone does not prove application
overflow; inspect the browser at defined viewport sizes before reporting a bug.

## Proposed hierarchy

```text
LogSense AI     Dataset / source     Time range + timezone
Investigation   Visible results      Configure analysis / Export (when available)
One concise demo disclosure
Search | Severity | Detector | Active filter chips | Clear
Host/service facets | Detector activity timeline
                    | Investigation table
                    | Selected-event drawer within the same workspace
```

Source selection and model configuration should open inline sections/drawers when
implemented. Do not add another dashboard page or pretend unfinished actions work.

## Table and detail content

Keep time, priority, signal summary, host/service, detector and score in the table.
Keep event ID available without giving it more emphasis than the incident summary.
Expose detection unit clearly. Put model version, feature values, observed versus
reference comparison, related raw logs and investigation status in the drawer.
Missing metadata must say unavailable. A rule detector need not claim an ML model.

## Accessibility and verification targets

- Normal text contrast at least 4.5:1; qualifying large text at least 3:1,
  with the criterion's exceptions. [W3C contrast guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
- Do not convey priority or selection by color alone.
  [W3C use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html)
- Meet 24x24 CSS-pixel pointer targets or the applicable spacing/other exception.
  Larger targets are preferable for primary actions. This is not a requirement
  that every dense timeline cell be independently 44px wide.
  [W3C target size](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)
- Test normal, filtered, selected, empty, loading and error states. Preserve
  filter state, focus and scroll position when closing details or clearing a chip.
- Verify desktop density and mobile context disclosure in an actual browser.

## Recommended sequence

1. Approve information hierarchy, filter scope and table columns.
2. Produce a compact wireframe with normal, selected and empty states.
3. Approve tokens for type, spacing, borders, priority and selection.
4. Implement the approved UI increment and verify screenshots/interactions.

Use [UI_REVIEW_PROMPT.md](UI_REVIEW_PROMPT.md) for the next design review.
