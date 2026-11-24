"""Process queued uploaded BGL files outside Flask requests; no arbitrary paths."""

import argparse
import time

from app import create_app
from app.extensions import db
from app.services.uploads import run_once


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        if 'sqlalchemy' not in app.extensions:
            raise ValueError('Configure MySQL before starting the ingestion worker.')
        while True:
            worked = run_once(db.engine)
            if args.once:
                return
            if not worked:
                time.sleep(1)


if __name__ == '__main__':
    main()
