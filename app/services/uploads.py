"""Bounded, immutable upload staging and queued BGL-compatible ingestion.

Original files are never interpreted as paths or executed. CSV is explicitly a
raw_line container, not a guessed event schema. Trusted manifests bind original
bytes, normalized bytes and row mapping; workers recheck their hashes on retry.
"""

from contextlib import contextmanager
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from uuid import uuid4
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from sqlalchemy import select
from sqlalchemy.orm import Session
from werkzeug.exceptions import NotFound

from app.models import Dataset, ProcessingJob, SourceArtifact
from app.domain import UserDataset
from app.parsers.bgl import parse_line, MAX_LINE_BYTES
from app.services.bgl_ingestion import fingerprint, ingest_bgl, import_lease, ImportBusyError
from app.services.redaction import redact
from app.security import Forbidden

UPLOAD_ROOT = Path('.local/uploads')
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_REQUEST_BYTES = 17 * 1024 * 1024
MAX_ROWS = 200000
MAX_ATTEMPTS = 3
TYPE = 'upload-bgl-v1'
LABEL_SOURCE, LABEL_VERSION = 'uploaded-bgl', 'supplied'


class UploadError(Exception):
    def __init__(self, code, message, status=422):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def root_path():
    root = UPLOAD_ROOT.resolve()
    local = (Path(__file__).resolve().parents[2] / '.local').resolve()
    if not root.is_relative_to(local) or root == local:
        raise UploadError('upload_storage', 'Upload storage is not an owned local directory.', 503)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def directory(upload_id):
    if not isinstance(upload_id, str) or not re.fullmatch(r'[a-f0-9]{32}', upload_id):
        raise NotFound()
    root = root_path()
    candidate = root / upload_id
    if candidate.is_symlink():
        raise UploadError('upload_integrity', 'Upload storage path changed.')
    result = candidate.resolve()
    if result.parent != root:
        raise UploadError('upload_integrity', 'Upload storage path changed.')
    return result


def local_file(folder, name):
    candidate = folder / name
    if candidate.is_symlink():
        raise UploadError('upload_integrity', 'Upload artifact path changed.')
    path = candidate.resolve()
    if path.parent != folder:
        raise UploadError('upload_integrity', 'Upload artifact path changed.')
    return path


def filename(value):
    if (not isinstance(value, str) or not 1 <= len(value) <= 200
            or value.startswith('.') or any(c in value for c in ('/', '\\', ':'))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise UploadError('invalid_filename', 'Use a plain .txt, .log or .csv filename.', 400)
    try:
        value.encode('utf-8', errors='strict')
    except UnicodeEncodeError:
        raise UploadError('invalid_filename', 'Filename must contain valid Unicode.', 400) from None
    extension = Path(value).suffix.lower()
    if extension not in {'.txt', '.log', '.csv'}:
        raise UploadError('unsupported_format', 'Only UTF-8 BGL .txt/.log or raw_line .csv files are supported.', 415)
    return value, extension


def protect_directory(folder):
    """Restrict original logs to the worker account before writing any bytes."""
    if os.name != 'nt':
        folder.chmod(0o700)
        return
    try:
        options = {'capture_output': True, 'check': True,
                   'creationflags': subprocess.CREATE_NO_WINDOW}
        identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], **options)
        matches = re.findall(rb'S-1-5-[0-9-]+', identity.stdout)
        if len(matches) != 1:
            raise ValueError('Current Windows identity is unavailable.')
        sid = matches[0].decode('ascii')
        subprocess.run(['icacls', str(folder), '/inheritance:r', '/grant:r',
                        '*' + sid + ':(OI)(CI)F', '*S-1-5-18:(OI)(CI)F'], **options)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise UploadError('upload_storage', 'Private upload storage permissions could not be established.', 503) from None


