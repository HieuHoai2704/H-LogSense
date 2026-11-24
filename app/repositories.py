"""Dataset-scoped, bounded read repositories. Callers own the transaction."""

from datetime import datetime
from sqlalchemy import select, or_, and_
from app.models import LogEvent, AnomalyOutput, Dataset


def page_events(
    session,
    dataset_id: int,
    start: datetime,
    end: datetime,
    *,
    cursor=None,
    limit=100,
    host=None,
):
    if not 1 <= limit <= 1000 or start >= end:
        raise ValueError("Invalid event page bounds.")
    query = select(LogEvent).where(
        LogEvent.dataset_id == dataset_id,
        LogEvent.timestamp >= start,
        LogEvent.timestamp < end,
    )
    if host is not None:
        query = query.where(LogEvent.host == host)
    if cursor is not None:
        timestamp, event_id = cursor
        query = query.where(
            or_(
                LogEvent.timestamp > timestamp,
                and_(LogEvent.timestamp == timestamp, LogEvent.id > event_id),
            )
        )
    return list(session.scalars(query.order_by(LogEvent.timestamp, LogEvent.id).limit(limit)))


def page_anomalies(session, dataset_id, run_id, *, after_id=0, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError("Invalid anomaly page size.")
    return list(
        session.scalars(
            select(AnomalyOutput)
            .where(
                AnomalyOutput.dataset_id == dataset_id,
                AnomalyOutput.run_id == run_id,
                AnomalyOutput.id > after_id,
            )
            .order_by(AnomalyOutput.id)
            .limit(limit)
        )
    )


def archive_dataset(session, dataset_id):
    dataset = session.get(Dataset, dataset_id)
    if dataset is None:
        raise ValueError("Dataset not found.")
    dataset.state = "archived"
