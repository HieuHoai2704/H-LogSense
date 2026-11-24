"""Process queued uploaded BGL files outside Flask requests; no arbitrary paths."""

import argparse
from functools import partial

from app import create_app
from app.extensions import db
from app.services.uploads import run_once
from scripts.run.supervision import configure_logging, reclaim_interrupted, serve


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    configure_logging()
    app = create_app()
    with app.app_context():
        if 'sqlalchemy' not in app.extensions:
            raise SystemExit('Configure MySQL (DATABASE_URL) before starting the ingestion worker.')
        engine = db.engine
        serve(partial(run_once, engine), once=args.once,
              reclaim=partial(reclaim_interrupted, engine, 'parsing', 'upload-job:'))


if __name__ == '__main__':
    main()