def discard(bundle):
    """Remove only newly created unaccepted staging files, never accepted data."""
    folder = directory(bundle['upload_id'])
    for name in ('original.txt', 'original.log', 'original.csv', 'normalized.zip', 'normalized.log', 'mapping.jsonl', 'manifest.json'):
        path = local_file(folder, name)
        if path.exists():
            path.unlink()
    folder.rmdir()


def _raw_lines(original):
    with original.open('rb') as stream:
        offset = 0
        for number in range(1, MAX_ROWS + 2):
            raw = stream.readline(MAX_LINE_BYTES + 1)
            if not raw:
                return
            if number > MAX_ROWS or len(raw) > MAX_LINE_BYTES:
                raise UploadError('upload_limit', 'Uploaded rows exceed bounded line or row limits.')
            if number == 1 and raw.startswith(b'\xef\xbb\xbf'):
                raise UploadError('unsupported_encoding', 'BGL TXT/LOG must be UTF-8 without a byte-order mark.')
            yield raw, {'original_line': number, 'original_byte_offset': offset}
            offset += len(raw)


def _csv_lines(original):
    # field_size_limit is process-global; use a fixed bounded policy, never a
    # user-provided value. The accepted schema is exactly one raw_line column.
    csv.field_size_limit(MAX_LINE_BYTES)
    try:
        with original.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream, strict=True)
            if next(reader, None) != ['raw_line']:
                raise UploadError('unsupported_csv_schema', 'CSV must have exactly one header: raw_line.')
            previous = reader.line_num
            for ordinal, row in enumerate(reader, 1):
                if ordinal > MAX_ROWS or len(row) != 1:
                    raise UploadError('invalid_csv_row', 'Each bounded CSV row must contain one raw_line field.')
                value = row[0]
                if value.endswith('\r\n'):
                    value = value[:-2]
                elif value.endswith('\n') or value.endswith('\r'):
                    value = value[:-1]
                if '\n' in value or '\r' in value:
                    raise UploadError('invalid_csv_row', 'raw_line must contain one BGL line, without embedded newlines.')
                raw = value.encode('utf-8') + b'\n'
                if len(raw) > MAX_LINE_BYTES:
                    raise UploadError('upload_limit', 'A decoded CSV raw_line exceeds the BGL line limit.')
                yield raw, {'csv_row': ordinal + 1, 'csv_physical_line_start': previous + 1,
                            'csv_physical_line_end': reader.line_num}
                previous = reader.line_num
    except (csv.Error, UnicodeError):
        raise UploadError('invalid_csv', 'CSV must be bounded, well-formed UTF-8 with a raw_line column.') from None


