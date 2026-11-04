# Single monitoring workspace

Updated: 2026-11-03.

## Decision

Use one primary workspace at `/`, replacing the seven-item module navigation.
The product modules remain future backend responsibilities, not seven obligatory
screens. No application stack change or SPA framework is introduced.

```text
Investigation | Source | Period | Timezone | Search | Apply | Export
Demo notice / current scope / priority and detector filters
Host + service context | Linked detector timeline
                       | Table narrowed by selected cell
Selected event evidence docked on the right
```

## Current behavior

- Visible project wordmark removed from header/footer at the user's request;
  repository and documentation retain the project name.

- No placeholder Overview, Explorer, Sources, Model Lab, Alerts or Reports menu.
- Host/service links and the search form filter events through the same Flask
  route. GET parameters preserve combined filters; no new destination is opened.
- Source context stays beside both the timeline and investigation table.
- Context can be collapsed for more chart/table width; mobile starts collapsed.
- Investigation drawer and filtered CSV export remain within the workspace.
- Activity matrix and table now share one filtered scope. A selected cell narrows
  the table within that scope and is labeled explicitly. See `WORKSPACE_V2_DESIGN.md`.

## Future integration boundary

When implemented, dataset import and detector configuration should use inline
sections or drawers in this workspace. Avoid adding navigation until there is a
distinct user task that cannot be handled here. MySQL, ingestion and actual model
runs are still pending; single-screen presentation does not implement them.
