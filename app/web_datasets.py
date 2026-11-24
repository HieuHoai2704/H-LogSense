"""Server-rendered dataset management on the existing session and CRUD services."""

from datetime import datetime, timezone

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.forms import DatasetCreateForm, DatasetDeleteForm, DatasetRenameForm
from app.i18n import translate
from app.security import identity
from app.services.dataset_management import (
    DELETE_ROLES,
    MAX_ID,
    READ_ROLES,
    WRITE_ROLES,
    DatasetConflict,
    create_dataset,
    delete_dataset,
    find_dataset,
    list_datasets,
    update_dataset,
)
from app.services.investigation import QueryError


dataset_pages = Blueprint("dataset_pages", __name__, url_prefix="/manage/datasets")


@dataset_pages.before_request
def require_session():
    g.user = identity()
    if g.user is None and request.method in {"GET", "HEAD"}:
        return redirect(url_for("dashboard", workspace="logs"))
    if g.user is None or g.user.role not in READ_ROLES:
        abort(403)


@dataset_pages.after_request
def private_page(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def localized_fields(form):
    for field in form:
        field.label.text = translate(field.label.text)
        field.errors = [translate(error) for error in field.errors]
        if field.type == "SelectField":
            field.choices = [(value, translate(label)) for value, label in field.choices]
    return form


@dataset_pages.route("", methods=["GET", "POST"])
def index():
    can_write = g.user.role in WRITE_ROLES
    if request.method == "POST" and not can_write:
        abort(403)
    form = DatasetCreateForm() if can_write else None
    if form and form.validate_on_submit():
        data = {key: form[key].data for key in ("name", "dataset_key", "data_mode")}
        if form.source_id.data is not None:
            data["source_id"] = form.source_id.data
        try:
            create_dataset(db.session, g.user, data)
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("That dataset key already exists for this source.", "danger")
        except QueryError as error:
            db.session.rollback()
            flash(str(error), "danger")
        else:
            flash("Dataset created.", "success")
            return redirect(url_for("dataset_pages.index"), code=303)
    after_id = request.args.get("after_id", 0, type=int)
    if not 0 <= after_id <= MAX_ID:
        abort(400)
    rows, next_id = list_datasets(db.session, g.user, after_id=after_id)
    return render_template(
        "dataset_pages/index.html",
        rows=rows,
        next_id=next_id,
        form=localized_fields(form) if form else None,
        can_write=can_write,
        can_delete=g.user.role in DELETE_ROLES,
        viewed_at=datetime.now(timezone.utc),
    ), (400 if request.method == "POST" else 200)


@dataset_pages.route("/<int:dataset_id>/<any(rename,delete):action>", methods=["GET", "POST"])
def edit(dataset_id, action):
    removing = action == "delete"
    if g.user.role not in (DELETE_ROLES if removing else WRITE_ROLES):
        abort(403)
    if not 1 <= dataset_id <= MAX_ID:
        abort(404)
    dataset = find_dataset(db.session, g.user, dataset_id)
    form = DatasetDeleteForm() if removing else DatasetRenameForm(obj=dataset)
    if form.validate_on_submit():
        try:
            if removing:
                delete_dataset(db.session, g.user, dataset_id)
            else:
                update_dataset(db.session, g.user, dataset_id, {"name": form.name.data})
            db.session.commit()
        except (QueryError, DatasetConflict) as error:
            db.session.rollback()
            flash(str(error), "danger")
            return render_template(
                "dataset_pages/edit.html", form=localized_fields(form), dataset=dataset, action=action
            ), 409
        except IntegrityError:
            db.session.rollback()
            flash("Related data prevented this change.", "danger")
            return render_template(
                "dataset_pages/edit.html", form=localized_fields(form), dataset=dataset, action=action
            ), 409
        flash("Empty dataset deleted." if removing else "Dataset renamed.", "success")
        return redirect(url_for("dataset_pages.index"), code=303)
    return render_template(
        "dataset_pages/edit.html", form=localized_fields(form), dataset=dataset, action=action
    ), (400 if request.method == "POST" else 200)


def register_page_errors(app):
    """Render HTML for browser navigation and retain the existing JSON contract."""

    def error_page(error):
        browser = request.accept_mimetypes["text/html"] > request.accept_mimetypes["application/json"]
        if browser and not request.path.startswith(("/api/", "/forms/")):
            return render_template("error_page.html", code=error.code, title=error.name), error.code
        return {
            "error": {"code": error.name.lower().replace(" ", "_"), "message": error.description}
        }, error.code

    for code in (400, 403, 404, 405, 500):
        app.register_error_handler(code, error_page)
