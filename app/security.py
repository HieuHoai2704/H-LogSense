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
        SESSION_COOKIE_SECURE=app.config.get("SESSION_COOKIE_SECURE") or os.environ.get("COOKIE_SECURE") == "1",
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

    from flask import render_template
    from sqlalchemy.exc import DataError, IntegrityError, SQLAlchemyError
    from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
    from app.i18n import translate

    def failure(code, message, status, title):
        """JSON for API clients; the HTML error page for browser navigation (never raw JSON)."""
        browser = request.accept_mimetypes["text/html"] > request.accept_mimetypes["application/json"]
        if browser and not request.path.startswith(("/api/", "/forms/")):
            return render_template("error_page.html", code=status, title=title), status
        response = jsonify(error={"code": code, "message": translate(message)})
        response.headers["Cache-Control"] = "no-store"
        return response, status

    @app.errorhandler(Forbidden)
    def denied(error):
        return failure("forbidden", "Authentication and dataset permission required.", 403, "Forbidden")

    @app.errorhandler(SQLAlchemyError)
    def unavailable(error):
        if "sqlalchemy" in app.extensions:
            db.session.rollback()
        # Permanent data errors are not "retry safely" outages.
        if isinstance(error, IntegrityError):
            return failure("conflict", "The change conflicts with existing data.", 409, "Conflict")
        if isinstance(error, DataError):
            return failure("invalid_data", "A value is outside the stored range or format.", 400, "Bad Request")
        return failure("database_unavailable", "Database operation unavailable; retry safely.", 503,
                       "Service Unavailable")

    @app.errorhandler(RequestEntityTooLarge)
    def oversized(error):
        return failure("payload_too_large", "Request exceeds the configured size limit.", 413, "Payload Too Large")

    @app.errorhandler(HTTPException)
    def http_error(error):
        return failure(error.name.lower().replace(" ", "_"), error.description, error.code, error.name)

    @app.after_request
    def security_headers(response):
        if response.mimetype == "text/html" and not response.direct_passthrough:
            # Content-Security-Policy: same-origin scripts only. Server-rendered inline scripts
            # (Flask-Moment) get a per-response nonce; user data is autoescaped, so it can never
            # produce a literal <script> tag. The workbench token shares this origin, so an XSS
            # must not be able to run code.
            nonce = secrets.token_urlsafe(16)
            body = response.get_data(as_text=True)
            if "<script>" in body:
                response.set_data(body.replace("<script>", f'<script nonce="{nonce}">'))
            # The native desktop window drives the page through pywebview's evaluate_js, which runs
            # host code through eval(); only that mode allows it. Browser mode stays strict.
            workbench = current_app.extensions.get("workbench") or {}
            evaluate = " 'unsafe-eval'" if workbench.get("desktop") else ""
            response.headers["Content-Security-Policy"] = (
                f"default-src 'self'; script-src 'self' 'nonce-{nonce}'{evaluate}; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; worker-src 'self' blob:; "
                "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.path.startswith("/api/") or (request.path == "/" and request.args.get("source", "").startswith("db-")):
            # Private MySQL-backed pages and API data are never cached.
            response.headers["Cache-Control"] = "no-store"
        return response
