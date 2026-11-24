#!/bin/sh
set -eu
CDPATH= cd "$(dirname "$0")"
# In a source checkout this script lives in packaging/posix/; work from the repository root.
if [ -f ../../pyproject.toml ] && [ -d ../../app ] && ! ls h_logsen-*.whl >/dev/null 2>&1; then
    CDPATH= cd ../..
fi

# Linux must use the distribution Python that provides GTK/WebKitGTK bindings,
# which is Python 3.14 on Ubuntu 26.04. macOS keeps the verified 3.13 limit.
case "$(uname -s)" in
    Darwin) extra='' newest=13 ;;
    Linux) extra='[desktop]' newest=14 ;;
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
    if ! "$python" -c "import sys; sys.exit(not ((3, 10) <= sys.version_info[:2] <= (3, $newest) and sys.maxsize > 2**32))"; then
        echo "Install Python 3.10–3.$newest (64-bit), or set H_LOGSEN_PYTHON to its executable." >&2
        exit 1
    fi
    "$python" -m venv "$@" .venv
fi
if [ -n "$extra" ] && ! .venv/bin/python -I -c "import cairo, gi; gi.require_version('Gtk', '3.0'); gi.require_version('WebKit2', '4.1'); from gi.repository import Gtk, WebKit2"; then
    echo 'Install python3-gi, python3-gi-cairo, gir1.2-gtk-3.0 and gir1.2-webkit2-4.1. Use the system Python and a venv with --system-site-packages.' >&2
    exit 1
fi
.venv/bin/python -m pip --isolated install --prefer-binary "$package$extra"
if [ -n "$extra" ]; then
    # The venv also sees system packages; only H-logsen's own dependency tree must be consistent.
    .venv/bin/python -I -m app.workbench.platforms.linux check
else
    .venv/bin/python -m pip check
fi
.venv/bin/python -I -m app.workbench --help >/dev/null
if [ -n "$extra" ] && [ "${H_LOGSEN_NO_LAUNCHER:-}" != 1 ]; then
    .venv/bin/python -I -m app.workbench.platforms.linux launcher ||
        echo 'Could not add H-logsen to the application menu. Open-H-logsen.sh is still available.' >&2
fi
echo 'H-logsen is installed. Run sh Open-H-logsen.sh to open the desktop workspace.'
