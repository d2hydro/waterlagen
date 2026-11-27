"""Serveer het lokale keuzevenster, alleen voor deze browsersessie."""

import json
import mimetypes
import re
import secrets
import subprocess
import sys
import threading
import time
import webbrowser
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .map_tiles import tile

ASSETS = Path(__file__).with_name("web")


def create_server(
    dispatch: Callable[[str, dict], dict], cache: Path
) -> ThreadingHTTPServer:
    """Bind uitsluitend localhost; ieder venster heeft een eigen geheime URL."""
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def authorized(self) -> bool:
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                return False
            origin = self.headers.get("Origin")
            return origin in (None, "http://" + expected) and urlsplit(
                self.path
            ).path.startswith(f"/{token}/")

        def reply(
            self, content: bytes, mime: str, status: int = 200, *, cached: bool = False
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header(
                "Cache-Control", "private, max-age=86400" if cached else "no-store"
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self) -> None:
            if not self.authorized():
                self.send_error(403)
                return
            relative = urlsplit(self.path).path[len(token) + 2 :]
            match = re.fullmatch(
                r"tiles/(streets|aerial)/(\d{1,2})/(\d+)/(\d+)", relative
            )
            if match:
                try:
                    provider, level, x, y = match.groups()
                    content, mime = tile(cache, provider, int(level), int(x), int(y))
                    self.reply(content, mime, cached=True)
                except Exception:
                    self.send_error(502, "Kaarttegel niet beschikbaar")
                return
            target = ASSETS / (relative or "index.html")
            if (
                not target.resolve().is_relative_to(ASSETS.resolve())
                or not target.is_file()
            ):
                self.send_error(404)
                return
            self.reply(
                target.read_bytes(),
                mimetypes.guess_type(target)[0] or "application/octet-stream",
            )

        def do_POST(self) -> None:
            if (
                not self.authorized()
                or self.headers.get("Content-Type") != "application/json"
            ):
                self.send_error(403)
                return
            relative = urlsplit(self.path).path[len(token) + 2 :]
            if not relative.startswith("api/"):
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4_000_000:
                    raise ValueError("Ongeldige verzoekgrootte.")
                values = json.loads(self.rfile.read(length))
                if not isinstance(values, dict):
                    raise ValueError("Ongeldige formulierkeuzes.")
                action = relative[4:]
                self.server.last_seen = time.monotonic()
                if action == "heartbeat":
                    result = {}
                else:
                    self.server.active_requests += 1
                    try:
                        result = dispatch(action, values)
                    finally:
                        self.server.active_requests -= 1
                    self.server.last_seen = time.monotonic()
                self.reply(
                    json.dumps(result, allow_nan=False).encode(), "application/json"
                )
                if result.get("closing"):
                    self.server.closing = True
            except (ValueError, TypeError, KeyError, OSError) as error:
                self.reply(
                    json.dumps({"error": str(error)}).encode(), "application/json", 400
                )
            except Exception as error:
                self.reply(
                    json.dumps(
                        {"error": f"Opdracht niet uitgevoerd: {error}"}
                    ).encode(),
                    "application/json",
                    500,
                )

        def log_message(self, format: str, *args) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    server.url = f"http://127.0.0.1:{server.server_port}/{token}/"
    server.last_seen = time.monotonic()
    server.active_requests = 0
    server.closing = False
    return server


def open_browser(project: Path) -> None:
    """Open dezelfde kaartindeling als het ontwerp, met echte lokale functies."""
    from waterlagen.datastore import DataStore
    from .browser_app import RunApplication
    from .native_dialogs import NativeDialogs, create_run_window

    root = create_run_window()
    root.withdraw()
    dialogs = NativeDialogs(root, project)
    application = RunApplication(project, dialogs)
    server = create_server(
        application.dispatch, DataStore().source_data_dir / "kaartachtergronden"
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Run maken: {server.url}", flush=True)

    desktop = None

    def check_closed() -> None:
        if desktop is not None:
            closed = desktop.poll() is not None
        else:
            closed = (
                not server.active_requests and time.monotonic() - server.last_seen > 120
            )
        if server.closing or closed:
            root.quit()
        else:
            root.after(1000, check_closed)

    try:
        if sys.platform == "win32":
            # Pixi starts hidden. Show the independent map window normally.
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1  # SW_SHOWNORMAL
            desktop = subprocess.Popen(
                [
                    Path(__file__).with_name("desktop") / "Waterlagen.Runmaker.exe",
                    server.url,
                ],
                startupinfo=startup,
            )
        elif not webbrowser.open(server.url, new=1):
            raise RuntimeError("De browser kon niet worden geopend.")
        root.after(1000, check_closed)
        root.mainloop()
        if desktop is not None and desktop.poll() not in (None, 0):
            raise RuntimeError("Het Waterlagen-venster is met een fout gesloten.")
    finally:
        if desktop is not None and desktop.poll() is None:
            desktop.terminate()
            desktop.wait()

        server.shutdown()
        server.server_close()
        root.destroy()
