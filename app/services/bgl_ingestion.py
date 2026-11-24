"""Bounded BGL ZIP import. Data, counters and checkpoint commit atomically."""

import hashlib
from contextlib import contextmanager
from itertools import islice
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from sqlalchemy import insert, select, text, update
from sqlalchemy.orm import Session

from app.models import (
    Dataset,
    SourceArtifact,
    RawLogRecord,
    LogEvent,
    GroundTruthLabel,
    ProcessingJob,
)
from app.parsers.bgl import iter_records, VERSION, VERSIONS


class ImportBusyError(RuntimeError):
    """Another live process owns the requested connection-bound import lease."""


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_member(member):
    key = PurePosixPath(member)
    if (
        not member
        or len(member) > 200
        or key.is_absolute()
        or ".." in key.parts
        or "\\" in member
        or ":" in member
    ):
        raise ValueError("Invalid archive member.")


@contextmanager
def import_lease(engine, dataset_id):
    """Connection-owned MySQL lease; process exit releases it automatically."""
    lock = (
        "lsi:"
        + hashlib.sha256(f"{engine.url.database}:{dataset_id}".encode()).hexdigest()[
            :60
        ]
    )
    with engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT GET_LOCK(:key, 0)"), {"key": lock}
        ).scalar_one()
        connection.commit()
        if acquired != 1:
            raise ImportBusyError("An import already owns this dataset.")
        try:
            yield
        finally:
            connection.execute(text("SELECT RELEASE_LOCK(:key)"), {"key": lock})
            connection.commit()


def ingest_bgl(
    engine,
    dataset_id,
    archive,
    *,
    member="BGL.log",
    limit=None,
    batch_size=500,
    progress=None,
    before_commit=None,
    label_source="loghub-bgl",
    label_version="original",
    event_metadata=None,
    job_started=None,
):
    with import_lease(engine, dataset_id):
        return _ingest_bgl(
            engine,
            dataset_id,
            archive,
            member=member,
            limit=limit,
            batch_size=batch_size,
            progress=progress,
            before_commit=before_commit,
            label_source=label_source,
            label_version=label_version,
            event_metadata=event_metadata,
            job_started=job_started,
        )


