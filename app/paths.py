"""Where H-logsen keeps local runtime state (uploads, model studies, feature caches, model files).

Product code resolves these locations here instead of from the current working directory, so the
web server, both workers and the scripts agree wherever they are started from.

- ``LOGSENSE_LOCAL_DIR`` (absolute path) overrides everything.
- A source checkout uses ``<repository>/.local``, the folder the MySQL runtime tools already own.
- An installed package uses ``~/.h-logsen/local``, next to the workbench profile.
"""

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def local_dir() -> Path:
    configured = os.environ.get("LOGSENSE_LOCAL_DIR")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            raise ValueError("LOGSENSE_LOCAL_DIR must be an absolute path.")
        return path
    if (PACKAGE_ROOT / "pyproject.toml").is_file() and (PACKAGE_ROOT / "app").is_dir():
        return PACKAGE_ROOT / ".local"
    return Path.home() / ".h-logsen" / "local"


LOCAL_DIR = local_dir()
UPLOADS_DIR = LOCAL_DIR / "uploads"
IF_STUDIES_DIR = LOCAL_DIR / "if_studies"
IF_HOLDOUT_DIR = LOCAL_DIR / "if_new_holdout"
VALIDATED_IF_INPUTS_DIR = LOCAL_DIR / "validated_if_inputs"
WINDOW_FEATURES_DIR = LOCAL_DIR / "window_features"
MODEL_ARTIFACTS_DIR = LOCAL_DIR / "model_artifacts"