def stage_file(storage):
    original_name, extension = filename(storage.filename)
    upload_id = uuid4().hex
    folder = directory(upload_id)
    folder.mkdir(mode=0o700)
    bundle = {'upload_id': upload_id}
    source = None
    try:
        protect_directory(folder)
        original = local_file(folder, 'original' + extension)
        digest, size = hashlib.sha256(), 0
        with original.open('xb') as output:
            for block in iter(lambda: storage.stream.read(65536), b''):
                size += len(block)
                if size > MAX_FILE_BYTES:
                    raise UploadError('file_too_large', 'Uploaded file exceeds 16 MiB.', 413)
                digest.update(block)
                output.write(block)
        if not size:
            raise UploadError('empty_file', 'Choose a nonempty UTF-8 BGL file.')
        normalized = local_file(folder, 'normalized.log')
        mapping = local_file(folder, 'mapping.jsonl')
        valid = malformed = total_bytes = 0
        source = _csv_lines(original) if extension == '.csv' else _raw_lines(original)
        normalized_digest = hashlib.sha256()
        with normalized.open('xb') as output, mapping.open('x', encoding='utf-8', newline='\n') as rows:
            for number, (raw, reference) in enumerate(source, 1):
                if raw.startswith(b'\xef\xbb\xbf'):
                    raise UploadError('unsupported_encoding', 'BGL records must not contain a byte-order mark.')
                if any(c < 32 and c not in (9, 10, 13) for c in raw):
                    raise UploadError('unsupported_encoding', 'Binary/control content is not supported.')
                try:
                    raw.decode('utf-8', errors='strict')
                except UnicodeDecodeError:
                    raise UploadError('unsupported_encoding', 'Files must use valid UTF-8.') from None
                record = parse_line(raw, number, total_bytes)
                if record.error is None:
                    valid += 1
                else:
                    malformed += 1
                reference.update(bgl_line=number, bgl_byte_offset=total_bytes)
                rows.write(json.dumps(reference, separators=(',', ':')) + '\n')
                output.write(raw)
                normalized_digest.update(raw)
                total_bytes += len(raw)
                if total_bytes > MAX_FILE_BYTES:
                    raise UploadError('upload_limit', 'Decoded BGL content exceeds 16 MiB.')
        if valid == 0:
            raise UploadError('unsupported_log_schema', 'No valid BGL records found; arbitrary log schemas are not guessed.')
        member = upload_id + '/BGL.log'
        archive = local_file(folder, 'normalized.zip')
        info = ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = ZIP_STORED
        info.external_attr = 0o600 << 16
        with ZipFile(archive, 'x') as zipped, normalized.open('rb') as source:
            with zipped.open(info, 'w') as output:
                for block in iter(lambda: source.read(65536), b''):
                    output.write(block)
        normalized.unlink()  # Derived staging copy only; original and ZIP persist.
        manifest = {'version': TYPE, 'upload_id': upload_id, 'original_filename': original_name,
            'original_key': original.name, 'original_bytes': size, 'original_sha256': digest.hexdigest(),
            'format': extension[1:], 'normalized_sha256': normalized_digest.hexdigest(),
            'normalized_bytes': total_bytes, 'archive_sha256': fingerprint(archive),
            'mapping_sha256': fingerprint(mapping), 'member': member,
            'total_lines': valid + malformed, 'valid_lines': valid, 'malformed_rows': malformed,
            'label_source': LABEL_SOURCE, 'label_version': LABEL_VERSION,
            'normalization': ('CSV raw_line container decoded as UTF-8; at most one terminal CRLF/LF/CR removed; LF appended per row. Original CSV bytes retained; CSV row/physical-line mapping is not a CSV byte offset.'
                              if extension == '.csv' else 'BGL content bytes preserved exactly; ZIP is a server-created container.')}
        path = local_file(folder, 'manifest.json')
        path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
        if os.name != 'nt':
            for stored_path in folder.iterdir():
                stored_path.chmod(0o600)
        bundle.update(manifest=manifest, manifest_sha256=fingerprint(path))
        return bundle
    except Exception:
        # A generator paused at yield still owns its input file. Close it before
        # cleanup, otherwise Windows correctly refuses to unlink the open file.
        if source is not None:
            source.close()
        discard(bundle)
        raise


def load_bundle(upload_id, expected=None):
    folder = directory(upload_id)
    manifest_path = local_file(folder, 'manifest.json')
    if not manifest_path.is_file() or manifest_path.stat().st_size > 16384:
        raise UploadError('upload_integrity', 'Upload manifest is unavailable or changed.')
    if expected is not None and expected.get('manifest_sha256') != fingerprint(manifest_path):
        raise UploadError('upload_integrity', 'Upload manifest checksum changed.')
    try:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    except (UnicodeError, ValueError):
        raise UploadError('upload_integrity', 'Upload manifest is malformed.') from None
    if manifest.get('version') != TYPE or manifest.get('upload_id') != upload_id:
        raise UploadError('upload_integrity', 'Upload identity changed.')
    _, extension = filename(manifest.get('original_filename'))
    if manifest.get('original_key') != 'original' + extension or manifest.get('member') != upload_id + '/BGL.log':
        raise UploadError('upload_integrity', 'Upload artifact identity changed.')
    checks = [('original' + extension, 'original_sha256', MAX_FILE_BYTES),
              ('normalized.zip', 'archive_sha256', MAX_FILE_BYTES + 2048),
              ('mapping.jsonl', 'mapping_sha256', 64 * 1024 * 1024)]
    for name, key, maximum in checks:
        path = local_file(folder, name)
        if not path.is_file() or path.stat().st_size > maximum or fingerprint(path) != manifest.get(key):
            raise UploadError('upload_integrity', 'Upload artifact checksum changed; no data was replaced.')
    if expected is not None and (expected.get('manifest_sha256') != fingerprint(manifest_path)
        or any(expected.get(key) != manifest.get(key) for key in ('original_sha256', 'original_filename', 'format', 'archive_sha256'))):
        raise UploadError('upload_integrity', 'Upload differs from the queued immutable manifest.')
    return manifest, folder


