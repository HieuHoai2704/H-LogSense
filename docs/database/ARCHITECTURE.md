# Implemented architecture

The application remains a modular Flask monolith. No React/Vue rewrite, second
backend, OS service, Redis or message broker was introduced.

```mermaid
flowchart LR
    ZIP[Immutable operator-supplied BGL ZIP] --> Parser[Streaming parser]
    Parser --> Import[Atomic import batches and checkpoint]
    Import --> Raw[Raw bytes and provenance]
    Import --> Events[Parsed UTC events]
    Import --> Labels[Original BGL labels]
    Events --> Features[Label-blind host-window features]
    Features --> Worker[Separate Python analysis worker]
    Worker --> Predictions[Versioned runs, predictions and flagged outputs]
    Predictions --> Evaluation[Post-inference test evaluation]
    Labels --> Evaluation
    Predictions --> Decisions[Rule matches and cooldown decisions]
    Decisions --> Incidents[Alerts, assignment, notes and audit]
    Incidents --> Outbox[Private opt-in SMTP outbox]
    Events --> API[Scoped Flask APIs and SQL aggregation]
    Predictions --> API
    Evaluation --> API
    Incidents --> API
    Auth[Session authentication, roles and dataset grants] --> API
    API --> Workspace[Existing Investigation V2 and bounded Log Explorer]
```

`app/extensions.py` owns shared SQLAlchemy/Migrate instances. The factory imports
metadata, optionally initializes the MySQL engine, and registers Blueprints.
No startup DDL or automatic database fallback exists. SQLAlchemy sessions are
request-scoped; batch services use explicit Session/transaction contexts.

`models.py` contains the log/detector foundation; `domain.py` contains identity,
prediction/evaluation and incidents. Composite dataset FKs prevent cross-dataset
references in the database. Services implement concrete workflows; templates do
not issue SQL or decide authorization.

The public demo provider remains bounded and explicitly synthetic. The MySQL
adapter uses SQL COUNT/GROUP BY, bounded result/facet/detector pages and immutable
run selection. Raw supporting logs load only on demand. The browser cancels stale
requests and preserves investigation filters when drawers close.

V3 is still broader than the implementation: immutable multi-run publication
manifests, tenant identity federation, retention enforcement, summary/columnar
storage, distributed scheduling and real-time ingestion are not claimed. Current
log snapshots pin an append-only event ID watermark; anomaly snapshots pin one
completed run per logical detector. Unknown source-time completeness is explicit.
