"""Create the LogSense AI Flask application."""

import secrets

from flask import Flask, jsonify, render_template, request

from app.access import AccessDenied, authorize_source
from app.api.anomalies import api
from app.presentation import context, payload
from app.services.investigation import QueryError, build, query

from config import Config


def create_app():
    """Build an application with its configuration and initial routes."""
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config['EVIDENCE_CURSOR_SECRET'] = secrets.token_hex(32)
    app.register_blueprint(api)

    @app.errorhandler(AccessDenied)
    def forbidden(error):
        response = jsonify(error={'code': 'forbidden', 'message': str(error)})
        response.headers['Cache-Control'] = 'no-store'
        return response, 403

    @app.get("/")
    def dashboard():
        try:
            authorize_source(request.args.get('source', 'demo'))
            view = build(query(request.args))
        except QueryError as error:
            if request.headers.get('X-Workspace-Fragment') == '1':
                return jsonify(error={'code': 'invalid_query', 'message': str(error)}), 400
            return render_template('query_error.html', message=str(error)), 400
        if request.headers.get('X-Workspace-Fragment') == '1':
            return jsonify(payload(view))
        return render_template('dashboard.html', **context(view))

    return app
