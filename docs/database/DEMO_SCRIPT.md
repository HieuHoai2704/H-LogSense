# Reproducible local demonstration

Use a fresh authorized research dataset; never reset somebody else's database.
Windows commands use the active venv Python; macOS uses its own native venv/MySQL
distribution. Setup commands and credential handling are in MYSQL_RUNBOOK.md.

1. Start the private loopback MySQL runtime, apply migrations through the migration
   role, register a BGL dataset and create a granted investigator account. Password
   entry is private; no default/demo password exists.
2. Run import with absolute limits 1000, 10000 and 100000. Show committed progress,
   raw/parsed/malformed counts and source SHA-256. Repeating the same target does
   not add source/event/label rows. Explain the difference between original bytes,
   parsed events, units and anomaly outputs.
3. Open `/?workspace=logs`, sign in, select the dataset and inspect UTC range,
   host/level/search filters. Page next/previous; show that the browser receives a
   bounded page and signed snapshot. Click a volume bin; confirm table/CSV scope.
4. Open a log's raw drawer. Show original timestamp string, authoritative Unix UTC,
   supplied Node, original label, file/line/byte provenance and redacted source
   text. Close with Escape and demonstrate preserved filters/focus.
5. Start `python -m scripts.worker` through the private environment wrapper. Queue
   a rule job, then IF. Explain temporal splits, template policy, features and
   thresholds before showing test metrics. Labels are not model features.
6. Open `/?source=db-DATASET_ID`. Show selected completed runs, Severity/Volume,
   faceted search, exact cell selection, brush/zoom and actual Evidence Drawer.
   Explain that a window contributes one anchored output, not one count per bin.
   Point out unknown source coverage and the absence of a confirmed root cause.
7. Expand Alerts in Log Explorer. Create a High-priority rule with manager
   permission, then run a new analysis. Show alert dedup/cooldown, acknowledgement,
   assignment to an authorized investigator, note history and the anomaly/run
   evidence link. No email is sent unless SMTP is explicitly configured/enabled.
8. Show numerical reports for real 10K/100K/1M ingestion/API measurements, source
   verification, actual integration/browser/axe results, and backup/restore proof.
   Explain that detector quality is still weak: window IF recall is zero in the
   measured case. Do not hide failed readiness behind passing software tests.

Actual-data screenshots are intentionally private under
`.local/database-verification/platform-browser/`. The demo fixture remains at `/`
for a reproducible public/synthetic walkthrough without private data access.

Closing discussion: macOS native execution and real external SMTP were NOT RUN;
Tkinter, supervised baseline, HTTP upload and production deployment are not
completed roadmap items. No university-grade or enterprise-readiness claim is made.
