"""The two investigation backends behind one interface.

Synthetic fixtures (``source=demo`` and the other named fixtures) and persisted datasets
(``source=db-<id>``) answer the same requests with the same response shapes. Routes call
``source_for(args)`` and never branch on the kind of source themselves.
"""

from collections.abc import Iterable, Iterator, Mapping
import csv
import io
from typing import Any, ClassVar, Protocol

from flask import Response, current_app, jsonify, stream_with_context
from flask.typing import ResponseReturnValue
from itsdangerous import URLSafeTimedSerializer
from werkzeug.datastructures import MultiDict
from werkzeug.exceptions import NotFound

from app.access import authorize_source
from app.contracts import InvestigationState, is_dataset_source
from app.extensions import db
from app.i18n import translate
from app.models import AnomalyOutput
from app.services import database_evidence, evidence as demo_evidence, investigation, mysql_investigation
from app.services.csv_safety import safe_cell
from app.services.redaction import redact

Args = MultiDict[str, str]
EXPORT_LIMIT = 50000  # exports are never silently truncated; a larger scope must be narrowed


class InvestigationSource(Protocol):
    mode: ClassVar[str]  # reported to the client as "mode"

    def check(self, args: Args) -> ResponseReturnValue | None:
        """Validate and authorize the request scope before any route runs; a response aborts it."""

    def view(self, args: Args) -> dict[str, Any]:
        """The full investigation view: scope, timeline, facets, result page and coverage."""

    def anomaly(self, anomaly_id: str, args: Args) -> ResponseReturnValue: ...
    def evidence(self, anomaly_id: str, args: Args) -> ResponseReturnValue: ...
    def raw(self, anomaly_id: str, args: Args) -> ResponseReturnValue: ...
    def related(self, anomaly_id: str, args: Args) -> ResponseReturnValue: ...
    def evidence_export(self, anomaly_id: str, args: Args) -> ResponseReturnValue: ...
    def export(self, args: Args) -> ResponseReturnValue: ...


def source_for(args: Mapping[str, Any]) -> InvestigationSource:
    return DATABASE if is_dataset_source(args.get("source", "")) else DEMO


def csv_stream(
    fields: list[str], rows: Iterable[Mapping[str, Any]], *, filename: str, **headers: str
) -> Response:
    """Stream rows as CSV; formula-like cells are neutralized and numbers kept."""

    def generate() -> Iterator[str]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerow(fields)
        yield buffer.getvalue()
        for row in rows:
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([safe_cell(row.get(field)) for field in fields])
            yield buffer.getvalue()

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', **headers},
    )


def export_too_large(message: str) -> ResponseReturnValue:
    return jsonify(error={"code": "export_limit", "message": message}), 422


