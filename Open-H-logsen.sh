#!/bin/sh
set -eu
CDPATH= cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo 'Run sh Install-H-logsen.sh first.' >&2
    exit 1
fi
exec .venv/bin/python -I -m app.workbench "$@"
