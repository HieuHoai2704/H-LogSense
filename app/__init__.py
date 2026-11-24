"""Create the H-logsen Flask application."""

import os
import secrets

from flask import Flask, jsonify, render_template, request

from app.access import AccessDenied, authorize_source
from app.api.anomalies import api
from app.i18n import translate
from app.presentation import context, payload
from app.services.investigation import QueryError, build, query
from config import APP_NAME, PROFILES


def create_app(config_overrides=None):
    """Build an application with its configuration and initial routes."""
    app = Flask(__name__)
    app.jinja_env.globals["app_name"] = APP_NAME
    profile = os.environ.get("LOGSENSE_PROFILE", "development")
    if profile not in PROFILES:
        raise ValueError("LOGSENSE_PROFILE must be development, testing or production.")
    app.config.from_object(PROFILES[profile])
    if config_overrides:
        app.config.update(config_overrides)
    app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or app.config.get("SECRET_KEY")
    app.config["EVIDENCE_CURSOR_SECRET"] = app.config["SECRET_KEY"] or secrets.token_hex(32)
    from app.database import configure_database

    configure_database(app)
    from app.i18n import initialize_i18n
    from app.security import initialize_security

    initialize_security(app)
    initialize_i18n(app)
    app.register_blueprint(api)
    from app.extensions import bootstrap, db, mail, moment
    from app.web_datasets import dataset_pages, register_page_errors

    bootstrap.init_app(app)
    moment.init_app(app)
    mail.init_app(app)
    app.register_blueprint(dataset_pages)
    register_page_errors(app)

    @app.shell_context_processor
    def shell_context():
        from app.models import Dataset, LogEvent

        return {"db": db, "Dataset": Dataset, "LogEvent": LogEvent}

    @app.errorhandler(AccessDenied)
    def forbidden(error):
        response = jsonify(error={"code": "forbidden", "message": translate(str(error))})
        response.headers["Cache-Control"] = "no-store"
        return response, 403

    @app.context_processor
    def workspace_navigation_context():
        return {
            "workspace_has_database": "sqlalchemy" in app.extensions,
            "workbench_enabled": "workbench" in app.extensions,
            "workbench_desktop": app.extensions.get("workbench", {}).get("desktop", False),
        }

    @app.get("/")
    def dashboard():
        if request.args.get("workspace") == "logs":
            return render_template("logs.html")
        project_view = request.args.get("view")
        if request.headers.get("X-Workspace-Fragment") != "1" and (
            not request.args or (len(request.args) == 1 and project_view in {"editor", "settings"})
        ):
            return render_template("project_workspace.html", workspace_view=project_view or "monitor")
        from app.services.mysql_investigation import build as mysql_build, is_mysql, state as mysql_state

        if is_mysql(request.args):
            try:
                view = mysql_build(mysql_state(request.args))
            except QueryError as error:
                return render_template("query_error.html", message=str(error)), 400
            return render_template("dashboard.html", **context(view))
        try:
            authorize_source(request.args.get("source", "demo"))
            view = build(query(request.args))
        except QueryError as error:
            if request.headers.get("X-Workspace-Fragment") == "1":
                return jsonify(error={"code": "invalid_query", "message": translate(str(error))}), 400
            return render_template("query_error.html", message=str(error)), 400
        if request.headers.get("X-Workspace-Fragment") == "1":
            return jsonify(payload(view))
        return render_template("dashboard.html", **context(view))

    return app
