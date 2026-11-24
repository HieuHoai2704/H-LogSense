"""Dataset metadata lifecycle; explicit grants and conservative physical delete.

Callers own commit/rollback. Names may change without changing the imported data
revision. Dataset identity, provenance fields and pipeline state are immutable
through this API. Only pristine empty registrations can be physically deleted.
"""

import re

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.orm import joinedload
from werkzeug.exceptions import NotFound

from app.domain import UserDataset
from app.extensions import db
from app.models import Dataset, DataSource
from app.security import Forbidden
from app.services.investigation import QueryError

MAX_ID = 2**63 - 1
MODES = {"real", "synthetic", "unverified"}
READ_ROLES = ("viewer", "analyst", "manager", "admin")
WRITE_ROLES = ("manager", "admin")
DELETE_ROLES = ("admin",)


class DatasetConflict(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def permission(actor, allowed):
    if actor is None or not actor.active or actor.role not in allowed:
        raise Forbidden()


def label(value, name, maximum):
    if not isinstance(value, str):
        raise QueryError(name + " must be text.")
    value = value.strip()
    if not 1 <= len(value) <= maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise QueryError(name + " has an invalid length or control character.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise QueryError(name + " must contain valid Unicode.") from None
    return value


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ID:
        raise QueryError("A positive integer source_id is required.")
    return value


def validate_create(data):
    if not isinstance(data, dict) or set(data) - {"name", "dataset_key", "data_mode", "source_id"}:
        raise QueryError("A dataset JSON object with supported fields is required.")
    name = label(data.get("name"), "Name", 200)
    key = label(data.get("dataset_key"), "Dataset key", 100)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", key):
        raise QueryError(
            "Dataset key must be an ASCII identifier using letters, numbers, dot, underscore or hyphen."
        )
    mode = data.get("data_mode", "unverified")
    if not isinstance(mode, str) or mode not in MODES:
        raise QueryError("Invalid data_mode.")
    source_id = identifier(data["source_id"]) if "source_id" in data else None
    return {"name": name, "dataset_key": key, "data_mode": mode, "source_id": source_id}


def validate_update(data):
    if not isinstance(data, dict) or set(data) != {"name"}:
        raise QueryError("Only the dataset name can be updated.")
    return label(data["name"], "Name", 200)


def serialize(dataset):
    return {
        "id": dataset.id,
        "name": dataset.name,
        "dataset_key": dataset.dataset_key,
        "data_mode": dataset.data_mode,
        "state": dataset.state,
        "input_revision": dataset.input_revision,
        "source_id": dataset.source_id,
        "source_name": dataset.source.name,
    }


def find_dataset(session, actor, dataset_id, *, lock=False):
    permission(actor, READ_ROLES)
    # No global admin data bypass, and no distinction between unseen/missing IDs.
    grant = session.scalar(
        select(UserDataset.id).where(UserDataset.user_id == actor.id, UserDataset.dataset_id == dataset_id)
    )
    if grant is None:
        raise Forbidden()
    query = select(Dataset).where(Dataset.id == dataset_id)
    if lock:
        query = query.with_for_update()
    else:
        query = query.options(joinedload(Dataset.source))
    dataset = session.scalar(query)
    if dataset is None:
        raise NotFound()
    return dataset


def list_datasets(session, actor, *, after_id=0, limit=50, search=""):
    permission(actor, READ_ROLES)
    query = (
        select(Dataset)
        .join(UserDataset, UserDataset.dataset_id == Dataset.id)
        .where(UserDataset.user_id == actor.id, Dataset.id > after_id)
        .options(joinedload(Dataset.source))
    )
    if search:
        query = query.where(
            or_(
                Dataset.name.contains(search, autoescape=True),
                Dataset.dataset_key.contains(search, autoescape=True),
            )
        )
    rows = list(session.scalars(query.order_by(Dataset.id).limit(limit + 1)))
    return rows[:limit], rows[limit - 1].id if len(rows) > limit else None


def create_dataset(session, actor, data):
    permission(actor, WRITE_ROLES)
    values = validate_create(data)
    personal_key = "api-user-" + str(actor.id)
    source_id = values.pop("source_id")
    if source_id is None:
        # Stable per-user namespace gives duplicate keys meaningful 409 behavior.
        # A no-op upsert serializes concurrent first registrations without moving
        # or renaming an existing source. No user-provided global key is trusted.
        statement = insert(DataSource).values(source_key=personal_key, name="User-managed datasets")
        session.execute(statement.on_duplicate_key_update(id=DataSource.id))
        # A locking/current read sees a source committed by a competing creator
        # even when authentication established an older REPEATABLE READ snapshot.
        source = session.scalar(
            select(DataSource).where(DataSource.source_key == personal_key).with_for_update()
        )
        source_id = source.id
    else:
        source = session.get(DataSource, source_id)
        allowed = source is not None and source.source_key == personal_key
        if not allowed:
            allowed = (
                session.scalar(
                    select(UserDataset.id)
                    .join(Dataset, Dataset.id == UserDataset.dataset_id)
                    .where(UserDataset.user_id == actor.id, Dataset.source_id == source_id)
                    .limit(1)
                )
                is not None
            )
        if not allowed:
            raise Forbidden()
    # Keep the current-read parent attached. A later lazy relationship lookup
    # could otherwise use the older RR snapshot and miss a concurrent creator.
    dataset = Dataset(source=source, source_id=source_id, state="registered", input_revision=0, **values)
    session.add(dataset)
    session.flush()
    session.add(UserDataset(user_id=actor.id, dataset_id=dataset.id))
    session.flush()
    return dataset


def update_dataset(session, actor, dataset_id, data):
    permission(actor, WRITE_ROLES)
    name = validate_update(data)
    dataset = find_dataset(session, actor, dataset_id, lock=True)
    dataset.name = name
    session.flush()
    return dataset


def _delete_dataset_row(session, dataset_id):
    # Kept separate so an injected DB failure can prove ACL deletion rolls back.
    session.execute(delete(Dataset).where(Dataset.id == dataset_id))


def delete_dataset(session, actor, dataset_id):
    permission(actor, DELETE_ROLES)
    dataset = find_dataset(session, actor, dataset_id, lock=True)
    if dataset.input_revision != 0:
        raise DatasetConflict("dataset_not_empty", "Imported datasets cannot be deleted.")
    if dataset.state not in {"registered", "archived"}:
        raise DatasetConflict("dataset_busy", "Dataset is not a pristine empty registration.")
    # Inspect every direct dataset FK, including future scoped tables. ACL rows
    # alone may be removed; any source artifact/job/evidence/coverage blocks delete.
    for table in db.metadata.sorted_tables:
        if table is UserDataset.__table__:
            continue
        for foreign_key in table.foreign_keys:
            if foreign_key.column.table is Dataset.__table__:
                used = session.execute(
                    select(foreign_key.parent).where(foreign_key.parent == dataset_id).limit(1)
                ).first()
                if used is not None:
                    raise DatasetConflict(
                        "dataset_not_empty", "Dataset has related records; deletion is blocked."
                    )
    session.execute(delete(UserDataset).where(UserDataset.dataset_id == dataset_id))
    _delete_dataset_row(session, dataset_id)
