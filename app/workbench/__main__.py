"""Launch the H-logsen workbench for the signed-in OS user on loopback."""

import argparse
from pathlib import Path
import secrets
import sys
from threading import Thread
import webbrowser

from werkzeug.serving import make_server

from app import create_app
from app.workbench.api import mount
from app.workbench.desktop import RENDERERS, desktop_window


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Loopback port. Zero selects an available port.")
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".h-logsen")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--desktop", dest="mode", action="store_const", const="desktop", help="Open the desktop window.")
    modes.add_argument("--browser", dest="mode", action="store_const", const="browser", help="Open in the default browser.")
    modes.add_argument("--no-browser", dest="mode", action="store_const", const="headless", help="Print the private launch URL.")
    parser.set_defaults(mode="desktop" if sys.platform in RENDERERS else "browser")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("Port must be between 0 and 65535.")
    if args.mode == "desktop" and sys.platform not in RENDERERS:
        parser.error("Desktop mode is available on Windows, macOS and Linux.")
    app = create_app({"TRUSTED_HOSTS": ["127.0.0.1"]})
    token = secrets.token_urlsafe(32)
    local = mount(app, token, args.state_dir, desktop=args.mode == "desktop")
    with make_server("127.0.0.1", args.port, app, threaded=True) as server:
        local["port"] = server.server_port
        url = f"http://127.0.0.1:{server.server_port}/"
        launch_url = url + "#workbench=" + token
        try:
            if args.mode == "desktop":
                worker = Thread(target=server.serve_forever, name="h-logsen-loopback", daemon=True)
                worker.start()
                try:
                    desktop_window(launch_url, token, local["store"])
                finally:
                    server.shutdown()
                    worker.join()
            else:
                print(f"H-logsen: {launch_url if args.mode == 'headless' else url}", flush=True)
                if args.mode == "browser" and not webbrowser.open(launch_url):
                    print(f"Open this private URL in your browser: {launch_url}", flush=True)
                server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            local["terminals"].shutdown()


def desktop_main():
    try:
        main()
    except Exception as error:
        if sys.platform != "win32":
            raise
        from ctypes import windll

        windll.user32.MessageBoxW(None, str(error), "H-logsen", 0x10)
        return 1
    return 0


if __name__ == "__main__":
    if "--desktop" in sys.argv and sys.platform == "win32":
        sys.exit(desktop_main())
    main()
