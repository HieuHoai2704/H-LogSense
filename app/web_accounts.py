"""Accounts: staff and administrator sign-in, sign-up with approval, password reset and user management.

Anyone may sign up; the account stays pending (it cannot sign in) until an administrator approves it.
Administrators can also create accounts directly.

Every page of the application sits behind the sign-in page (``require_login``): opening the app shows
the sign-in page first, and signing out ends access to every workspace at once.
"""

from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.forms import (
    ActionForm,
    ForgotPasswordForm,
    LoginForm,
    LogoutForm,
    RegisterForm,
    ResetPasswordForm,
    UserCreateForm,
    UserDeleteForm,
    UserEditForm,
)
from app.i18n import translate
from app.security import (
    auth_available,
    authenticate,
    identity,
    login_rate_limited,
    service_token_valid,
    start_session,
)
from app.services.account_mail import send_account_mail

accounts = Blueprint("accounts", __name__, url_prefix="/account")

STAFF_ROLES = ("staff",)
ADMIN_ROLES = ("admin",)
RESET_SALT = "h-logsen-password-reset"
RESET_SECONDS = 3600
PAGE_SIZE = 20
# Reachable without a session: the sign-in pages, assets, the language switch and health checks.
PUBLIC_ENDPOINTS = {
    "accounts.login",
    "accounts.admin_login",
    "accounts.register",
    "accounts.forgot",
    "accounts.reset",
    "static",
    "bootstrap.static",
    "locale_pages.select_language",
    "security.login",
    "database_health",
}


def localized(form):
    for field in form:
        field.label.text = translate(field.label.text)
        field.errors = [translate(error) for error in field.errors]
        if field.type in {"SelectField", "SelectMultipleField"}:
            field.choices = [(value, translate(label)) for value, label in field.choices]
    return form