def job_for_upload(session, upload_id, *, lock=False):
    if not isinstance(upload_id, str) or not re.fullmatch(r'[a-f0-9]{32}', upload_id):
        raise NotFound()
    query = select(ProcessingJob).where(ProcessingJob.kind == 'parsing',
        ProcessingJob.configuration['type'].as_string() == TYPE,
        ProcessingJob.configuration['upload_id'].as_string() == upload_id)
    if lock:
        query = query.with_for_update()
    job = session.scalar(query)
    if job is None:
        raise NotFound()
    return job


def queue_upload(session, actor, dataset_id, key, bundle):
    if (actor is None or not actor.active or actor.role not in {'analyst', 'manager', 'admin'}
            or session.scalar(select(UserDataset.id).where(
                UserDataset.user_id == actor.id, UserDataset.dataset_id == dataset_id)) is None):
        raise Forbidden()
    dataset = session.scalar(select(Dataset).where(Dataset.id == dataset_id).with_for_update())
    if dataset is None or dataset.state == 'archived':
        raise UploadError('dataset_unavailable', 'Dataset is unavailable for ingestion.', 409)
    key_hash = hashlib.sha256(key.encode('utf-8')).hexdigest()
    job_key = 'upload:' + key_hash
    existing = session.scalar(select(ProcessingJob).where(ProcessingJob.dataset_id == dataset_id,
        ProcessingJob.job_key == job_key).with_for_update())
    manifest = bundle['manifest']
    if existing is not None:
        old = existing.configuration or {}
        if old.get('type') != TYPE or any(old.get(k) != manifest.get(k) for k in ('original_sha256', 'original_filename', 'format')):
            raise UploadError('idempotency_conflict', 'This key already refers to different content or metadata.', 409)
        return existing, False
    config = {key: manifest[key] for key in ('upload_id', 'original_sha256', 'original_filename', 'original_bytes', 'normalized_sha256', 'format', 'archive_sha256', 'total_lines', 'valid_lines', 'malformed_rows', 'member')}
    config.update(type=TYPE, manifest_sha256=bundle['manifest_sha256'], submitted_by=actor.id)
    job = ProcessingJob(dataset_id=dataset_id, kind='parsing', state='queued', job_key=job_key,
                        configuration=config, result={'attempts': 0})
    session.add(job)
    session.flush()
    return job, True


def serialize_job(session, job):
    config, result = job.configuration or {}, job.result or {}
    artifact = session.scalar(select(SourceArtifact).where(SourceArtifact.dataset_id == job.dataset_id,
        SourceArtifact.artifact_key == config['member']))
    count = artifact.checkpoint_line if artifact else job.processed_count
    return {'upload_id': config['upload_id'], 'job_id': job.id, 'dataset_id': job.dataset_id,
        'original_sha256': config['original_sha256'],
        'state': job.state, 'processed_count': count, 'total_lines': config['total_lines'],
        'parsed_events': artifact.parsed_count if artifact else 0,
        'malformed_rows': artifact.malformed_count if artifact else 0,
        'error_code': job.error_code, 'child_import_job_id': result.get('child_import_job_id'),
        'attempts': result.get('attempts', 0),
        'can_retry': job.state in {'running', 'failed'} and result.get('attempts', 0) < MAX_ATTEMPTS and job.error_code != 'upload_integrity',
        'status_url': '/api/v1/uploads/' + config['upload_id'],
        'provenance': redact({key: config[key] for key in ('original_filename', 'original_bytes', 'original_sha256', 'normalized_sha256', 'format')} | {'label_source': LABEL_SOURCE, 'label_version': LABEL_VERSION})}


