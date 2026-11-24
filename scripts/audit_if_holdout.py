"""Preregistered later BGL holdout, label-blind streaming features and IF audit.

Offline experiment only: MySQL application data/models and UI are not changed.
An external event sort handles source lines that are not chronological. Raw
messages, references, feature caches and model binaries remain under .local.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import heapq
import itertools
import json
import math
import os
from pathlib import Path
import platform
import time
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

import joblib
import numpy as np
import psutil
import sklearn
from sklearn.ensemble import IsolationForest

from app.parsers.bgl import parse_line
from app.services.detector_calibration import reservoir_sample, choose_threshold, binary_metrics
from app.services.window_detection import aggregate_windows, EPOCH, FEATURE_NAMES
from app.services.window_features import TrainReference
from scripts.audit_isolation_forest import digest, write_json, read_json, records

ROOT = Path('.local/if_new_holdout')
CURATED = Path('docs/ml/measurements/if-july-holdout-2026-11-04')
EXPOSED_TEST_END = int(datetime(2005, 6, 25, 18, 50, tzinfo=timezone.utc).timestamp())
STUDY_ID = 'f3e5a88403ab48fb84ea36904214e867'
GRID = [
    {'id': 'base-100-256', 'features': 'base', 'n_estimators': 100, 'max_samples': 256, 'seed': 42},
    {'id': 'context-100-256', 'features': 'context', 'n_estimators': 100, 'max_samples': 256, 'seed': 42},
    {'id': 'base-200-1024', 'features': 'base', 'n_estimators': 200, 'max_samples': 1024, 'seed': 42},
    {'id': 'context-200-1024', 'features': 'context', 'n_estimators': 200, 'max_samples': 1024, 'seed': 42},
]


def epoch(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.utcoffset() is None:
        raise ValueError('Explicit UTC offset required.')
    return int(value.timestamp())


def protocol(study_id, archive):
    bounds = {key: epoch(value) for key, value in {
        'train_start': '2005-07-01T00:00:00Z', 'train_end': '2005-07-14T00:00:00Z',
        'validation_end': '2005-07-21T00:00:00Z', 'test_end': '2005-07-28T00:00:00Z',
    }.items()}
    validate_bounds(bounds, 300)
    with ZipFile(archive) as zipped:
        member = zipped.getinfo('BGL.log')
    return {
        'study_id': study_id, 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'archive_sha256': digest(archive), 'member': 'BGL.log', 'member_bytes': member.file_size,
        'member_crc32': member.CRC, 'seconds': 300, 'splits': bounds,
        'split_utc': {key: datetime.fromtimestamp(value, timezone.utc).isoformat() for key, value in bounds.items()},
        'exposed_old_test_end_utc': '2005-06-25T18:50:00Z',
        'candidate_grid': GRID, 'reservoir_limit': 20000, 'reservoir_seed': 42,
        'legacy_training': 'first 20000 chronological training units',
        'legacy_if': '100 trees, max_samples256, seed42, validation first20000 native-score p01',
        'legacy_rule': 'first20000 training counts p99, strict greater comparison',
        'objective': 'validation maximum F1 subject to empirical FPR<=0.01; ties AP, lower FPR, candidate ID',
        'max_fpr': 0.01, 'minimum_validation_each_class': 20,
        'quantile_sensitivity': [0.001, 0.005, 0.01, 0.02, 0.05], 'seed_sensitivity': [17, 73],
        'native_score_direction': 'lower', 'native_comparison': '<',
        'label_use': 'no labels in references/features/fitting; validation labels ONLY for calibration/selection; test labels after selection freeze',
        'unit': 'nonempty completed observed host-window UTC [start,end); any original BGL alert among ALL observed events',
        'coverage': 'unknown source time completeness; no zero-host windows invented',
        'external_sort': {'rows_per_chunk': 50000, 'key': ['epoch_seconds', 'physical_source_line'], 'merge': 'heapq.merge'},
        'maximum_units_per_phase': 1000000,
        'software': {'python': platform.python_version(), 'sklearn': sklearn.__version__,
                     'numpy': np.__version__, 'platform': platform.platform()},
        'test_policy': 'one evaluation of frozen legacy rule/IF and selected IF on identical new test; no test-driven reselection',
    }


def validate_bounds(bounds, seconds):
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds <= 0:
        raise ValueError('Positive whole-second resolution required.')
    values = [bounds[k] for k in ('train_start', 'train_end', 'validation_end', 'test_end')]
    if any(not isinstance(x, int) or isinstance(x, bool) or x % seconds for x in values):
        raise ValueError('UTC whole-window boundaries required.')
    if values != sorted(set(values)) or values[0] <= EXPOSED_TEST_END:
        raise ValueError('Fresh periods must start after the already exposed June test.')


def phase_for(stamp, bounds):
    if bounds['train_start'] <= stamp < bounds['train_end']:
        return 'train'
    if bounds['train_end'] <= stamp < bounds['validation_end']:
        return 'validation'
    if bounds['validation_end'] <= stamp < bounds['test_end']:
        return 'test'
    return None


def raw_epoch(raw):
    # The second source token is the Unix timestamp. No ground-truth value is
    # inspected to choose or discard a date range.
    fields = raw.split(maxsplit=2)
    if len(fields) < 3:
        return None
    try:
        return int(fields[1])
    except ValueError:
        return None


def event_from_record(record):
    return SimpleNamespace(id=record[1], timestamp=datetime.fromtimestamp(record[0], timezone.utc),
                           host=record[2], severity=record[3], message=record[4])


def external_chunks(archive, directory, registration):
    chunk_root = directory / 'events'
    chunk_root.mkdir()
    pending, chunks = [], []
    counts = dict.fromkeys(('train', 'validation', 'test'), 0)
    missing_host = dict.fromkeys(counts, 0)
    malformed, physical_lines, offset = 0, 0, 0
    selected_source = hashlib.sha256()
    full_source = hashlib.sha256()
    minimum = maximum = None
    previous = None
    source_time_reversals = 0

    def flush():
        if not pending:
            return
        pending.sort(key=lambda r: (r[0], r[1]))
        path = chunk_root / (f'{len(chunks):04d}.jsonl')
        with path.open('x', encoding='utf-8', newline='\n') as output:
            for row in pending:
                output.write(json.dumps(row, separators=(',', ':')) + '\n')
        chunks.append(path)
        pending.clear()

    with ZipFile(archive) as zipped, zipped.open('BGL.log') as stream:
        for physical_lines, raw in enumerate(stream, 1):
            full_source.update(raw)
            stamp = raw_epoch(raw)
            if stamp is not None:
                minimum = stamp if minimum is None else min(minimum, stamp)
                maximum = stamp if maximum is None else max(maximum, stamp)
                if previous is not None and stamp < previous:
                    source_time_reversals += 1
                previous = stamp
            phase = None if stamp is None else phase_for(stamp, registration['splits'])
            if phase is not None:
                selected_source.update(raw)
                parsed = parse_line(raw, physical_lines, offset)
                if parsed.error:
                    malformed += 1
                elif parsed.host is None:
                    missing_host[phase] += 1
                else:
                    # Original label, raw line prefix, absolute time, source ID
                    # and host ID are not included in the model feature vector.
                    counts[phase] += 1
                    pending.append([stamp, physical_lines, parsed.host,
                                    parsed.attributes['level'], parsed.message, offset])
                    if len(pending) == registration['external_sort']['rows_per_chunk']:
                        flush()
            offset += len(raw)
            if physical_lines % 1000000 == 0:
                print(json.dumps({'source_lines_scanned': physical_lines,
                                  'selected_events_unlabeled': sum(counts.values())}), flush=True)
    flush()
    return chunks, {'physical_source_lines': physical_lines, 'raw_member_bytes': offset,
                    'full_member_sha256': full_source.hexdigest(),
                    'selected_raw_sha256': selected_source.hexdigest(), 'phase_events': counts,
                    'missing_host_events': missing_host, 'malformed_selected_events': malformed,
                    'source_epoch_min': minimum, 'source_epoch_max': maximum,
                    'source_time_reversals': source_time_reversals,
                    'external_chunks': len(chunks)}


def sorted_events(paths):
    streams = [records(path) for path in paths]
    previous = None
    for row in heapq.merge(*streams, key=lambda r: (r[0], r[1])):
        key = row[0], row[1]
        if previous is not None and key <= previous:
            raise ValueError('Duplicate/out-of-order source reference in external merge.')
        previous = key
        yield event_from_record(row)


def prepare(study_id, archive):
    directory = ROOT / study_id
    directory.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    registration = protocol(study_id, archive)
    # Exclusive protocol is durable BEFORE source extraction or any label use.
    write_json(directory / 'protocol.json', registration)
    chunks, metadata = external_chunks(archive, directory, registration)
    counts = dict.fromkeys(('train', 'validation', 'test'), 0)
    singletons = dict.fromkeys(counts, 0)
    outputs = {phase: (directory / (phase + '.jsonl')).open('x', encoding='utf-8', newline='\n') for phase in counts}
    try:
        for unit in aggregate_windows(sorted_events(chunks), registration['seconds'], include_templates=True):
            phase = phase_for(unit['bucket'] * registration['seconds'], registration['splits'])
            if phase is None:
                raise ValueError('Unit is outside registered scope.')
            counts[phase] += 1
            if counts[phase] > registration['maximum_units_per_phase']:
                raise ValueError('Registered bounded unit budget exceeded; test labels remain unopened.')
            singletons[phase] += unit['count'] == 1
            outputs[phase].write(json.dumps(unit, separators=(',', ':')) + '\n')
    finally:
        for stream in outputs.values():
            stream.close()
    if not all(counts.values()):
        raise ValueError('Registered time periods do not have observed data; no test fallback.')
    metadata.update(protocol_sha256=digest(directory / 'protocol.json'), unit_counts=counts,
                    singleton_units=singletons, cache={p: {'key': p + '.jsonl',
                    'sha256': digest(directory / (p + '.jsonl')), 'count': counts[p]} for p in counts},
                    prepare_seconds=time.perf_counter() - started)
    write_json(directory / 'manifest.json', dict(registration, **metadata))
    print(json.dumps({'prepared': study_id, 'phase_units': counts, 'phase_events': metadata['phase_events'],
                      'prepare_seconds': metadata['prepare_seconds']}), flush=True)


def checked(directory, archive):
    manifest = read_json(directory / 'manifest.json')
    registration = read_json(directory / 'protocol.json')
    if digest(directory / 'protocol.json') != manifest['protocol_sha256']:
        raise ValueError('Preregistration checksum changed.')
    if any(manifest.get(key) != value for key, value in registration.items()):
        raise ValueError('Manifest differs from preregistered policy.')
    if digest(archive) != manifest['archive_sha256']:
        raise ValueError('Source archive changed.')
    validate_bounds(manifest['splits'], manifest['seconds'])
    return manifest


def checked_cache(directory, manifest, phase):
    path = directory / (phase + '.jsonl')
    if digest(path) != manifest['cache'][phase]['sha256']:
        raise ValueError('Feature cache changed.')
    return path


def labels_for(archive, manifest, phase, path):
    if phase not in {'validation', 'test'}:
        raise ValueError('No train-label query is part of model fitting.')
    if phase == 'test' and not path.parent.joinpath('test-access.json').exists():
        raise ValueError('Test access requires a frozen selection marker.')
    known = {}
    offset = 0
    with ZipFile(archive) as zipped, zipped.open('BGL.log') as stream:
        for line, raw in enumerate(stream, 1):
            stamp = raw_epoch(raw)
            if stamp is not None and phase_for(stamp, manifest['splits']) == phase:
                parsed = parse_line(raw, line, offset)
                if not parsed.error and parsed.host is not None:
                    key = parsed.host, stamp // manifest['seconds']
                    old_count, old_label = known.get(key, (0, 0))
                    known[key] = old_count + 1, max(old_label, int(parsed.label != '-'))
            offset += len(raw)
    truth = np.empty(manifest['cache'][phase]['count'], dtype=np.int8)
    index = 0
    for unit in records(path):
        count, label = known.get((unit['host'], unit['bucket']), (0, None))
        if count != unit['count'] or label is None:
            raise ValueError('Incomplete window ground truth; no silent cohort exclusions.')
        truth[index] = label
        index += 1
    if index != len(truth):
        raise ValueError('Window count changed.')
    return truth


def matrix(source, count, reference=None):
    rows = records(source) if isinstance(source, Path) else iter(source)
    width = len(FEATURE_NAMES) if reference is None else len(reference.names)
    result = np.empty((count, width), dtype=np.float64)
    index = 0
    for row in rows:
        if index >= count:
            raise ValueError('Feature count exceeds frozen manifest.')
        result[index] = row['features'] if reference is None else reference.transform(row)
        index += 1
    if index != count or not np.all(np.isfinite(result)):
        raise ValueError('Feature matrix count/values invalid.')
    return result


def fit(spec, values):
    return IsolationForest(n_estimators=spec['n_estimators'], max_samples=min(spec['max_samples'], len(values)),
                           contamination='auto', random_state=spec['seed'], n_jobs=1).fit(values)


def validate(study_id, archive):
    directory = ROOT / study_id
    if (directory / 'selection.json').exists() or (directory / 'test-access.json').exists():
        raise ValueError('Selection frozen/test exposed; no reselection.')
    started = time.perf_counter()
    manifest = checked(directory, archive)
    train = checked_cache(directory, manifest, 'train')
    validation = checked_cache(directory, manifest, 'validation')
    truth = labels_for(archive, manifest, 'validation', validation)
    if min(int(truth.sum()), len(truth) - int(truth.sum())) < manifest['minimum_validation_each_class']:
        raise ValueError('Insufficient validation classes; do not inspect test labels.')
    reference = TrainReference.fit(records(train))
    sample = reservoir_sample(records(train), limit=manifest['reservoir_limit'], seed=manifest['reservoir_seed'])
    if len(sample) < 16:
        raise ValueError('Insufficient train units.')
    first = list(itertools.islice(records(train), 20000))
    legacy_model = fit(manifest['candidate_grid'][0], matrix(first, len(first)))
    base_validation = matrix(validation, len(truth))
    legacy_threshold = float(np.quantile(legacy_model.score_samples(base_validation[:20000]), 0.01))
    legacy_rule_threshold = float(np.quantile(np.expm1(matrix(first, len(first))[:, 0]), 0.99))
    joblib.dump({'model': legacy_model, 'if_threshold': legacy_threshold,
                 'rule_threshold': legacy_rule_threshold}, directory / 'baselines.joblib')
    candidates, fitted, sensitivity = [], {}, []
    for spec in manifest['candidate_grid']:
        ref = reference if spec['features'] == 'context' else None
        values = matrix(sample, len(sample), ref)
        val_values = base_validation if ref is None else matrix(validation, len(truth), ref)
        begin = time.perf_counter()
        model = fit(spec, values)
        scores = model.score_samples(val_values)
        calibration = choose_threshold(truth, scores, max_fpr=manifest['max_fpr'])
        candidate = {'spec': spec, 'calibration': calibration,
                     'distinct_training_vectors': len(np.unique(values, axis=0)),
                     'fit_score_calibration_seconds': time.perf_counter() - begin}
        candidates.append(candidate)
        fitted[spec['id']] = model, ref
        for q in manifest['quantile_sensitivity']:
            threshold = float(np.quantile(scores, q))
            sensitivity.append({'candidate': spec['id'], 'policy': 'label-blind validation quantile',
                'quantile': q, 'threshold': threshold, 'metrics': binary_metrics(truth, scores, threshold)})
        sensitivity.append({'candidate': spec['id'], 'policy': 'sklearn auto offset', 'threshold': float(model.offset_),
                            'metrics': binary_metrics(truth, scores, float(model.offset_))})
        print(json.dumps({'validation_candidate': spec['id'], 'calibration': calibration}), flush=True)
    chosen = sorted(candidates, key=lambda c: (-float(c['calibration']['metrics']['f1'] or 0),
        -float(c['calibration']['metrics']['auprc_average_precision'] or 0),
        float(c['calibration']['metrics']['fpr']), c['spec']['id']))[0]
    model, ref = fitted[chosen['spec']['id']]
    seeds = []
    for seed in manifest['seed_sensitivity']:
        spec = dict(chosen['spec'], seed=seed)
        scores = fit(spec, matrix(sample, len(sample), ref)).score_samples(
            base_validation if ref is None else matrix(validation, len(truth), ref))
        seeds.append({'seed': seed, 'calibration': choose_threshold(truth, scores, max_fpr=manifest['max_fpr'])})
    joblib.dump({'model': model, 'reference': ref, 'features': chosen['spec']['features']}, directory / 'selected.joblib')
    report = {'status': 'PASS', 'scope': 'validation only; no test scores or label distribution accessed',
        'eligible_units': len(truth), 'positives': int(truth.sum()), 'negatives': int((truth == 0).sum()),
        'training_used': len(sample), 'reference': reference.summary(), 'candidates': candidates,
        'threshold_sensitivity': sensitivity, 'seed_sensitivity': seeds,
        'legacy_if': binary_metrics(truth, legacy_model.score_samples(base_validation), legacy_threshold),
        'legacy_rule': binary_metrics(truth, np.expm1(base_validation[:, 0]), legacy_rule_threshold, direction='higher'),
        'selected': chosen['spec']['id'], 'validation_seconds': time.perf_counter() - started}
    write_json(directory / 'validation.json', report)
    selection = {'selected': chosen['spec'], 'threshold': chosen['calibration']['threshold'],
        'comparison': '<', 'score_direction': 'lower', 'threshold_uses_validation_labels': True,
        'manifest_sha256': digest(directory / 'manifest.json'),
        'validation_sha256': digest(directory / 'validation.json'),
        'selected_artifact_sha256': digest(directory / 'selected.joblib'),
        'baseline_artifact_sha256': digest(directory / 'baselines.joblib'),
        'frozen_at_utc': datetime.now(timezone.utc).isoformat()}
    write_json(directory / 'selection.json', selection)
    print(json.dumps({'frozen_selection': selection}), flush=True)


def test(study_id, archive):
    directory = ROOT / study_id
    if (directory / 'test-access.json').exists():
        raise ValueError('Independent test has been opened; no repeat tuning/evaluation.')
    manifest = checked(directory, archive)
    selection = read_json(directory / 'selection.json')
    if digest(directory / 'manifest.json') != selection['manifest_sha256'] or digest(directory / 'validation.json') != selection['validation_sha256']:
        raise ValueError('Frozen selection input changed.')
    if digest(directory / 'selected.joblib') != selection['selected_artifact_sha256'] or digest(directory / 'baselines.joblib') != selection['baseline_artifact_sha256']:
        raise ValueError('Trusted local artifact changed.')
    validation = read_json(directory / 'validation.json')
    chosen = next(c for c in validation['candidates'] if c['spec']['id'] == validation['selected'])
    if chosen['spec'] != selection['selected'] or chosen['calibration']['threshold'] != selection['threshold']:
        raise ValueError('Selection no longer matches validation-only choice.')
    path = checked_cache(directory, manifest, 'test')
    write_json(directory / 'test-access.json', {'selection_sha256': digest(directory / 'selection.json'),
        'opened_at_utc': datetime.now(timezone.utc).isoformat()})
    begin = time.perf_counter()
    bundle = joblib.load(directory / 'selected.joblib')
    baseline = joblib.load(directory / 'baselines.joblib')
    truth = labels_for(archive, manifest, 'test', path)
    base = matrix(path, len(truth))
    legacy_scores = baseline['model'].score_samples(base)
    rule_scores = np.expm1(base[:, 0])
    features = base if bundle['reference'] is None else matrix(path, len(truth), bundle['reference'])
    improved_scores = bundle['model'].score_samples(features)
    results = {'legacy_rule': binary_metrics(truth, rule_scores, baseline['rule_threshold'], direction='higher'),
        'legacy_if': binary_metrics(truth, legacy_scores, baseline['if_threshold']),
        'selected_if': binary_metrics(truth, improved_scores, selection['threshold'])}
    np.savez_compressed(directory / 'test-predictions.npz', truth=truth, legacy_if_scores=legacy_scores,
                        selected_if_scores=improved_scores, rule_scores=rule_scores)
    report = {'status': 'MEASURED', 'study_id': study_id, 'source': 'actual full Loghub BGL archive, fixed July UTC slice',
        'archive_sha256': manifest['archive_sha256'], 'full_member_sha256': manifest['full_member_sha256'],
        'selected_raw_sha256': manifest['selected_raw_sha256'], 'split_utc': manifest['split_utc'],
        'phase_events': manifest['phase_events'], 'unit_counts': manifest['unit_counts'],
        'singleton_units': manifest['singleton_units'], 'test_positives': int(truth.sum()),
        'test_negatives': int((truth == 0).sum()), 'test_prevalence': float(truth.mean()),
        'selection': selection, 'metrics': results, 'test_seconds': time.perf_counter() - begin,
        'peak_working_set_mib': psutil.Process().memory_info().peak_wset / 1048576 if os.name == 'nt' else None,
        'prediction_sha256': digest(directory / 'test-predictions.npz'),
        'manifest_sha256': digest(directory / 'manifest.json'), 'selection_sha256': digest(directory / 'selection.json'),
        'software': manifest['software'],
        'semantics': {'unit': manifest['unit'], 'coverage': manifest['coverage'],
                      'scores': 'native lower score more anomalous; not probability',
                      'auprc': 'sklearn average precision, not trapezoidal PR area',
                      'comparison': 'same cohort; no point adjustment; no event/window mixing',
                      'deployment': 'offline experiment only; no default detector, UI or MySQL data changed'}}
    write_json(directory / 'test-results.json', report)
    CURATED.mkdir(parents=True, exist_ok=True)
    for name in ('protocol.json', 'manifest.json', 'validation.json', 'selection.json', 'test-access.json', 'test-results.json'):
        destination = CURATED / name
        if destination.exists():
            raise ValueError('Curated report already exists; preserve prior evidence.')
        destination.write_bytes((directory / name).read_bytes())
    print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', required=True, choices=['prepare', 'validate', 'test'])
    parser.add_argument('--study-id', default=STUDY_ID)
    parser.add_argument('--archive', type=Path, default=Path('data/raw/BGL.zip'))
    args = parser.parse_args()
    if len(args.study_id) != 32 or any(c not in '0123456789abcdef' for c in args.study_id):
        parser.error('A lowercase 32-hex study ID is required.')
    {'prepare': prepare, 'validate': validate, 'test': test}[args.stage](args.study_id, args.archive)


if __name__ == '__main__':
    main()
