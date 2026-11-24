"""Start H-logsen as a local web application and open it in the browser.

    python -m app.workbench               # start (or reuse) the local server and open the browser
    python -m app.workbench --no-browser  # print the private launch URL instead

The server listens on 127.0.0.1 only. One server runs per state directory: launching again while it
runs just opens the browser on it, so the launcher icon can be clicked any number of times.
"""

import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import sys
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser

from werkzeug.serving import make_server

from app import create_app
from app.permissions import write_private
from app.workbench.api import mount


def running_instance(state_dir):
    """The launch URL of a server already running for this state directory, or None."""
    path = state_dir / "server.json"
    try:
        info = json.loads(path.read_text("utf-8"))
        port, token = int(info["port"]), str(info["token"])
        os.kill(int(info["pid"]), 0)
        with urlopen(f"http://127.0.0.1:{port}/api/v1/health/database", timeout=2):
            pass
    except URLError as error:
        # Any HTTP answer (503 without a database included) means our server is up.
        if getattr(error, "code", None) is None:
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return f"http://127.0.0.1:{port}/#workbench={token}"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--port", type=int, default=0, help="Loopback port. Zero selects an available port.")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".h-logsen")
    parser.add_argument("--no-browser", action="store_true", help="Print the private launch URL.")
    # Earlier launchers passed these; the app now always opens in the browser.
    parser.add_argument("--browser", "--desktop", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")

    existing = running_instance(args.state_dir)
    if existing:
        open_browser(existing, args.no_browser)
        return

    # Opened from the launcher icon, the app finds the local demo database (and starts its container).
    from app.workbench.local_database import use_demo_database

    use_demo_database()
    # A new session secret per server start: restarting the server signs everyone out.
    app = create_app({"TRUSTED_HOSTS": ["127.0.0.1"], "SECRET_KEY": secrets.token_hex(32)})
    token = secrets.token_urlsafe(32)
    local = mount(app, token, args.state_dir)
    with make_server("127.0.0.1", args.port, app, threaded=True) as server:
        local["port"] = server.server_port
        launch_url = f"http://127.0.0.1:{server.server_port}/#workbench={token}"
        state = args.state_dir / "server.json"
        state.parent.mkdir(parents=True, exist_ok=True)
        write_private(state, json.dumps({"pid": os.getpid(), "port": server.server_port, "token": token}))

        def stop(signum, frame):
            raise KeyboardInterrupt  # a polite stop (logout, shutdown) cleans up like Ctrl+C

        signal.signal(signal.SIGTERM, stop)
        try:
            open_browser(launch_url, args.no_browser)
            print("H-logsen: running; press Ctrl+C to stop.", flush=True)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            local["terminals"].shutdown()
            try:
                if json.loads(state.read_text("utf-8")).get("pid") == os.getpid():
                    state.unlink()
            except (OSError, ValueError):
                pass


def open_browser(launch_url, print_only=False):
    print(f"H-logsen: {launch_url.split('#')[0]}", flush=True)
    if print_only or not webbrowser.open(launch_url):
        print(f"Open this private URL in your browser: {launch_url}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