@contextmanager
def mapping_reader(folder, manifest):
    with local_file(folder, 'mapping.jsonl').open(encoding='utf-8') as stream:
        iterator = (json.loads(line) for line in stream)
        current = None
        def metadata(record):
            nonlocal current
            while current is None or current['bgl_line'] < record.line_number:
                current = next(iterator)
            if current['bgl_line'] != record.line_number:
                raise UploadError('upload_integrity', 'Upload source mapping changed.')
            return dict(current, upload_id=manifest['upload_id'], original_sha256=manifest['original_sha256'],
                        original_filename=manifest['original_filename'], format=manifest['format'],
                        label_source=LABEL_SOURCE, label_version=LABEL_VERSION)
        yield metadata


def run_once(engine):
    with Session(engine) as session:
        candidate = session.scalar(select(ProcessingJob.id).where(ProcessingJob.kind == 'parsing',
            ProcessingJob.state == 'queued', ProcessingJob.configuration['type'].as_string() == TYPE)
            .order_by(ProcessingJob.id).limit(1))
    if candidate is None:
        return False
    try:
        with import_lease(engine, 'upload-job:' + str(candidate)):
            return execute_job(engine, candidate)
    except RuntimeError:
        return False


def execute_job(engine, job_id):
    with Session(engine) as session, session.begin():
        job = session.scalar(select(ProcessingJob).where(ProcessingJob.id == job_id,
            ProcessingJob.kind == 'parsing', ProcessingJob.state == 'queued').with_for_update())
        if job is None or (job.configuration or {}).get('type') != TYPE:
            return False
        config = dict(job.configuration)
        result = dict(job.result or {})
        if result.get('attempts', 0) >= MAX_ATTEMPTS:
            job.state, job.error_code = 'failed', 'retry_limit'
            return True
        result['attempts'] = result.get('attempts', 0) + 1
        job.result, job.state, job.error_code = result, 'running', None
        dataset_id = job.dataset_id
    try:
        manifest, folder = load_bundle(config['upload_id'], config)
        def progress(value):
            with Session(engine) as session, session.begin():
                outer = session.get(ProcessingJob, job_id)
                outer.processed_count = value['line']
        def started(inner_id):
            with Session(engine) as session, session.begin():
                outer = session.get(ProcessingJob, job_id)
                outer.result = dict(outer.result or {}, child_import_job_id=inner_id)
        with mapping_reader(folder, manifest) as metadata:
            imported = ingest_bgl(engine, dataset_id, local_file(folder, 'normalized.zip'), member=manifest['member'],
                progress=progress, job_started=started, event_metadata=metadata,
                label_source=LABEL_SOURCE, label_version=LABEL_VERSION)
        with Session(engine) as session, session.begin():
            outer = session.get(ProcessingJob, job_id)
            outer.state, outer.processed_count = 'completed', imported['physical_lines']
            outer.result = dict(outer.result or {}, **imported, stage='completed')
    except Exception as error:
        code = error.code if isinstance(error, UploadError) else 'dataset_busy' if isinstance(error, ImportBusyError) else 'upload_ingestion_failed'
        with Session(engine) as session, session.begin():
            outer = session.get(ProcessingJob, job_id)
            outer.state, outer.error_code = 'failed', code
    return True
