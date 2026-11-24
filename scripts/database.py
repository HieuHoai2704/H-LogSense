"""Operator CLI. Run as `python -m scripts.database`; never accepts HTTP paths."""

import argparse
import json

from sqlalchemy.orm import Session

from app import create_app
from app.extensions import db
from app.models import DataSource, Dataset
from app.services.bgl_ingestion import ingest_bgl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register-bgl")
    register.add_argument("--key", required=True)
    user_command = commands.add_parser("create-user")
    user_command.add_argument("--username", required=True)
    user_command.add_argument(
        "--role", choices=["viewer", "analyst", "manager", "admin"], required=True
    )
    access = user_command.add_mutually_exclusive_group(required=True)
    access.add_argument("--dataset", type=int, action="append", default=[])
    access.add_argument("--no-dataset", action="store_true",
                        help="Create an account with no initial dataset grants.")
    notify = commands.add_parser("notify")
    notify.add_argument("--alert-id", type=int, help="Restrict processing to this alert.")
    ingest = commands.add_parser("ingest-bgl")
    ingest.add_argument("--dataset", type=int, required=True)
    ingest.add_argument("--archive", required=True)
    ingest.add_argument("--limit", type=int)
    ingest.add_argument("--batch-size", type=int, default=500)
    run = commands.add_parser("detect")
    run.add_argument("--dataset", type=int, required=True)
    run.add_argument("--kind", choices=["rule", "isolation_forest"], required=True)
    run.add_argument("--train-size", type=int, default=1000)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        if "sqlalchemy" not in app.extensions:
            parser.error("Set DATABASE_URL to an isolated MySQL database first.")
        if args.command == "create-user":
            import getpass, os
            from werkzeug.security import generate_password_hash
            from app.domain import User, UserDataset

            password = os.environ.get("LOGSENSE_BOOTSTRAP_PASSWORD") or getpass.getpass(
                "New account password (12+ characters): "
            )
            if (
                len(password) < 12
                or len(password) > 1024
                or not 1 <= len(args.username) <= 100
            ):
                raise ValueError("Invalid account settings.")
            with Session(db.engine) as session, session.begin():
                for dataset_id in args.dataset:
                    if session.get(Dataset, dataset_id) is None:
                        raise ValueError("Dataset not found.")
                user = User(
                    username=args.username,
                    password_hash=generate_password_hash(password),
                    role=args.role,
                )
                session.add(user)
                session.flush()
                session.add_all(
                    [
                        UserDataset(user_id=user.id, dataset_id=d)
                        for d in set(args.dataset)
                    ]
                )
                result = {
                    "user_id": user.id,
                    "role": user.role,
                    "datasets": sorted(set(args.dataset)),
                }
        elif args.command == "notify":
            from app.services.alerts import deliver_notifications

            if args.alert_id is not None and args.alert_id < 1:
                parser.error("--alert-id must be positive")
            result = deliver_notifications(db.engine, alert_id=args.alert_id)
        elif args.command == "register-bgl":
            from sqlalchemy import select

            with Session(db.engine) as session, session.begin():
                source = session.scalar(
                    select(DataSource).where(DataSource.source_key == "loghub-bgl")
                )
                if source is None:
                    source = DataSource(source_key="loghub-bgl", name="Loghub BGL")
                    session.add(source)
                    session.flush()
                dataset = Dataset(
                    source_id=source.id,
                    dataset_key=args.key,
                    name=args.key,
                    data_mode="real",
                )
                session.add(dataset)
                session.flush()
                result = {"dataset_id": dataset.id}
        elif args.command == "ingest-bgl":
            result = ingest_bgl(
                db.engine,
                args.dataset,
                args.archive,
                limit=args.limit,
                batch_size=args.batch_size,
                progress=lambda item: print(json.dumps({"progress": item})),
            )
        else:
            from app.services.detection import detect

            result = detect(
                db.engine, args.dataset, kind=args.kind, train_size=args.train_size
            )
        print(json.dumps(result))


if __name__ == "__main__":
    # SQL exceptions can contain bound log data. Do not print their raw repr/URL.
    try:
        main()
    except Exception as error:
        raise SystemExit(
            "Operation failed ("
            + type(error).__name__
            + "); inspect private diagnostics with authorization."
        ) from None
