# Design artifact verification

Historical design-stage results. Subsequent application implementation and its
verification are recorded in `../INVESTIGATION_V2_IMPLEMENTATION.md`.

Date: 2026-11-03. Scope: **audit + static design artifacts only**.

## Results

| Check | Observed result | Limit |
|---|---|---|
| Git status | `fatal: not a git repository` | Cannot identify uncommitted changes or produce a git diff |
| Existing unit/integration suite | `python -m unittest discover -s tests -q`: 8 tests passed, 0 failed, 0.045s | Existing fixture behavior, not proposed zoom/coverage/SQL behavior |
| SVG rasterization | 5 sheets rendered with Playwright / headless Microsoft Edge | Static artifact rendering, not application UI smoke tests |
| Canvas boundaries | 0 text elements outside each of 5 SVG canvases | Bounding-box check, not a usability study |
| Text intersection | 0 overlaps in desktop, compact, selection and state sheets | Evidence overlay deliberately covers underlying workspace; reviewed visually instead |
| Manual visual inspection | Desktop, compact, selection, evidence and state images inspected; volume token and export-button clearance corrected | No functional interaction validation of these static wireframes |
| Fixture correspondence | Four detector lanes, six anomaly anchors and three High/Critical match `app/demo.py` | Diagram assumes one record per occupied fixture bin; volume examples are separately constructed |
| Text token contrast | All 13 measured text/background pairs >=4.5:1; minimum 4.846:1 | Token pairs only; not full app accessibility conformance |
| Boundary/selection token contrast | Both tested against white >=3:1 | Does not cover every rendered state/background |
| Source integrity | Seven audited application/test files match their pre-design SHA256 hashes | See `source-integrity.json`; no claim about Git-tracked status |
| Backend/scale | Not benchmarked; no MySQL query measurements | No p95, throughput or million-event capability claim |

## Artifacts

- `TIMELINE_V2_UI_SPEC.md`: all ten requested design deliverables, including
  source audit, priority table, component tree, interaction matrix, tokens,
  state behavior, accessibility, change inventory and execution gates.
- `timeline-v2-desktop.svg/png`: 1440px overview.
- `timeline-v2-compact.svg/png`: 1024px overview.
- `timeline-v2-selection.svg/png`: selected cell and linked single result.
- `timeline-v2-evidence.svg/png`: 1440px evidence overlay preserving context.
- `timeline-v2-states.svg/png`: exclusive severity/volume encodings, coverage,
  request failure and empty states, all explicitly constructed examples.
- `token-contrast.json`, `wireframe-render-check.json`, `source-integrity.json`:
  supporting measured checks.
- `generate_wireframes.py`: reproducible native SVG generator, **not app code**.

Rebuild SVGs using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe docs/ui/generate_wireframes.py
```

PNG previews were captured from those SVG files at their native width using
Playwright with `chromium.launch(channel="msedge", headless=True)` and
`page.locator("svg").screenshot(...)`. These local authoring utilities do not
introduce a Playwright runtime dependency into the Flask application.

Contrast measurements use the sRGB relative-luminance formula. The targets are
informed by [WCAG text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
Final UI still needs independent keyboard, focus, color/state, screen reader,
target-size and responsive testing after approved implementation.

## Approval boundary

No application template, stylesheet, JavaScript, route, fixture or test was
modified. No dependencies installed, server deployed, Git repository initialized
or changes pushed. Production implementation remains pending design approval.
