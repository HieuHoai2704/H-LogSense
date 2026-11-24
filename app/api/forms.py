"""Authenticated multipart forms for the existing inline workspace.

Flask-WTF CSRF and the existing role/header CSRF guard are both required.
JSON clients continue using /api/v1/datasets without a form compatibility break.
"""

from flask import Blueprint, Response, g, jsonify, request, url_for
from flask_wtf.csrf import generate_csrf
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.forms import DatasetCreateForm, DatasetDeleteForm, DatasetRenameForm
from app.i18n import translate
from app.security import roles
from app.services.dataset_management import (
    DELETE_ROLES,
    MAX_ID,
    READ_ROLES,
    WRITE_ROLES,
    DatasetConflict,
    create_dataset,
    delete_dataset,
    serialize,
    update_dataset,
)
from app.services.investigation import QueryError, integer

forms_api = Blueprint("forms", __name__)


@forms_api.after_request
def private_form_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@forms_api.errorhandler(QueryError)
def invalid(error):
    db.session.rollback()
    return jsonify(error={"code": "invalid_query", "message": translate(str(error))}), 400


@forms_api.errorhandler(DatasetConflict)
def conflict(error):
    db.session.rollback()
    return jsonify(error={"code": error.code, "message": translate(error.message)}), 409


def validate_form(form_class, allowed_fields):
    if request.mimetype not in {"multipart/form-data", "application/x-www-form-urlencoded"}:
        return None, (jsonify(error={"code": "invalid_form", "message": "Submit a form, not JSON."}), 400)
    if (
        set(request.form) - set(allowed_fields) - {"csrf_token"}
        or request.files
        or any(len(values) != 1 for _, values in request.form.lists())
    ):
        return None, (jsonify(error={"code": "invalid_form", "message": "Unsupported form field."}), 400)
    form = form_class()
    if not form.validate_on_submit():
        return None, (
            jsonify(
                error={
                    "code": "invalid_form",
                    "message": "Correct the form fields and retry.",
                    "fields": form.errors,
                }
            ),
            400,
        )
    return form, None


@forms_api.get("/api/v1/forms/csrf")
@roles(*READ_ROLES)
def csrf():
    return jsonify(csrf_token=generate_csrf())


@forms_api.post("/forms/datasets")
@roles(*WRITE_ROLES)
def create():
    form, denied = validate_form(DatasetCreateForm, {"name", "dataset_key", "data_mode", "source_id"})
    if denied:
        return denied
    values = {"name": form.name.data, "dataset_key": form.dataset_key.data, "data_mode": form.data_mode.data}
    if form.source_id.data is not None:
        values["source_id"] = form.source_id.data
    try:
        dataset = create_dataset(db.session, g.user, values)
        result = serialize(dataset)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DatasetConflict(
            "dataset_conflict", "Dataset key conflicts with an existing registration."
        ) from None
    response = jsonify(dataset=result)
    response.status_code = 201
    response.headers["Location"] = url_for("datasets.detail", dataset_id=result["id"])
    return response


@forms_api.post("/forms/datasets/<int:dataset_id>/rename")
@roles(*WRITE_ROLES)
def rename(dataset_id):
    dataset_id = integer(dataset_id, 1, MAX_ID, "Dataset")
    form, denied = validate_form(DatasetRenameForm, {"name"})
    if denied:
        return denied
    dataset = update_dataset(db.session, g.user, dataset_id, {"name": form.name.data})
    result = serialize(dataset)
    db.session.commit()
    return jsonify(dataset=result)


@forms_api.post("/forms/datasets/<int:dataset_id>/delete")
@roles(*DELETE_ROLES)
def remove(dataset_id):
    dataset_id = integer(dataset_id, 1, MAX_ID, "Dataset")
    form, denied = validate_form(DatasetDeleteForm, {"confirmation"})
    if denied:
        return denied
    try:
        delete_dataset(db.session, g.user, dataset_id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DatasetConflict(
            "dataset_not_empty", "Dataset has related records; deletion is blocked."
        ) from None
    return Response(status=204)
