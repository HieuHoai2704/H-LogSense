"""Analysis > Schedules: create, edit, pause, run now and delete recurring jobs (Flask-WTF forms, CSRF).

The worker (``python -m scripts.run.worker``, started by the demo command) runs the schedules that fall due.
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.analysis_menu import requested_dataset

schedule_pages = Blueprint("schedules", __name__, url_prefix="/analysis/schedules")


@schedule_pages.before_request
def require_account() -> ResponseReturnValue | None:
    if "sqlalchemy" not in current_app.extensions:
        return render_template("schedules.html", unavailable=True, datasets=[], dataset=None), 503
    from app.security import identity

    g.user = identity()
    if g.user is None:
        if request.method in {"GET", "HEAD"}:
            return redirect(url_for("accounts.login", next=request.full_path.rstrip("?")))
        abort(403)
    return None


@schedule_pages.after_request
def private_page(response: Any) -> Any:
    response.headers["Cache-Control"] = "no-store"
    return response


def granted_datasets() -> list[Any]:
    from app.extensions import db
    from app.models import Dataset
    from app.security import authorized_datasets

    allowed = authorized_datasets()
    return list(db.session.scalars(select(Dataset).where(Dataset.id.in_(allowed)).order_by(Dataset.id)))


def schedule_or_404(schedule_id: int) -> Any:
    from app.domain import JobSchedule
    from app.extensions import db
    from app.security import authorized_datasets

    schedule = db.session.get(JobSchedule, schedule_id)
    if schedule is None or schedule.dataset_id not in authorized_datasets():
        abort(404)
    return schedule


def localized(form: Any) -> Any:
    from app.web_datasets import localized_fields

    return localized_fields(form)


def save(form: Any, schedule: Any) -> str | None:
    """Copy the form into ``schedule``; returns an error message, or None."""
    from app.extensions import db
    from app.services.schedules import import_allowed

    if form.task.data == "import" and not import_allowed(db.session, schedule.dataset_id):
        return "Import schedules only extend a BGL dataset; this dataset holds other sources."
    schedule.name = form.name.data
    schedule.task = form.task.data
    schedule.interval_minutes = form.interval_minutes.data
    schedule.import_lines = form.import_lines.data if form.task.data == "import" else None
    schedule.enabled = form.enabled.data
    return None


@schedule_pages.route("", methods=["GET", "POST"])
def index() -> ResponseReturnValue:
    from app.domain import JobSchedule
    from app.extensions import db
    from app.forms import ActionForm, ScheduleForm
    from app.services.schedules import list_schedules, utcnow

    try:
        datasets = granted_datasets()
        wanted = request.args.get("dataset_id", type=int) or requested_dataset()
        dataset = next((item for item in datasets if item.id == wanted), datasets[0] if datasets else None)
        form = ScheduleForm(prefix="schedule")
        status = 200
        if request.method == "POST":
            if dataset is None:
                abort(403)
            if form.validate_on_submit():
                schedule = JobSchedule(dataset_id=dataset.id, created_by=g.user.id, next_run_at=utcnow())
                error = save(form, schedule)
                if error is None:
                    db.session.add(schedule)
                    try:
                        db.session.commit()
                    except IntegrityError:
                        db.session.rollback()
                        error = "A schedule with this name already exists for the dataset."
                if error is None:
                    flash("Schedule created.", "success")
                    return redirect(url_for("schedules.index", dataset_id=dataset.id), code=303)
                flash(error, "danger")
            status = 400
        schedules = list_schedules(db.session, dataset.id) if dataset else []
    except SQLAlchemyError:
        db.session.rollback()
        return render_template("schedules.html", unavailable=True, datasets=[], dataset=None), 503
    return render_template(
        "schedules.html",
        unavailable=False,
        datasets=datasets,
        dataset=dataset,
        schedules=schedules,
        form=localized(form),
        action=ActionForm(),
        editing=None,
        now=utcnow(),
    ), status


@schedule_pages.route("/<int:schedule_id>/edit", methods=["GET", "POST"])
def edit(schedule_id: int) -> ResponseReturnValue:
    from app.extensions import db
    from app.forms import ActionForm, ScheduleForm
    from app.services.schedules import list_schedules, utcnow

    schedule = schedule_or_404(schedule_id)
    form = ScheduleForm(prefix="schedule", obj=schedule)
    status = 200
    if request.method == "POST":
        if form.validate_on_submit():
            error = save(form, schedule)
            if error is None:
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    error = "A schedule with this name already exists for the dataset."
            if error is None:
                flash("Schedule saved.", "success")
                return redirect(url_for("schedules.index", dataset_id=schedule.dataset_id), code=303)
            flash(error, "danger")
            schedule = schedule_or_404(schedule_id)
        status = 400
    datasets = granted_datasets()
    dataset = next(item for item in datasets if item.id == schedule.dataset_id)
    return render_template(
        "schedules.html",
        unavailable=False,
        datasets=datasets,
        dataset=dataset,
        schedules=list_schedules(db.session, dataset.id),
        form=localized(form),
        action=ActionForm(),
        editing=schedule.id,
        now=utcnow(),
    ), status


@schedule_pages.post("/<int:schedule_id>/<any(toggle,run,delete):verb>")
def act(schedule_id: int, verb: str) -> ResponseReturnValue:
    from app.extensions import db
    from app.forms import ActionForm
    from app.services.schedules import utcnow

    if not ActionForm().validate_on_submit():
        abort(400)
    schedule = schedule_or_404(schedule_id)
    dataset_id = schedule.dataset_id
    if verb == "toggle":
        schedule.enabled = not schedule.enabled
        if schedule.enabled and schedule.next_run_at < utcnow():
            schedule.next_run_at = utcnow()
        message = "Schedule resumed." if schedule.enabled else "Schedule paused."
    elif verb == "run":
        schedule.enabled = True
        schedule.next_run_at = utcnow()
        message = "The schedule runs at the worker's next pass."
    else:
        db.session.delete(schedule)
        message = "Schedule deleted."
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("schedules.index", dataset_id=dataset_id), code=303)
