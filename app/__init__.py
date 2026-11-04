"""Create the LogSense AI Flask application."""

import secrets
import os

from flask import Flask, jsonify, render_template, request

from app.access import AccessDenied, authorize_source
from app.api.anomalies import api
from app.presentation import context, payload
from app.services.investigation import QueryError, build, query

from config import Config


def create_app(config_overrides=None):
    """Build an application with its configuration and initial routes."""
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_overrides:
        app.config.update(config_overrides)
    app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY') or app.config.get('SECRET_KEY')
    app.config['EVIDENCE_CURSOR_SECRET'] = app.config['SECRET_KEY'] or secrets.token_hex(32)
    from app.database import configure_database
    configure_database(app)
    from app.security import initialize_security
    initialize_security(app)
    app.register_blueprint(api)

    @app.errorhandler(AccessDenied)
    def forbidden(error):
        response = jsonify(error={'code': 'forbidden', 'message': str(error)})
        response.headers['Cache-Control'] = 'no-store'
        return response, 403

    @app.get("/")
    def dashboard():
        if request.args.get('workspace') == 'logs':
            return render_template('logs.html')
        from app.services.mysql_investigation import is_mysql,build as mysql_build,state as mysql_state
        if is_mysql(request.args):
            try:
                view=mysql_build(mysql_state(request.args))
            except QueryError as error:
                return render_template('query_error.html',message=str(error)),400
            return render_template('dashboard.html',**context(view))
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
