"""The Analysis function menu: one place lists every Analysis page and the dataset it opens."""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask, current_app, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from app.contracts import QueryError, dataset_id_of, dataset_source, is_dataset_source


@dataclass(frozen=True)
class MenuItem:
    key: str
    label: str
    icon: str
    href: str | None  # None: the page is planned but not built yet

    @property
    def available(self) -> bool:
        return self.href is not None


@dataclass(frozen=True)
class MenuGroup:
    label: str
    items: tuple[MenuItem, ...]


def requested_dataset() -> int | None:
    """The dataset named by the current URL (dataset_id=N or source=db-N), if any."""
    value = request.args.get("dataset_id", "")
    if value.isascii() and value.isdigit():
        return int(value)
    source = request.args.get("source", "")
    if is_dataset_source(source):
        try:
            return dataset_id_of(source)
        except QueryError:
            return None
    return None


def menu_dataset() -> int | None:
    """A dataset the signed-in user may open: the one in the URL, else their first grant."""
    if "sqlalchemy" not in current_app.extensions:
        return None
    from app.extensions import db
    from app.security import authorized_datasets

    try:
        allowed = authorized_datasets()
    except SQLAlchemyError:
        db.session.rollback()
        return None
    wanted = requested_dataset()
    if wanted in allowed:
        return wanted
    return min(allowed) if allowed else None


def analysis_menu() -> tuple[MenuGroup, ...]:
    dataset = menu_dataset()
    logs = url_for("dashboard", workspace="logs", dataset_id=dataset)
    investigation = url_for("dashboard", source=dataset_source(dataset) if dataset else "demo")
    alerts = url_for("dashboard", workspace="logs", dataset_id=dataset, _anchor="incident-workspace")
    overview = url_for("operations.overview", dataset_id=dataset)
    quality = url_for("operations.quality", dataset_id=dataset)
    pipeline = url_for("operations.pipeline", dataset_id=dataset)
    return (
        MenuGroup(
            "Monitoring",
            (
                MenuItem("overview", "Overview", "overview", overview),
                MenuItem("logs", "Log Explorer", "logs", logs),
                MenuItem("investigation", "Anomaly investigation", "investigation", investigation),
                MenuItem("alerts", "Alerts", "alerts", alerts),
            ),
        ),
        MenuGroup(
            "Data operations",
            (
                MenuItem("quality", "Data quality", "quality", quality),
                MenuItem("pipeline", "Pipeline & jobs", "pipeline", pipeline),
                MenuItem("schedule", "Schedules", "schedule", None),
            ),
        ),
        MenuGroup(
            "Data sources",
            (
                MenuItem("datasets", "Datasets", "datasets", url_for("dataset_pages.index")),
                MenuItem("catalog", "Loghub catalog", "catalog", url_for("dataset_pages.catalog")),
            ),
        ),
    )


def init_analysis_menu(app: Flask) -> None:
    # A global, not a context processor: emails render templates outside a request.
    app.jinja_env.globals["analysis_menu"] = analysis_menu
