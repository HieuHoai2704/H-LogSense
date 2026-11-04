"""Streaming export shares the exact Investigation filter/run/selection scope."""

import csv, io
from flask import request, jsonify, Response, stream_with_context
from app.extensions import db
from app.models import AnomalyOutput as A
from app.services.mysql_investigation import state, base, count, row_summary
from app.services.csv_safety import safe_cell


def export_actual():
    scope = state(request.args)
    query = base(scope, selection=True)
    total = count(query)
    if total > 50000:
        return jsonify(
            error={
                "code": "export_limit",
                "message": "Narrow the scope to 50,000 anomalies.",
            }
        ), 422

    def safe(v):
        return safe_cell(v)

    def generate():
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        fields = [
            "id",
            "timestamp",
            "host",
            "service",
            "severity",
            "detector",
            "unit",
            "score",
            "run_id",
            "version_id",
            "message",
        ]
        writer.writerow(fields)
        yield buffer.getvalue()
        for row in db.session.execute(
            query.order_by(A.anchor_time.desc(), A.id.desc()).execution_options(
                yield_per=100
            )
        ):
            item = row_summary(row, scope)
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([safe(item[k]) for k in fields])
            yield buffer.getvalue()

    return Response(
        stream_with_context(generate()),
        mimetype="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="mysql-anomalies.csv"',
            "X-Result-Count": str(total),
        },
    )
