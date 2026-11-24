"""Internal background supervisor for a workbench-started Python process."""

import json
from pathlib import Path
import sys

from app.workbench.jobs import execute_run


def main():
    execute_run(Path(sys.argv[1]), sys.argv[2], sys.argv[3], json.loads(sys.argv[4]), sys.argv[5:])


if __name__ == "__main__":
    main()
