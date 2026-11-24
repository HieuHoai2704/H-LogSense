#!/bin/sh
set -eu
CDPATH= cd "$(dirname "$0")"

case "$(uname -s)" in
    Darwin) extra='' ;;
    Linux) extra='[desktop]' ;;
    *) echo 'Use Install-H-logsen.cmd on Windows.' >&2; exit 1 ;;
esac

set -- ./h_logsen-*.whl
if [ -f "$1" ] && [ "$#" -eq 1 ]; then
    package=$1
elif [ ! -f "$1" ] && [ -f pyproject.toml ]; then
    package=.
else
    echo 'Extract the full download and keep exactly one H-logsen wheel in this folder.' >&2
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    if [ -n "$extra" ]; then
        python=${H_LOGSEN_PYTHON:-/usr/bin/python3}
        set -- --system-site-packages
    else
        python=${H_LOGSEN_PYTHON:-python3}
        set --
    fi
    if ! "$python" -c 'import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] < (3, 14) and sys.maxsize > 2**32))'; then
        echo 'Install Python 3.10–3.13 (64-bit), or set H_LOGSEN_PYTHON to its executable.' >&2
        exit 1
    fi
    "$python" -m venv "$@" .venv
fi
if [ -n "$extra" ] && ! .venv/bin/python -I -c "import cairo, gi; gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1'); from gi.repository import Gtk, WebKit2"; then
    echo 'Install python3-gi, python3-gi-cairo, gir1.2-gtk-3.0 and gir1.2-webkit2-4.1. Use the system Python and a venv with --system-site-packages.' >&2
    exit 1
fi
.venv/bin/python -m pip --isolated install --prefer-binary "$package$extra"
.venv/bin/python -m pip check
.venv/bin/python -I -m app.workbench --help >/dev/null
echo 'H-logsen is installed. Run sh Open-H-logsen.sh to open the desktop workspace.'