def safe_next(value):
    """A same-site path to return to after signing in, or None."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return None
    parts = urlsplit(value)
    if parts.scheme or parts.netloc or parts.path.startswith("/account/"):
        return None
    return value


def require_login():
    """Default deny: without a signed-in account only the public endpoints answer."""
    if not current_app.config.get("LOGIN_REQUIRED", True):
        return None
    if request.endpoint is None or request.endpoint in PUBLIC_ENDPOINTS:
        return None
    # Service clients of the read API use the configured service token (see authorized_datasets).
    if not request.path.startswith("/api/local/") and service_token_valid():
        return None
    g.account = identity()
    if g.account is not None:
        return None
    fragment = request.headers.get("X-Workspace-Fragment") == "1"
    if request.path.startswith(("/api/", "/forms/")) or fragment or request.method not in {"GET", "HEAD"}:
        response = jsonify(error={"code": "login_required", "message": translate("Sign in to continue.")})
        response.headers["Cache-Control"] = "no-store"
        return response, 401
    target = request.full_path if request.query_string else request.path
    return redirect(url_for("accounts.login", next=None if target == "/" else target))


def account_context():
    if not has_request_context():  # emails rendered by workers have no signed-in account
        return {"current_account": None, "logout_form": None, "account_is_admin": False}
    account = g.get("account") if "account" in g else identity()
    return {
        "current_account": account,
        "logout_form": LogoutForm() if account is not None else None,
        "account_is_admin": account is not None and account.role in ADMIN_ROLES,
    }


def initialize_accounts(app):
    # Every served page needs a signed-in account. Test apps exercise features directly unless a test
    # turns the gate on.
    app.config.setdefault("LOGIN_REQUIRED", not app.testing)
    app.register_blueprint(accounts)
    app.before_request(require_login)
    app.context_processor(account_context)


@accounts.after_request
def private(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def landing(user, portal):
    if portal == "admin":
        if user.role == "admin":
            return url_for("accounts.users")
        return url_for("dataset_pages.index")
    return url_for("dashboard")


def portal_form(portal):
    """The sign-in form of one portal; the administrator form carries a prefix (both share one page)."""
    return LoginForm(
        prefix="admin" if portal == "admin" else "", portal=portal, next=request.args.get("next", "")
    )


def auth_page(mode, login_form=None, status=200, signup_form=None):
    """The sign-in card in one of its modes: "staff", "signup" or "admin" (all three forms are on it)."""
    forms = {name: portal_form(name) for name in ("staff", "admin")}
    if login_form is not None:
        forms[mode] = login_form
    return render_template(
        "account/auth.html",
        mode=mode,
        portal="admin" if mode == "admin" else "staff",
        staff_form=localized(forms["staff"]),
        admin_form=localized(forms["admin"]),
        signup_form=localized(signup_form or RegisterForm(prefix="signup")),
        accounts_ready=auth_available(),
    ), status


def sign_in(portal):
    if identity() is not None and request.method == "GET":
        return redirect(url_for("dashboard"))
    form = portal_form(portal)
    if request.method == "POST":
        if not auth_available():  # the page itself explains how to start the database
            return auth_page(portal, form, status=503)
        if not form.validate_on_submit():
            return auth_page(portal, form, status=400)
        if login_rate_limited():
            form.password.errors.append("Too many sign-in attempts. Wait a minute and try again.")
            return auth_page(portal, form, status=429)
        user = authenticate(form.username.data, form.password.data)
        if user is None:
            if awaiting_approval(form.username.data, form.password.data):
                form.username.errors.append("Your account is waiting for administrator approval.")
                return auth_page(portal, form, status=403)
            form.password.errors.append("Incorrect username or password.")
            return auth_page(portal, form, status=401)
        expected = ADMIN_ROLES if portal == "admin" else STAFF_ROLES
        if user.role not in expected:
            form.username.errors.append(
                "This is a staff account. Use staff sign-in."
                if portal == "admin"
                else "This is an administrator account. Use administrator sign-in."
            )
            return auth_page(portal, form, status=403)
        start_session(user)
        flash("Signed in.", "success")
        return redirect(safe_next(form.next.data) or landing(user, portal), code=303)
    return auth_page(portal, form)


def awaiting_approval(username, password):
    """True only for the right password of a signed-up account that is not approved yet."""
    from app.domain import User

    user = db.session.scalar(select(User).where(User.username == username))
    return bool(user and user.pending and check_password_hash(user.password_hash, password))


def all_dataset_grants(user_id):
    from app.domain import UserDataset

    return [UserDataset(user_id=user_id, dataset_id=row[0]) for row in dataset_choices()]


def notify_administrators(user):
    """Tell every active administrator with an email that an account waits for approval."""
    from app.domain import User

    for admin in db.session.scalars(
        select(User).where(User.role == "admin", User.active.is_(True), User.email.is_not(None))
    ):
        send_account_mail(
            "New account waiting for approval",
            admin.email,
            "mail/approval_request",
            username=user.username,
            email=user.email,
            review_url=url_for("accounts.users", state="pending", _external=True),
        )


@accounts.route("/register", methods=["GET", "POST"])
def register():
    from app.domain import User

    if identity() is not None and request.method == "GET":
        return redirect(url_for("dashboard"))
    form = RegisterForm(prefix="signup")
    status = 200
    if request.method == "POST":
        status = 400
        if not auth_available():
            flash("Accounts need the MySQL database. Start the demo environment first.", "danger")
            status = 503
        elif form.validate_on_submit():
            if login_rate_limited():
                form.username.errors.append("Too many requests. Wait a minute and try again.")
                status = 429
            elif db.session.scalar(
                select(User.id).where(or_(User.username == form.username.data, User.email == form.email.data))
            ):
                form.username.errors.append("That username or email is already registered.")
                status = 409
            else:
                user = User(
                    username=form.username.data,
                    email=form.email.data,
                    password_hash=generate_password_hash(form.password.data),
                    role="staff",
                    active=False,
                    pending=True,
                    auth_version=1,
                )
                db.session.add(user)
                db.session.commit()
                send_account_mail(
                    "Registration received",
                    user.email,
                    "mail/registered",
                    username=user.username,
                )
                notify_administrators(user)
                flash("Registration received. You can sign in once an administrator approves it.", "success")
                return redirect(url_for("accounts.login"), code=303)
    return auth_page("signup", status=status, signup_form=form)


@accounts.route("/login", methods=["GET", "POST"])
def login():
    return sign_in("staff")


@accounts.route("/admin", methods=["GET", "POST"])
def admin_login():
    return sign_in("admin")


@accounts.post("/logout")
def logout():
    form = LogoutForm()
    if not form.validate_on_submit():
        abort(400)
    session.clear()
    flash("Signed out.", "success")
    return redirect(url_for("accounts.login"), code=303)


def reset_serializer():
    return URLSafeTimedSerializer(current_app.secret_key, salt=RESET_SALT)


@accounts.route("/forgot", methods=["GET", "POST"])
def forgot():
    from app.domain import User

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        if not auth_available():
            flash("Accounts need the MySQL database. Start the demo environment first.", "danger")
            return render_template("account/forgot.html", form=localized(form)), 503
        if login_rate_limited():
            form.email.errors.append("Too many requests. Wait a minute and try again.")
            return render_template("account/forgot.html", form=localized(form)), 429
        user = db.session.scalar(select(User).where(User.email == form.email.data))
        if user is not None and user.active:
            token = reset_serializer().dumps({"user": user.id, "version": user.auth_version})
            send_account_mail(
                "Reset your password",
                user.email,
                "mail/reset",
                username=user.username,
                reset_url=url_for("accounts.reset", token=token, _external=True),
                minutes=RESET_SECONDS // 60,
            )
        # The same answer whether or not the address has an account.
        flash("If that email belongs to an account, a reset link has been sent.", "info")
        return redirect(url_for("accounts.login"), code=303)
    return render_template("account/forgot.html", form=localized(form)), (
        400 if request.method == "POST" else 200
    )


@accounts.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    from app.domain import User

    if not auth_available() or len(token) > 512:
        abort(404)
    try:
        claims = reset_serializer().loads(token, max_age=RESET_SECONDS)
    except SignatureExpired:
        flash("This reset link has expired. Request a new one.", "danger")
        return redirect(url_for("accounts.forgot"), code=303)
    except BadSignature:
        abort(404)
    user = db.session.get(User, claims.get("user")) if isinstance(claims, dict) else None
    # A reset bumps auth_version, so each link works once and older sessions end.
    if user is None or not user.active or claims.get("version") != user.auth_version:
        flash("This reset link has already been used. Request a new one.", "danger")
        return redirect(url_for("accounts.forgot"), code=303)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = generate_password_hash(form.password.data)
        user.auth_version += 1
        db.session.commit()
        session.clear()
        flash("Password changed. Sign in with your new password.", "success")
        return redirect(
            url_for("accounts.admin_login" if user.role in ADMIN_ROLES else "accounts.login"), 303
        )
    return render_template("account/reset.html", form=localized(form), username=user.username), (
        400 if request.method == "POST" else 200
    )


# ---- Administrator console: user CRUD, search and pagination ----


def require_admin():
    user = identity()
    if user is None or user.role != "admin":
        abort(403)
    g.user = user
    return user


def dataset_choices():
    from app.models import Dataset

    return [
        (row.id, f"{row.name} · {row.dataset_key}")
        for row in db.session.scalars(select(Dataset).order_by(Dataset.id))
    ]


@accounts.get("/admin/users")
def users():
    from app.domain import User

    require_admin()
    query_text = (request.args.get("q") or "").strip()[:100]
    role = request.args.get("role", "")
    page = request.args.get("page", 1, type=int)
    if page < 1 or page > 100000:
        abort(400)
    statement = select(User).order_by(User.id)
    if query_text:
        pattern = "%" + query_text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        statement = statement.where(or_(User.username.like(pattern), User.email.like(pattern)))
    if role in {"staff", "admin"}:
        statement = statement.where(User.role == role)
    state = request.args.get("state", "")
    if state == "pending":
        statement = statement.where(User.pending.is_(True))
    elif state == "active":
        statement = statement.where(User.active.is_(True))
    elif state == "disabled":
        statement = statement.where(User.active.is_(False), User.pending.is_(False))
    else:
        state = ""
    pages = db.paginate(statement, page=page, per_page=PAGE_SIZE, error_out=False)
    counts = dict(db.session.execute(select(User.role, func.count()).group_by(User.role)).tuples().all())
    return render_template(
        "account/users.html",
        workspace_view="users",
        pages=pages,
        state=state,
        pending=db.session.scalar(select(func.count()).select_from(User).where(User.pending.is_(True))),
        action_form=ActionForm(),
        q=query_text,
        role=role,
        counts=counts,
        form=localized(UserCreateForm()),
    )


@accounts.post("/admin/users")
def create_user():
    from app.domain import User, UserDataset

    require_admin()
    form = UserCreateForm()
    if form.validate_on_submit():
        clash = db.session.scalar(
            select(User.id).where(or_(User.username == form.username.data, User.email == form.email.data))
        )
        if clash:
            flash("That username or email is already registered.", "danger")
        else:
            user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=generate_password_hash(form.password.data),
                role=form.role.data,
                active=True,
                auth_version=1,
            )
            db.session.add(user)
            db.session.flush()
            # Staff use the whole application: a new account can open every existing dataset. The
            # administrator can narrow this on the account's edit page.
            db.session.add_all(UserDataset(user_id=user.id, dataset_id=row[0]) for row in dataset_choices())
            db.session.commit()
            portal = "accounts.admin_login" if user.role in ADMIN_ROLES else "accounts.login"
            send_account_mail(
                "Welcome",
                user.email,
                "mail/welcome",
                username=user.username,
                role=user.role,
                sign_in_url=url_for(portal, _external=True),
            )
            flash("Account created. A welcome email has been sent.", "success")
            return redirect(url_for("accounts.users"), code=303)
    for field in form:
        for error in field.errors:
            flash(f"{translate(field.label.text)}: {translate(error)}", "danger")
    return redirect(url_for("accounts.users"), code=303)


@accounts.route("/admin/users/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):
    from app.domain import User, UserDataset

    admin = require_admin()
    user = db.session.get(User, user_id) or abort(404)
    form = UserEditForm(obj=user)
    form.datasets.choices = dataset_choices()
    current = set(db.session.scalars(select(UserDataset.dataset_id).where(UserDataset.user_id == user.id)))
    if request.method == "GET":
        form.datasets.data = sorted(current)
    delete_form = UserDeleteForm(prefix="delete")
    if form.validate_on_submit():
        if user.id == admin.id and (form.role.data != "admin" or not form.active.data):
            flash("You cannot remove your own administrator access.", "danger")
        else:
            changed_access = form.role.data != user.role or bool(form.active.data) != user.active
            if form.email.data and form.email.data != user.email:
                taken = db.session.scalar(
                    select(User.id).where(User.email == form.email.data, User.id != user.id)
                )
                if taken:
                    flash("That email is already registered.", "danger")
                    return render_user(user, form, delete_form, 409)
            user.email = form.email.data or None
            user.role, user.active = form.role.data, bool(form.active.data)
            if user.active and user.pending:
                user.pending = False  # activating a signed-up account approves it
            if form.password.data:
                user.password_hash = generate_password_hash(form.password.data)
                changed_access = True
            if changed_access and user.id != admin.id:
                user.auth_version += 1  # signs the account out everywhere
            wanted = set(form.datasets.data or [])
            if wanted - current:
                db.session.add_all(
                    UserDataset(user_id=user.id, dataset_id=d) for d in sorted(wanted - current)
                )
            if current - wanted:
                db.session.execute(
                    delete(UserDataset).where(
                        UserDataset.user_id == user.id, UserDataset.dataset_id.in_(current - wanted)
                    )
                )
            db.session.commit()
            flash("Account updated.", "success")
            return redirect(url_for("accounts.users"), code=303)
    return render_user(user, form, delete_form, 400 if request.method == "POST" else 200)


def render_user(user, form, delete_form, status):
    return render_template(
        "account/user_edit.html",
        workspace_view="users",
        user=user,
        form=localized(form),
        delete_form=localized(delete_form),
    ), status


@accounts.post("/admin/users/<int:user_id>/<any(approve,reject):decision>")
def decide(user_id, decision):
    """Approve a signed-up account (it opens every dataset) or reject it (the request is deleted)."""
    from app.domain import User

    require_admin()
    if not ActionForm().validate_on_submit():
        abort(400)
    user = db.session.get(User, user_id) or abort(404)
    if not user.pending:
        flash("This account is not waiting for approval.", "danger")
        return redirect(url_for("accounts.users"), code=303)
    email, username = user.email, user.username
    if decision == "approve":
        user.pending, user.active = False, True
        db.session.add_all(all_dataset_grants(user.id))
        db.session.commit()
        if email:
            send_account_mail(
                "Account approved",
                email,
                "mail/approved",
                username=username,
                sign_in_url=url_for("accounts.login", _external=True),
            )
        flash("Account approved. An email has been sent.", "success")
    else:
        db.session.delete(user)
        db.session.commit()
        if email:
            send_account_mail("Registration declined", email, "mail/declined", username=username)
        flash("Registration rejected.", "success")
    return redirect(
        request.form.get("back") if safe_back(request.form.get("back")) else url_for("accounts.users"), 303
    )


def safe_back(value):
    return isinstance(value, str) and value.startswith("/account/admin/users") and "//" not in value


@accounts.post("/admin/users/<int:user_id>/delete")
def delete_user(user_id):
    from app.domain import User, UserDataset

    admin = require_admin()
    user = db.session.get(User, user_id) or abort(404)
    form = UserDeleteForm(prefix="delete")
    if not form.validate_on_submit():
        flash("Confirm account deletion.", "danger")
        return redirect(url_for("accounts.edit_user", user_id=user_id), code=303)
    if user.id == admin.id:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("accounts.edit_user", user_id=user_id), code=303)
    try:
        db.session.execute(delete(UserDataset).where(UserDataset.user_id == user.id))
        db.session.delete(user)
        db.session.commit()
    except (IntegrityError, OperationalError):
        # Referenced by alerts or audit records, or the database account may not delete users.
        db.session.rollback()
        flash("This account cannot be deleted. Deactivate it instead.", "danger")
        return redirect(url_for("accounts.edit_user", user_id=user_id), code=303)
    flash("Account deleted.", "success")
    return redirect(url_for("accounts.users"), code=303)
