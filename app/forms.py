"""Flask-WTF forms used by the existing inline dataset and upload workflows.

Per-form CSRF remains enabled. REST JSON endpoints retain their existing,
independent session/header CSRF contract rather than disabling form protection.
"""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    SelectMultipleField,
    StringField,
)
from wtforms.validators import (
    AnyOf,
    DataRequired,
    EqualTo,
    InputRequired,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)

MAX_ID = 2**63 - 1


def clean_label(value):
    return value.strip() if isinstance(value, str) else value


def valid_text(form, field):
    value = field.data or ""
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ValidationError("Control characters are not allowed.")
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValidationError("Valid Unicode text is required.") from None


class DatasetCreateForm(FlaskForm):
    name = StringField(
        "Name", filters=[clean_label], validators=[InputRequired(), Length(min=1, max=200), valid_text]
    )
    dataset_key = StringField(
        "Dataset key",
        filters=[clean_label],
        validators=[
            InputRequired(),
            Length(min=1, max=100),
            valid_text,
            Regexp(
                r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z",
                message="Use letters, numbers, dot, underscore or hyphen.",
            ),
        ],
    )
    data_mode = SelectField(
        "Data mode",
        choices=[("unverified", "Unverified"), ("real", "Real source"), ("synthetic", "Synthetic source")],
        default="unverified",
        validators=[InputRequired()],
    )
    source_id = IntegerField("Existing source ID", validators=[Optional(), NumberRange(min=1, max=MAX_ID)])


class DatasetRenameForm(FlaskForm):
    name = StringField(
        "Name", filters=[clean_label], validators=[InputRequired(), Length(min=1, max=200), valid_text]
    )


class DatasetDeleteForm(FlaskForm):
    confirmation = BooleanField(
        "Confirm empty dataset deletion",
        false_values=(False, "false", "", "0"),
        validators=[DataRequired(message="Confirm empty dataset deletion.")],
    )


class UploadForm(FlaskForm):
    dataset_id = IntegerField("Dataset", validators=[InputRequired(), NumberRange(min=1, max=MAX_ID)])
    idempotency_key = StringField(
        "Import reference",
        filters=[clean_label],
        validators=[InputRequired(), Length(min=1, max=100), valid_text],
    )
    file = FileField(
        "BGL source file",
        validators=[FileRequired(), FileAllowed(["txt", "log", "csv"], "Upload a TXT, LOG or CSV file.")],
    )


# Accounts. Usernames and emails are checked with plain patterns: no extra validation package.
USERNAME = Regexp(
    r"[A-Za-z0-9][A-Za-z0-9._-]{2,99}\Z", message="Use 3-100 letters, numbers, dot, underscore or hyphen."
)
EMAIL = Regexp(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]+\Z", message="Enter a valid email address.")
ROLES = [("viewer", "Viewer"), ("analyst", "Analyst"), ("manager", "Manager"), ("admin", "Administrator")]


def lower(value):
    return value.strip().lower() if isinstance(value, str) else value


class LoginForm(FlaskForm):
    username = StringField(
        "Username", filters=[clean_label], validators=[InputRequired(), Length(max=100), valid_text]
    )
    password = PasswordField("Password", validators=[InputRequired(), Length(max=1024)])
    portal = HiddenField(default="staff", validators=[AnyOf(["staff", "admin"])])
    next = HiddenField(validators=[Optional(), Length(max=2000)])


class RegisterForm(FlaskForm):
    username = StringField(
        "Username", filters=[clean_label], validators=[InputRequired(), Length(max=100), valid_text, USERNAME]
    )
    email = StringField("Email", filters=[lower], validators=[InputRequired(), Length(max=254), EMAIL])
    password = PasswordField(
        "Password",
        validators=[InputRequired(), Length(min=8, max=1024, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[InputRequired(), EqualTo("password", message="The passwords do not match.")],
    )


class ForgotPasswordForm(FlaskForm):
    email = StringField("Email", filters=[lower], validators=[InputRequired(), Length(max=254), EMAIL])


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password",
        validators=[InputRequired(), Length(min=8, max=1024, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[InputRequired(), EqualTo("password", message="The passwords do not match.")],
    )


class LogoutForm(FlaskForm):
    """Only the CSRF token: signing out is a POST."""


class UserCreateForm(RegisterForm):
    role = SelectField("Role", choices=ROLES, default="viewer", validators=[InputRequired()])


class UserEditForm(FlaskForm):
    email = StringField("Email", filters=[lower], validators=[Optional(), Length(max=254), EMAIL])
    role = SelectField("Role", choices=ROLES, validators=[InputRequired()])
    active = BooleanField("Active")
    password = PasswordField(
        "New password (optional)",
        validators=[Optional(), Length(min=8, max=1024, message="Use at least 8 characters.")],
    )
    datasets = SelectMultipleField("Dataset access", coerce=int, choices=[])


class UserDeleteForm(FlaskForm):
    confirmation = BooleanField(
        "Confirm account deletion",
        false_values=(False, "false", "", "0"),
        validators=[DataRequired(message="Confirm account deletion.")],
    )