class DemoSource:
    """Labelled synthetic fixtures; never detector output."""

    mode: ClassVar[str] = "demo"

    def scope(self, args: Args) -> InvestigationState:
        authorize_source(args.get("source", "demo"))
        return investigation.query(args)

    def check(self, args: Args) -> ResponseReturnValue | None:
        authorize_source(args.get("source", "demo"))
        if args.get("revision", investigation.REVISION) != investigation.REVISION:
            message = translate("Data revision changed. Refresh this scope before continuing.")
            return jsonify(error={"code": "revision_changed", "message": message}), 409
        return None

    def view(self, args: Args) -> dict[str, Any]:
        return investigation.build(self.scope(args))

    def _context(
        self, anomaly_id: str, args: Args
    ) -> tuple[dict[str, Any], InvestigationState, URLSafeTimedSerializer]:
        state = investigation.query(args)
        event = demo_evidence.find_record(anomaly_id, state["source"])
        if event is None:
            raise NotFound()
        secret = current_app.config["EVIDENCE_CURSOR_SECRET"]
        return event, state, URLSafeTimedSerializer(secret, salt="related-evidence-v1")

    def anomaly(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        source = args.get("source", "demo")
        if source not in investigation.SOURCES:
            raise investigation.QueryError("Unknown source.")
        result = investigation.detail(anomaly_id, source)
        if result is None:
            return jsonify(
                error={"code": "not_found", "message": "Anomaly is unavailable in this source."}
            ), 404
        return jsonify(event=result, revision=investigation.REVISION, mode=self.mode)

    def evidence(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        event, state, signer = self._context(anomaly_id, args)
        return jsonify(demo_evidence.evidence(event, state, args, signer))

    def raw(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        event, _, _ = self._context(anomaly_id, args)
        return jsonify(
            raw_event=demo_evidence.raw_page(event, args), revision=investigation.REVISION, mode=self.mode
        )

    def related(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        event, state, signer = self._context(anomaly_id, args)
        related = demo_evidence.related_page(event, state, args, signer)
        return jsonify(related_events=related, revision=investigation.REVISION, mode=self.mode)

    def evidence_export(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        event, state, signer = self._context(anomaly_id, args)
        result = demo_evidence.evidence(event, state, args, signer)
        result["export_scope"] = {
            "type": "current evidence page",
            "query": redact(state),
            "note": "Redacted raw and related-event pages only. Availability fields identify omitted or paginated data.",
        }
        response = jsonify(result)
        response.headers["Content-Disposition"] = (
            f'attachment; filename="synthetic-evidence-{event["id"]}.json"'
        )
        return response

    def export(self, args: Args) -> ResponseReturnValue:
        rows = investigation.export_rows(investigation.query(args))
        if len(rows) > EXPORT_LIMIT:
            return export_too_large("Narrow the scope to at most 50,000 anomalies.")
        fields = ["id", "timestamp", "host", "service", "detector", "unit", "score", "severity", "message"]
        return csv_stream(
            [*fields, "synthetic"],
            ({**row, "synthetic": True} for row in rows),
            filename="synthetic-investigation-results.csv",
            **{"X-Result-Count": str(len(rows)), "X-Data-Revision": investigation.REVISION},
        )


class DatabaseSource:
    """Persisted datasets the signed-in user is granted; bounded SQL over completed runs."""

    mode: ClassVar[str] = "database"

    def check(self, args: Args) -> ResponseReturnValue | None:
        mysql_investigation.state(args)  # authorizes the dataset; cached for the rest of the request
        return None

    def view(self, args: Args) -> dict[str, Any]:
        return mysql_investigation.build(mysql_investigation.state(args))

    def _evidence(self, anomaly_id: str, args: Args) -> dict[str, Any]:
        return database_evidence.evidence(anomaly_id, args)

    def anomaly(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        return jsonify(event=self._evidence(anomaly_id, args)["anomaly"], mode=self.mode)

    def evidence(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        return jsonify(self._evidence(anomaly_id, args))

    def raw(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        return jsonify(raw_event=self._evidence(anomaly_id, args)["raw_event"]["page"], mode=self.mode)

    def related(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        return jsonify(related_events=self._evidence(anomaly_id, args)["related_events"], mode=self.mode)

    def evidence_export(self, anomaly_id: str, args: Args) -> ResponseReturnValue:
        result = self._evidence(anomaly_id, args)
        result["export_scope"] = "Current redacted raw/related page; actual persisted evidence."
        return jsonify(result)

    def export(self, args: Args) -> ResponseReturnValue:
        scope = mysql_investigation.state(args)
        query = mysql_investigation.base(scope, selection=True)
        total = mysql_investigation.count(query)
        if total > EXPORT_LIMIT:
            return export_too_large("Narrow the scope to 50,000 anomalies.")
        ordered = query.order_by(AnomalyOutput.anchor_time.desc(), AnomalyOutput.id.desc())

        def rows() -> Iterator[dict[str, Any]]:  # runs while the response streams
            for row in db.session.execute(ordered.execution_options(yield_per=100)):
                yield mysql_investigation.row_summary(row, scope)

        fields = ["id", "timestamp", "host", "service", "severity", "detector", "unit", "score", "run_id"]
        return csv_stream(
            [*fields, "version_id", "message"],
            rows(),
            filename="mysql-anomalies.csv",
            **{"X-Result-Count": str(total)},
        )


DEMO = DemoSource()
DATABASE = DatabaseSource()
