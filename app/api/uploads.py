"""Authenticated multipart uploads; HTTP validates/stages but never imports."""

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Dataset
from app.security import roles, require_dataset
from app.services.bgl_ingestion import import_lease, ImportBusyError
from app.services.uploads import (
    MAX_REQUEST_BYTES, MAX_ATTEMPTS, UploadError, stage_file, discard, queue_upload,
    job_for_upload, serialize_job, load_bundle,
)

uploads_api = Blueprint('uploads', __name__)


@uploads_api.errorhandler(UploadError)
def invalid(error):
    db.session.rollback()
    return jsonify(error={'code': error.code, 'message': error.message}), error.status


@uploads_api.post('/api/v1/uploads')
@roles('analyst', 'manager', 'admin')
def upload():
    # Override the request only. Login and unrelated endpoints keep their global
    # 1MiB cap. Set limits before accessing form/files in the multipart parser.
    request.max_content_length = MAX_REQUEST_BYTES
    request.max_form_memory_size = 256 * 1024
    request.max_form_parts = 8
    if request.mimetype != 'multipart/form-data':
        raise UploadError('invalid_form', 'Use multipart/form-data with one source file.', 400)
    from app.forms import UploadForm
    form = UploadForm()
    if not form.validate_on_submit():
        return jsonify(error={'code': 'invalid_form', 'message': 'Valid fields, file and signed form CSRF token required.', 'fields': form.errors}), 400
    if (set(request.form) - {'csrf_token', 'dataset_id', 'idempotency_key'} or set(request.files) != {'file'}
            or len(request.files.getlist('file')) != 1
            or any(len(request.form.getlist(key)) != 1 for key in request.form)):
        raise UploadError('invalid_form', 'Only one file and the supported fields are accepted.', 400)
    dataset_id = form.dataset_id.data
    require_dataset(dataset_id)
    if db.session.get(Dataset, dataset_id) is None:
        raise UploadError('dataset_unavailable', 'Dataset unavailable.', 409)
    bundle = stage_file(form.file.data)
    accepted = False
    try:
        job, created = queue_upload(db.session, g.user, dataset_id, form.idempotency_key.data, bundle)
        db.session.commit()
        accepted = created
        response = serialize_job(db.session, job)
        return jsonify(response), 202 if created else 200
    except IntegrityError:
        db.session.rollback()
        raise UploadError('upload_conflict', 'Upload registration conflicted; retry the same key.', 409) from None
    finally:
        if not accepted:
            discard(bundle)


@uploads_api.get('/api/v1/uploads/<upload_id>')
@roles('viewer', 'analyst', 'manager', 'admin')
def status(upload_id):
    job = job_for_upload(db.session, upload_id)
    require_dataset(job.dataset_id)
    return jsonify(serialize_job(db.session, job))


@uploads_api.post('/api/v1/uploads/<upload_id>/retry')
@roles('analyst', 'manager', 'admin')
def retry(upload_id):
    job = job_for_upload(db.session, upload_id)
    require_dataset(job.dataset_id)
    # The exact worker lease prevents retrying an active import. An abruptly
    # exiting process releases its named lock, enabling explicit safe recovery.
    try:
        with import_lease(db.engine, 'upload-job:' + str(job.id)):
            db.session.rollback()
            job = job_for_upload(db.session, upload_id, lock=True)
            require_dataset(job.dataset_id)
            result = job.result or {}
            if job.state not in {'failed', 'running'} or result.get('attempts', 0) >= MAX_ATTEMPTS or job.error_code == 'upload_integrity':
                raise UploadError('job_not_retryable', 'Upload cannot be retried in its current state.', 409)
            load_bundle(upload_id, job.configuration)
            job.state, job.error_code = 'queued', None
            db.session.commit()
    except ImportBusyError:
        raise UploadError('worker_active', 'Upload worker is still active.', 409) from None
    return jsonify(serialize_job(db.session, job)), 202


