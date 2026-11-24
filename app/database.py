"""Optional MySQL wiring. No implicit DDL, fallback database or credential output."""

import os

from flask import jsonify
from sqlalchemy import event, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, migrate


def configure_database(app):
    from app import (
        domain,  # noqa: F401
        models,  # noqa: F401 -- register metadata before migrations
    )

    configured = app.config.get("SQLALCHEMY_DATABASE_URI")
    if not configured:
        configured = os.environ.get("TEST_DATABASE_URL" if app.testing else "DATABASE_URL")
    if configured:
        try:
            url = make_url(configured)
            if url.drivername != "mysql+pymysql" or not url.database:
                raise ValueError()
            url = url.update_query_dict({"charset": "utf8mb4"})
        except Exception:
            raise ValueError("A valid mysql+pymysql database URL is required.") from None
        app.config.update(
            SQLALCHEMY_DATABASE_URI=url,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={
                "pool_pre_ping": True,
                "pool_recycle": 1800,
                "hide_parameters": True,
                "connect_args": {
                    "connect_timeout": 5,
                    "read_timeout": 600,
                    "write_timeout": 600,
                },  # a stalled server frees the thread
            },
        )
        db.init_app(app)
        migrate.init_app(app, db, compare_type=True)
        with app.app_context():

            @event.listens_for(db.engine, "connect")
            def utc_session(connection, record):
                with connection.cursor() as cursor:
                    cursor.execute("SET time_zone = '+00:00'")
                    cursor.execute(
                        "SET SESSION sql_mode = 'STRICT_TRANS_TABLES,NO_ZERO_DATE,NO_ZERO_IN_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
                    )

    from app.api.database import database_api

    app.register_blueprint(database_api)
    from app.api.logs import logs_api

    app.register_blueprint(logs_api)
    from app.api.jobs import jobs_api

    app.register_blueprint(jobs_api)
    from app.api.alerts import alerts_api

    app.register_blueprint(alerts_api)
    from app.api.datasets import datasets_api

    app.register_blueprint(datasets_api)
    from app.api.forms import forms_api

    app.register_blueprint(forms_api)
    from app.api.uploads import uploads_api

    app.register_blueprint(uploads_api)

    @app.get("/api/v1/health/database")
    def database_health():
        # No server names, credentials, SQL exceptions, or log data in the response.
        if "sqlalchemy" not in app.extensions:
            return jsonify(status="not_configured"), 503
        try:
            with db.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return jsonify(status="ready")
        except SQLAlchemyError:
            return jsonify(status="unavailable"), 503
