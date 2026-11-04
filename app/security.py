"""Local user/session authentication and dataset authorization, default deny."""

import hashlib
import os
import secrets
import time
from collections import defaultdict, deque
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request, session
from sqlalchemy import select
from werkzeug.security import check_password_hash

from app.extensions import db

security_api = Blueprint("security", __name__)
attempts = defaultdict(deque)


def identity():
    from app.domain import User

    if "sqlalchemy" not in current_app.extensions or not session.get("user_id"):
        return None
    user = db.session.get(User, session["user_id"])
    if (
        user is None
        or not user.active
        or session.get("auth_version") != user.auth_version
    ):
        return None
    return user


def authorized_datasets():
    from app.domain import UserDataset

    user = identity()
    if user:
        return set(
            db.session.scalars(
                select(UserDataset.dataset_id).where(UserDataset.user_id == user.id)
            )
        )
    token = current_app.config.get("DATABASE_READ_TOKEN") or os.environ.get(
        "DATABASE_READ_TOKEN"
    )
    supplied = request.headers.get("Authorization", "")
    if token and secrets.compare_digest(
        supplied.encode(), ("Bearer " + token).encode()
    ):
        return set(current_app.config.get("DATABASE_ALLOWED_DATASETS", ()))
    return set()


def require_dataset(dataset_id):
    if dataset_id not in authorized_datasets():
        raise Forbidden()


class Forbidden(Exception):
    pass


def roles(*allowed):
    def decorate(function):
        @wraps(function)
        def checked(*args, **kwargs):
            user = identity()
            if user is None or user.role not in allowed:
                raise Forbidden()
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                token = request.headers.get("X-CSRF-Token", "")
                if not token or not secrets.compare_digest(
                    token.encode(), session.get("csrf", "").encode()
                ):
                    raise Forbidden()
            g.user = user
            return function(*args, **kwargs)

        return checked

    return decorate


@security_api.post("/api/v1/auth/login")
def login():
    if not current_app.secret_key or "sqlalchemy" not in current_app.extensions:
        return jsonify(error={"code": "auth_unavailable"}), 503
    from app.domain import User

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error={"code": "invalid_credentials"}), 401
    username, password = data.get("username"), data.get("password")
    if (
        not isinstance(username, str)
        or not isinstance(password, str)
        or len(username) > 100
        or len(password) > 1024
    ):
        return jsonify(error={"code": "invalid_credentials"}), 401
    key = hashlib.sha256((request.remote_addr or "").encode()).hexdigest()
    now = time.monotonic()
    if len(attempts) > 10000:
        attempts.clear()
    queue = attempts[key]
    while queue and now - queue[0] > 60:
        queue.popleft()
    if len(queue) >= 5:
        return jsonify(error={"code": "rate_limited"}), 429
    queue.append(now)
    user = db.session.scalar(select(User).where(User.username == username))
    # Fixed dummy hash work prevents a trivial missing-user fast path.
    valid = check_password_hash(
        user.password_hash if user else current_app.config["DUMMY_PASSWORD_HASH"],
        password,
    )
    if user is None or not user.active or not valid:
        return jsonify(error={"code": "invalid_credentials"}), 401
    session.clear()
    session.update(
        user_id=user.id, auth_version=user.auth_version, csrf=secrets.token_hex(32)
    )
    return jsonify(
        user={"id": user.id, "username": user.username, "role": user.role},
        csrf_token=session["csrf"],
    )


@security_api.get("/api/v1/auth/me")
@roles("viewer", "analyst", "manager", "admin")
def me():
    return jsonify(
        user={"id": g.user.id, "username": g.user.username, "role": g.user.role},
        csrf_token=session["csrf"],
        datasets=sorted(authorized_datasets()),
    )


@security_api.post("/api/v1/auth/logout")
@roles("viewer", "analyst", "manager", "admin")
def logout():
    session.clear()
    return jsonify(status="logged_out")


def initialize_security(app):
    # This deterministic public dummy is not an account credential.
    from werkzeug.security import generate_password_hash

    app.config.setdefault(
        "DUMMY_PASSWORD_HASH", generate_password_hash(secrets.token_hex(32))
    )
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE") == "1",
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    if os.environ.get("DATABASE_ALLOWED_DATASETS"):
        try:
            allowed = tuple(
                int(x) for x in os.environ["DATABASE_ALLOWED_DATASETS"].split(",")
            )
            if len(allowed) > 100 or any(not 1 <= x < 2**63 for x in allowed):
                raise ValueError()
            app.config["DATABASE_ALLOWED_DATASETS"] = allowed
        except ValueError:
            raise ValueError("Invalid dataset allow-list.") from None
    app.register_blueprint(security_api)

    @app.errorhandler(Forbidden)
    def denied(error):
        return jsonify(
            error={
                "code": "forbidden",
                "message": "Authentication and dataset permission required.",
            }
        ), 403

    from sqlalchemy.exc import SQLAlchemyError

    @app.errorhandler(SQLAlchemyError)
    def unavailable(error):
        if "sqlalchemy" in app.extensions:
            db.session.rollback()
        return jsonify(
            error={
                "code": "database_unavailable",
                "message": "Database operation unavailable; retry safely.",
            }
        ), 503

    from werkzeug.exceptions import RequestEntityTooLarge

    @app.errorhandler(RequestEntityTooLarge)
    def oversized(error):
        return jsonify(
            error={
                "code": "payload_too_large",
                "message": "Request exceeds the configured size limit.",
            }
        ), 413

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(
            error={
                "code": error.name.lower().replace(" ", "_"),
                "message": error.description,
            }
        ), error.code

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response
