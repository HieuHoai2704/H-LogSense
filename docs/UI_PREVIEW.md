# Current UI preview

Updated: 2026-11-03.

The current implementation is described in [WORKSPACE_V2_DESIGN.md](WORKSPACE_V2_DESIGN.md).
It supersedes the earlier static, independently illustrated timeline.

- One white investigation workspace; no visible project wordmark or module menu.
- Compact source, demo period, display timezone and search controls.
- Shared host/service/priority/detector filters for timeline and events.
- Timeline cell selection narrows the table with an explicit scope banner.
- A docked right evidence panel keeps desktop context visible; mobile uses a modal.
- CSV exports the displayed records. Loading, error/retry and empty states exist.
- Data, scores, reference values and raw messages are synthetic and labeled.

`app/demo.py` aggregates fixture scope. `app/__init__.py` serves full and fragment
views. Jinja templates render structure; CSS controls layout; JavaScript handles
partial rendering, selection presentation, the panel, history and CSV export.
No ML algorithm is implemented in browser JavaScript.

Verified: eight unit/rendering checks and actual Edge interaction checks; see the
v2 design document for exact scope. This is not a complete accessibility audit.
MySQL, real file import, analysis jobs and ML evaluation remain unimplemented.

Research references: [enterprise UI patterns](research/ENTERPRISE_UI_REFERENCES.md).
