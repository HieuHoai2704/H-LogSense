#!/bin/sh
set -eu
CDPATH= cd "$(dirname "$0")"
# In a source checkout this script lives in packaging/posix/; work from the repository root.
if [ -f ../../pyproject.toml ] && [ -d ../../app ] && ! ls h_logsen-*.whl >/dev/null 2>&1; then
    CDPATH= cd ../..
fi
if [ ! -x .venv/bin/python ]; then
    echo 'Run sh Install-H-logsen.sh first.' >&2
    exit 1
fi
exec .venv/bin/python -I -m app.workbench "$@"
