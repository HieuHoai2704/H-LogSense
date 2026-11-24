"""Session/RBAC protected dataset metadata CRUD, separate from Demo fixtures."""

from flask import Blueprint, Response, g, jsonify, request, url_for
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.security import roles
from app.services.investigation import QueryError, integer
from app.services.dataset_management import (
    DatasetConflict, MAX_ID, create_dataset, delete_dataset, find_dataset,
    label, list_datasets, serialize, update_dataset, READ_ROLES, WRITE_ROLES, DELETE_ROLES,
)
from app.i18n import translate

datasets_api = Blueprint('datasets', __name__)


@datasets_api.errorhandler(QueryError)
def invalid(error):
    db.session.rollback()
    return jsonify(error={'code': 'invalid_query', 'message': translate(str(error))}), 400


@datasets_api.errorhandler(DatasetConflict)
def conflict(error):
    db.session.rollback()
    return jsonify(error={'code': error.code, 'message': translate(error.message)}), 409


def body():
    if not request.is_json:
        raise QueryError('A JSON object is required.')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise QueryError('A JSON object is required.')
    return data


@datasets_api.get('/api/v1/datasets')
@roles(*READ_ROLES)
def index():
    if set(request.args) - {'after_id', 'limit', 'q'}:
        raise QueryError('Unknown dataset query parameter.')
    after = integer(request.args.get('after_id', 0), 0, MAX_ID, 'Cursor')
    limit = integer(request.args.get('limit', 50), 1, 100, 'Page size')
    search = request.args.get('q', '').strip()
    if search:
        search = label(search, 'Search', 200)
    rows, cursor = list_datasets(db.session, g.user, after_id=after, limit=limit, search=search)
    return jsonify(items=[serialize(row) for row in rows], next_after_id=cursor)


@datasets_api.get('/api/v1/datasets/<int:dataset_id>')
@roles(*READ_ROLES)
def detail(dataset_id):
    dataset_id = integer(dataset_id, 1, MAX_ID, 'Dataset')
    return jsonify(dataset=serialize(find_dataset(db.session, g.user, dataset_id)))


@datasets_api.post('/api/v1/datasets')
@roles(*WRITE_ROLES)
def create():
    try:
        dataset = create_dataset(db.session, g.user, body())
        result = serialize(dataset)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DatasetConflict('dataset_conflict', 'Dataset key conflicts with an existing registration.') from None
    response = jsonify(dataset=result)
    response.status_code = 201
    response.headers['Location'] = url_for('datasets.detail', dataset_id=result['id'])
    return response


@datasets_api.patch('/api/v1/datasets/<int:dataset_id>')
@roles(*WRITE_ROLES)
def update(dataset_id):
    dataset_id = integer(dataset_id, 1, MAX_ID, 'Dataset')
    dataset = update_dataset(db.session, g.user, dataset_id, body())
    result = serialize(dataset)
    db.session.commit()
    return jsonify(dataset=result)


@datasets_api.delete('/api/v1/datasets/<int:dataset_id>')
@roles(*DELETE_ROLES)
def remove(dataset_id):
    dataset_id = integer(dataset_id, 1, MAX_ID, 'Dataset')
    try:
        delete_dataset(db.session, g.user, dataset_id)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise DatasetConflict('dataset_not_empty', 'Dataset has related records; deletion is blocked.') from None
    return Response(status=204)