def _ingest_bgl(
    engine,
    dataset_id,
    archive,
    *,
    member="BGL.log",
    limit=None,
    batch_size=500,
    progress=None,
    before_commit=None,
    label_source="loghub-bgl",
    label_version="original",
    event_metadata=None,
    job_started=None,
):
    """Import up to an absolute physical-line checkpoint; None means EOF.

    Serialize per dataset with SELECT FOR UPDATE. Retrying the same immutable
    artifact/parser resumes committed progress; changed content is rejected.
    An archive is an operator-supplied local input, never an HTTP filename.
    """
    if not 1 <= batch_size <= 2000 or (limit is not None and limit < 1):
        raise ValueError("Invalid import limits.")
    if any(not isinstance(value, str) or not 1 <= len(value) <= 64
           for value in (label_source, label_version)):
        raise ValueError("Invalid supplied label provenance.")
    if event_metadata is not None and not callable(event_metadata):
        raise ValueError("Event metadata must be a trusted callable.")
    validate_member(member)
    archive = Path(archive)
    checksum = fingerprint(archive)
    with ZipFile(archive) as zipped:
        info = zipped.getinfo(member)
        if info.is_dir() or info.file_size > 10 * 1024**3:
            raise ValueError("Invalid archive member size.")
        with Session(engine) as session, session.begin():
            dataset = session.scalar(
                select(Dataset).where(Dataset.id == dataset_id).with_for_update()
            )
            if dataset is None or dataset.state == "archived":
                raise ValueError("Dataset unavailable.")
            artifact = session.scalar(
                select(SourceArtifact).where(
                    SourceArtifact.dataset_id == dataset_id,
                    SourceArtifact.artifact_key == member,
                )
            )
            if artifact is None:
                artifact = SourceArtifact(
                    dataset_id=dataset_id,
                    artifact_key=member,
                    sha256=checksum,
                    byte_length=info.file_size,
                    parser_version=VERSION,
                )
                session.add(artifact)
                session.flush()
            elif (artifact.sha256, artifact.byte_length) != (checksum, info.file_size) or (
                artifact.parser_version not in VERSIONS
            ):
                raise ValueError("Artifact or parser changed; register a new dataset.")
            # Resume with the version the artifact started with, so one dataset never mixes versions.
            parser_version = artifact.parser_version
            artifact_id = artifact.id
            # Holding the exclusive lease proves no earlier import worker is alive.
            session.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.dataset_id == dataset_id,
                    ProcessingJob.kind == "ingestion",
                    ProcessingJob.state == "running",
                )
                .values(state="failed", error_code="worker_interrupted")
            )
            job = ProcessingJob(
                dataset_id=dataset_id, kind="ingestion", state="running"
            )
            session.add(job)
            session.flush()
            job_id = job.id
        try:
            if job_started:
                job_started(job_id)
            with zipped.open(info) as stream:
                while True:
                    with Session(engine) as session, session.begin():
                        dataset = session.scalar(
                            select(Dataset)
                            .where(Dataset.id == dataset_id)
                            .with_for_update()
                        )
                        if dataset.state == "archived":
                            raise ValueError("Dataset archived while importing.")
                        artifact = session.get(SourceArtifact, artifact_id)
                        if limit is not None and artifact.checkpoint_line >= limit:
                            session.get(ProcessingJob, job_id).state = "completed"
                            break
                        stream.seek(artifact.checkpoint_byte)
                        remaining = (
                            batch_size
                            if limit is None
                            else min(batch_size, limit - artifact.checkpoint_line)
                        )
                        records = []
                        batch_bytes = 0
                        iterator = iter_records(
                            stream,
                            first_line=artifact.checkpoint_line + 1,
                            byte_offset=artifact.checkpoint_byte,
                            version=parser_version,
                        )
                        for record in islice(iterator, remaining):
                            if (
                                records
                                and batch_bytes + len(record.raw) > 8 * 1024 * 1024
                            ):
                                break
                            records.append(record)
                            batch_bytes += len(record.raw)
                        if not records:
                            dataset.state = "imported"
                            session.get(ProcessingJob, job_id).state = "completed"
                            break
                        session.execute(
                            insert(RawLogRecord),
                            [
                                dict(
                                    dataset_id=dataset_id,
                                    artifact_id=artifact_id,
                                    line_number=r.line_number,
                                    byte_offset=r.byte_offset,
                                    raw_bytes=r.raw,
                                    parse_error=r.error,
                                )
                                for r in records
                            ],
                        )
                        raw_ids = dict(
                            session.execute(
                                select(RawLogRecord.line_number, RawLogRecord.id).where(
                                    RawLogRecord.dataset_id == dataset_id,
                                    RawLogRecord.artifact_id == artifact_id,
                                    RawLogRecord.line_number >= records[0].line_number,
                                    RawLogRecord.line_number <= records[-1].line_number,
                                )
                            ).all()
                        )
                        valid = [r for r in records if r.error is None]
                        if valid:
                            session.execute(
                                insert(LogEvent),
                                [
                                    dict(
                                        dataset_id=dataset_id,
                                        raw_id=raw_ids[r.line_number],
                                        parser_version=parser_version,
                                        emit_index=0,
                                        timestamp=r.timestamp,
                                        raw_timestamp=r.attributes["printed_timestamp"],
                                        host=r.host,
                                        service=r.attributes["component"],
                                        severity=r.attributes["level"],
                                        message=r.message,
                                        attributes=(dict(r.attributes, upload=event_metadata(r))
                                                    if event_metadata else r.attributes),
                                    )
                                    for r in valid
                                ],
                            )
                            event_ids = dict(
                                session.execute(
                                    select(LogEvent.raw_id, LogEvent.id).where(
                                        LogEvent.dataset_id == dataset_id,
                                        LogEvent.raw_id.in_(
                                            [raw_ids[r.line_number] for r in valid]
                                        ),
                                    )
                                ).all()
                            )
                            session.execute(
                                insert(GroundTruthLabel),
                                [
                                    dict(
                                        dataset_id=dataset_id,
                                        event_id=event_ids[raw_ids[r.line_number]],
                                        source=label_source,
                                        version=label_version,
                                        label=r.label,
                                    )
                                    for r in valid
                                ],
                            )
                        artifact.checkpoint_line = records[-1].line_number
                        artifact.checkpoint_byte = records[-1].byte_offset + len(
                            records[-1].raw
                        )
                        artifact.parsed_count += len(valid)
                        artifact.malformed_count += len(records) - len(valid)
                        dataset.input_revision += 1
                        dataset.state = (
                            "imported"
                            if artifact.checkpoint_byte == info.file_size
                            else "partial"
                        )
                        job = session.get(ProcessingJob, job_id)
                        job.processed_count += len(records)
                        if before_commit:
                            before_commit(artifact.checkpoint_line)
                        checkpoint = artifact.checkpoint_line
                    # Progress is observable only after commit, never before.
                    if progress:
                        progress(
                            {
                                "line": checkpoint,
                                "total_bytes": info.file_size,
                                "dataset_id": dataset_id,
                            }
                        )
        except Exception:
            with Session(engine) as session, session.begin():
                session.get(ProcessingJob, job_id).state = "failed"
                session.get(ProcessingJob, job_id).error_code = "import_failed"
            raise
    with Session(engine) as session:
        artifact = session.get(SourceArtifact, artifact_id)
        return dict(
            dataset_id=dataset_id,
            physical_lines=artifact.checkpoint_line,
            parsed_events=artifact.parsed_count,
            malformed_rows=artifact.malformed_count,
            checkpoint_byte=artifact.checkpoint_byte,
        )
