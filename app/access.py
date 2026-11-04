"""Explicit public-demo source policy; private data is not connected or authorized."""
from flask import current_app

from app.services.investigation import QueryError, SOURCES


class AccessDenied(Exception):
    """A configured source is not readable under the current demo policy."""


def authorize_source(source):
    if source not in SOURCES:
        raise QueryError('Unknown source. Private datasets are not connected.')
    if not current_app.config['DEMO_READ_ENABLED'] or source not in current_app.config['PUBLIC_DEMO_SOURCES']:
        raise AccessDenied('Access to this source is denied.')
