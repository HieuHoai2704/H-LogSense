"""Read-only demo APIs; real ingestion and authorization are not connected."""
import csv
import io
import time

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from itsdangerous import URLSafeTimedSerializer
from werkzeug.exceptions import NotFound

from app.access import authorize_source
from app.presentation import payload
from app.services.evidence import evidence, find_record, raw_page, related_page
from app.services.redaction import redact
from app.services.investigation import (QueryError, REVISION, SOURCES, build, detail,
                                        export_rows, query)

api = Blueprint('anomalies', __name__, url_prefix='/api/v1')


@api.errorhandler(QueryError)
def invalid_query(error):
    return jsonify(error={'code': 'invalid_query', 'message': str(error)}), 400


@api.before_request
def validate_revision():
    authorize_source(request.args.get('source', 'demo'))
    if request.args.get('revision', REVISION) != REVISION:
        return jsonify(error={'code': 'revision_changed', 'message': 'Data revision changed. Refresh this scope before continuing.'}), 409


@api.after_request
def no_cached_scope(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@api.errorhandler(NotFound)
def missing_evidence(error):
    return jsonify(error={'code': 'not_found', 'message': 'Anomaly is unavailable in this source.'}), 404


def evidence_context(anomaly_id):
    state = query(request.args)
    event = find_record(anomaly_id, state['source'])
    if event is None:
        raise NotFound()
    signer = URLSafeTimedSerializer(current_app.config['EVIDENCE_CURSOR_SECRET'], salt='related-evidence-v1')
    return event, state, signer


@api.get('/anomalies/<anomaly_id>/evidence')
def anomaly_evidence(anomaly_id):
    event, state, signer = evidence_context(anomaly_id)
    return jsonify(evidence(event, state, request.args, signer))


@api.get('/anomalies/<anomaly_id>/evidence/raw')
def raw_evidence(anomaly_id):
    event, state, _ = evidence_context(anomaly_id)
    return jsonify(raw_event=raw_page(event, request.args), revision=REVISION, mode='demo')


@api.get('/anomalies/<anomaly_id>/related')
def related_evidence(anomaly_id):
    event, state, signer = evidence_context(anomaly_id)
    return jsonify(related_events=related_page(event, state, request.args, signer), revision=REVISION, mode='demo')


@api.get('/anomalies/<anomaly_id>/evidence/export')
def export_evidence(anomaly_id):
    event, state, signer = evidence_context(anomaly_id)
    result = evidence(event, state, request.args, signer)
    result['export_scope'] = {'type': 'current evidence page', 'query': redact(state),
                              'note': 'Redacted raw and related-event pages only. Availability fields identify omitted or paginated data.'}
    response = jsonify(result)
    response.headers['Content-Disposition'] = f'attachment; filename="synthetic-evidence-{event["id"]}.json"'
    return response


@api.get('/investigation')
def investigation():
    started = time.perf_counter()
    result = payload(build(query(request.args)))
    result['query_ms'] = round((time.perf_counter()-started)*1000, 2)
    return jsonify(result)


@api.get('/anomalies/timeline')
def timeline():
    view = build(query(request.args))
    return jsonify({key: view[key] for key in ['state', 'revision', 'mode', 'scope_count', 'high_critical_count', 'timeline', 'coverage', 'row_count', 'row_page_count']})


@api.get('/anomalies')
def anomalies():
    view = build(query(request.args))
    return jsonify({key: view[key] for key in ['state', 'revision', 'mode', 'scope_count', 'result_count', 'events', 'page_count']})


@api.get('/anomalies/export')
def export():
    state = query(request.args)
    rows = export_rows(state)
    # Demo adapter is bounded. A SQL repository must stream its snapshot rather
    # than collect arbitrary result rows. Never silently truncate an export.
    if len(rows) > 50000:
        return jsonify(error={'code': 'export_limit', 'message': 'Narrow the scope to at most 50,000 anomalies.'}), 422
    fields = ['id', 'timestamp', 'host', 'service', 'detector', 'unit', 'score', 'severity', 'message', 'synthetic']

    def safe(value):
        value = str(value if value is not None else '')
        return "'"+value if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value

    def generate():
        buffer = io.StringIO(newline='')
        writer = csv.writer(buffer)
        writer.writerow(fields)
        yield buffer.getvalue()
        for event in rows:
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow([safe(True if field == 'synthetic' else event.get(field)) for field in fields])
            yield buffer.getvalue()

    return Response(stream_with_context(generate()), mimetype='text/csv', headers={
        'Content-Disposition': 'attachment; filename="synthetic-investigation-results.csv"',
        'X-Result-Count': str(len(rows)), 'X-Data-Revision': REVISION})


@api.get('/anomalies/<anomaly_id>')
def anomaly_detail(anomaly_id):
    source = request.args.get('source', 'demo')
    if source not in SOURCES:
        raise QueryError('Unknown source.')
    result = detail(anomaly_id, source)
    if result is None:
        return jsonify(error={'code': 'not_found', 'message': 'Anomaly is unavailable in this source.'}), 404
    return jsonify(event=result, revision=REVISION, mode='demo')
