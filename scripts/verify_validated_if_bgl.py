"""Actual BGL-to-MySQL-to-frozen-IF functional proof in a NEW owned schema.

The slice intentionally uses known frozen-model signals, not an unbiased sample
or new quality evaluation. Exact source bytes and physical origin are retained.
No model fitting/calibration or existing dataset mutation occurs.
"""

import csv
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import secrets
import time
from zipfile import ZipFile

import numpy as np
from flask_migrate import upgrade
from sqlalchemy import create_engine, select, text, func
from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import DataSource, Dataset, AnomalyOutput, DetectionUnit, LogEvent, UnitEvent
from app.domain import DetectionPrediction
from app.services.bgl_ingestion import ingest_bgl, fingerprint
from app.services.validated_if import DEFAULT_MODEL_ID, run_validated, model_card
from app.services.window_detection import EPOCH, second
from scripts.audit_if_holdout import ROOT, CURATED
from scripts.audit_isolation_forest import records
from scripts.mysql_runtime import owned_root, status
from scripts.verify_university_e2e import runtime_url

PRIVATE = Path('.local/validated_if_bgl_proof')


def main():
    if (PRIVATE / 'proof.json').exists() or (PRIVATE / 'context.json').exists():
        raise ValueError('Existing proof retained; never overwrite/reinitialize it.')
    PRIVATE.mkdir(exist_ok=True)
    runtime = owned_root('.local/university-e2e-mysql')
    assert status(runtime)['port'] == 13307
    study = ROOT / DEFAULT_MODEL_ID
    card = model_card()
    with np.load(study / 'test-predictions.npz') as predictions:
        scores = predictions['selected_if_scores']
    selected = []
    for unit, score in zip(records(study / 'test.jsonl'), scores):
        if unit['count'] == 1 and score < card['threshold']:
            selected.append((unit, float(score)))
        if len(selected) == 20:
            break
    if not selected:
        raise ValueError('No complete singleton signal available; no synthetic replacement.')
    wanted = {u['sample_ids'][0] for u, _ in selected}
    raw_lines = []
    origin = []
    with ZipFile('data/raw/BGL.zip') as archive, archive.open('BGL.log') as stream:
        for number, raw in enumerate(stream, 1):
            if number in wanted:
                raw_lines.append(raw)
                origin.append({'original_physical_line': number,
                               'sha256': hashlib.sha256(raw).hexdigest()})
            if len(raw_lines) == len(wanted):
                break
    assert len(raw_lines) == len(wanted)
    zip_path = PRIVATE / 'actual-july-known-signal-slice.zip'
    with ZipFile(zip_path, 'w') as archive:
        archive.writestr('BGL.log', b''.join(raw_lines))
        archive.writestr('README.md', 'Known frozen-model signal slice for functional verification only. Not a random sample or new quality evaluation.\n')
    (PRIVATE / 'origin-private.json').write_text(json.dumps(origin, indent=2), encoding='utf-8')
    schema = 'logsense_bench_if_' + secrets.token_hex(6)
    admin = create_engine(runtime_url(runtime, 'root', 'mysql'), hide_parameters=True)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE `{schema}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_cs'))
        connection.execute(text(f"GRANT SELECT,INSERT,UPDATE ON `{schema}`.* TO 'logsense_app'@'localhost'"))
        connection.execute(text(f"GRANT SELECT,INSERT,UPDATE,CREATE,ALTER,INDEX,REFERENCES ON `{schema}`.* TO 'logsense_migrator'@'localhost'"))
    admin.dispose()
    secret = secrets.token_hex(32)
    (PRIVATE / 'context.json').write_text(json.dumps({'schema': schema, 'source_sha256': fingerprint(zip_path)}), encoding='utf-8')
    app = create_app({'SQLALCHEMY_DATABASE_URI': runtime_url(runtime, 'migrate', schema), 'SECRET_KEY': secret})
    with app.app_context():
        upgrade()
        db.engine.dispose()
    token = secrets.token_hex(32)
    app = create_app({'SQLALCHEMY_DATABASE_URI': runtime_url(runtime, 'app', schema),
                      'SECRET_KEY': secret, 'DATABASE_READ_TOKEN': token})
    started = time.perf_counter()
    with app.app_context():
        with Session(db.engine) as session, session.begin():
            source = DataSource(source_key='verified-loghub-slice-' + secrets.token_hex(6), name='Actual BGL known-signal functional proof')
            session.add(source)
            session.flush()
            dataset = Dataset(source_id=source.id, dataset_key='july-functional-proof',
                              name='Actual BGL curated signal slice; not quality evaluation', data_mode='real')
            session.add(dataset)
            session.flush()
            dataset_id = dataset.id
        app.config['DATABASE_ALLOWED_DATASETS'] = (dataset_id,)
        begin = time.perf_counter()
        imported = ingest_bgl(db.engine, dataset_id, zip_path)
        import_seconds = time.perf_counter() - begin
        begin = time.perf_counter()
        result = run_validated(db.engine, dataset_id, 'actual-bgl-validated-proof',
                               {'detector': 'isolation_forest', 'model_id': DEFAULT_MODEL_ID})
        inference_seconds = time.perf_counter() - begin
        expected = {(u['host'], u['bucket']): score for u, score in selected}
        with Session(db.engine) as session:
            pairs = session.execute(select(DetectionPrediction, DetectionUnit).join(DetectionUnit,
                (DetectionUnit.id == DetectionPrediction.unit_id) & (DetectionUnit.dataset_id == DetectionPrediction.dataset_id)).where(
                    DetectionPrediction.dataset_id == dataset_id, DetectionPrediction.run_id == result['run_id'])).all()
            assert len(pairs) == len(selected)
            for prediction, unit in pairs:
                assert prediction.score == expected[(unit.host, second(unit.start_time) // 300)]
                assert prediction.predicted
            output_count = session.scalar(select(func.count()).select_from(AnomalyOutput).where(AnomalyOutput.dataset_id == dataset_id))
            ids = set(session.scalars(select(LogEvent.id).where(LogEvent.dataset_id == dataset_id)))
            members = set(session.scalars(select(UnitEvent.event_id).where(UnitEvent.dataset_id == dataset_id)))
            assert ids == members and output_count == len(selected)
            first = min(unit.start_time for _, unit in pairs)
            end = max(unit.end_time for _, unit in pairs)
        client = app.test_client()
        headers = {'Authorization': 'Bearer ' + token}
        params = {'source': 'db-' + str(dataset_id), 'start_time': first.isoformat(), 'end_time': end.isoformat()}
        response = client.get('/api/v1/investigation', query_string=params, headers=headers)
        assert response.status_code == 200
        actual = response.json
        assert actual['scope_count'] == actual['result_count'] == output_count
        assert sum(cell['count'] for cell in actual['timeline']['overall']) == output_count
        evidence = client.get('/api/v1/anomalies/' + actual['events'][0]['id'] + '/evidence', query_string=params, headers=headers)
        assert evidence.status_code == 200
        material = evidence.json
        assert material['raw_event']['provenance']['original_log_available']
        assert material['raw_event']['page']['synthetic'] is False
        assert material['detector_evidence']['model_version'] == card['version']
        assert material['summary']['root_cause'] is None
        csv_response = client.get('/api/v1/anomalies/export', query_string=params, headers=headers)
        assert csv_response.status_code == 200
        csv_rows = list(csv.DictReader(io.StringIO(csv_response.text)))
        assert len(csv_rows) == output_count == int(csv_response.headers['X-Result-Count'])
        default = client.get('/api/v1/investigation', query_string={'source': params['source']}, headers=headers)
        report = {'status': 'PASS', 'corpus': 'Actual Loghub BGL July known-signal curated functional slice',
            'selection_policy': '20 complete singleton windows already flagged by the frozen model; no ground-truth selection; NOT an unbiased quality estimate',
            'quality_metrics': 'Not reported on this selected functional fixture; independent July benchmark remains unchanged',
            'schema': schema, 'dataset_id': dataset_id, 'model_id': DEFAULT_MODEL_ID,
            'model_version': card['version'], 'inference_start_utc': card['inference_start_utc'],
            'import_result': imported, 'import_seconds': import_seconds,
            'inference_seconds': inference_seconds, 'wall_seconds': time.perf_counter() - started,
            'actual_db_predictions': len(pairs), 'actual_db_outputs': output_count,
            'database_scores_equal_frozen_original_scores_exactly': True,
            'membership_uses_actual_dataset_event_ids': True,
            'timeline_result_csv_count': output_count, 'evidence_actual_raw_provenance': True,
            'default_range_count': default.json.get('scope_count') if default.status_code == 200 else None,
            'default_range_matches_all_outputs': default.status_code == 200 and default.json['scope_count'] == output_count,
            'source_slice_sha256': hashlib.sha256(b''.join(raw_lines)).hexdigest(),
            'derived_archive_sha256': fingerprint(zip_path), 'source_origin_map_sha256': fingerprint(PRIVATE / 'origin-private.json'),
            'no_model_or_threshold_changes': True, 'source_time_scope': {'start': first.isoformat(), 'end': end.isoformat()},
            'existing_datasets_unchanged': True, 'no_push_or_merge': True}
        report['inference_pipeline_status'] = 'PASS'
        report['default_range_status'] = 'PASS' if report['default_range_matches_all_outputs'] else 'FAIL'
        if not report['default_range_matches_all_outputs']:
            report['status'] = 'PARTIAL'
        db.engine.dispose()
    (PRIVATE / 'proof.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    (CURATED / 'actual-db-profile-proof.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


def verify_existing():
    context = json.loads((PRIVATE / 'context.json').read_text())
    original = json.loads((PRIVATE / 'proof.json').read_text())
    previous = PRIVATE / 'initial-proof.json'
    if not previous.exists():
        previous.write_bytes((PRIVATE / 'proof.json').read_bytes())
    runtime = owned_root('.local/university-e2e-mysql')
    assert status(runtime)['port'] == 13307
    token = secrets.token_hex(32)
    dataset_id = original['dataset_id']
    app = create_app({'SQLALCHEMY_DATABASE_URI': runtime_url(runtime, 'app', context['schema']),
        'SECRET_KEY': secrets.token_hex(32), 'DATABASE_READ_TOKEN': token,
        'DATABASE_ALLOWED_DATASETS': (dataset_id,)})
    with app.app_context():
        client = app.test_client()
        headers = {'Authorization': 'Bearer ' + token}
        params = {'source': 'db-' + str(dataset_id)}
        response = client.get('/api/v1/investigation', query_string=params, headers=headers)
        assert response.status_code == 200
        with Session(db.engine) as session:
            expected = session.scalar(select(func.count()).select_from(AnomalyOutput).where(AnomalyOutput.dataset_id == dataset_id))
        assert response.json['scope_count'] == response.json['result_count'] == expected
        csv_response = client.get('/api/v1/anomalies/export', query_string=params, headers=headers)
        assert csv_response.status_code == 200
        assert len(list(csv.DictReader(io.StringIO(csv_response.text)))) == expected
        original.update(status='PASS', initial_default_range_count=original.get('initial_default_range_count', original.get('default_range_count')),
            default_range_count=expected, default_range_status='PASS', default_range_matches_all_outputs=True,
            inference_pipeline_status='PASS', default_csv_count=expected,
            default_range_fix='Default time extent includes completed anomaly anchors; explicit user ranges unchanged',
            recheck_policy='Read-only API/SQL/CSV recheck on existing persisted records; model and threshold not rerun or changed')
        db.engine.dispose()
    (PRIVATE / 'proof.json').write_text(json.dumps(original, indent=2) + '\n', encoding='utf-8')
    (CURATED / 'actual-db-profile-proof.json').write_text(json.dumps(original, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'default_range_count': expected,
                      'model_and_threshold_unchanged': True}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-existing', action='store_true')
    args = parser.parse_args()
    verify_existing() if args.verify_existing else main()
