"""Shared extensions; the demonstration application needs no database server."""

from typing import TYPE_CHECKING

from flask_bootstrap import Bootstrap5
from flask_mail import Mail
from flask_migrate import Migrate
from flask_moment import Moment
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(table_name)s_%(column_0_name)s",
            "uq": "uq_%(table_name)s_%(column_0_N_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


db = SQLAlchemy(model_class=Base)
# Models subclass this. Flask-SQLAlchemy builds db.Model from Base at runtime, which type checkers cannot
# follow; they see Base, which has the same mapped-column behavior.
if TYPE_CHECKING:
    Model = Base
else:
    Model = db.Model
migrate = Migrate()
bootstrap = Bootstrap5()
moment = Moment()
mail = Mail()
