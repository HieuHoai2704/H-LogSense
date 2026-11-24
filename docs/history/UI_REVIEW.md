# UI review — removing generic AI presentation

Date: 2026-11-03. Assessment concerns the local prototype and supplied reference,
not an exhaustive survey of all interfaces.

| Previous choice | Assessment | Implemented revision |
|---|---|---|
| Promotional eyebrow and slogans | Marketing language in an operational task | Removed; functional page description |
| Four pastel KPI cards | Repetitive decoration | Compact counts computed from the fixture |
| Invented 24,860 event volume | No corresponding input | Removed; six actual synthetic records |
| Sidebar promotion and star | Template-style advertising block | Removed |
| User avatar without authentication | Implies an unavailable account feature | Removed |
| Fake workspace dropdown | Suggests unavailable behavior | Plain local project label |
| Arbitrary host influence bars | Ranking lacks evidence | Actual counts without bars |
| Repeated badges and score bars | Redundant visual encoding | Numeric scores and plain severity labels |
| Pulse brand mark | Weak project-specific identity | Terminal-style `L_` mark |
| Rounded surfaces everywhere | Excessive card styling | White canvas and restrained rectangular sections |

Keep useful conventions: search, filters, navigation, severity colors, timestamp
columns and an investigation dialog. Distinct identity should support the actual
workflow without making familiar controls harder to use.

## Verification

Flask checks confirmed removed slogans, invented volume, avatars, KPI-card markup
and host bar markup are absent. Edge checks passed for drawer/Escape, filtering,
CSV export, empty state and mobile navigation. Downloaded datasets are not yet
connected to this synthetic preview.
