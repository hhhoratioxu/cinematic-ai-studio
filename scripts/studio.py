"""Private loopback production workbench. Generation remains an explicit CLI operation."""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from common import CinemaError, content_key
from project import read_json, review_asset, status, task_snapshot
from state import run_lock


def media_registry(directory):
    paths = set()
    for accepted in (directory / "shots").glob("*/accepted.json"):
        entry = read_json(accepted, {})
        paths.update(entry.get(k) for k in ("generated_file", "source_file", "normalized_file") if entry.get(k))
    paths.update(t["output"] for t in task_snapshot(directory)["tasks"] if t["state"] == "complete")
    manifest = read_json(directory / "manifest.json", {})
    if manifest.get("output"):
        paths.add(manifest["output"])
    for c in read_json(directory / "characters.json", []):
        paths.update(c.get("references", {}).values())
    root = directory.resolve()
    return {content_key(str(Path(p).resolve()))[:24]: Path(p).resolve() for p in paths
            if Path(p).is_file() and Path(p).resolve().is_relative_to(root) and
            Path(p).suffix.lower() in (".mp4", ".mkv", ".webm", ".png", ".jpg", ".jpeg", ".wav", ".mp3")}


def create_server(directory: Path, port=0):
    directory = directory.resolve(strict=True)
    session_token = secrets.token_urlsafe(32)
    html = (Path(__file__).resolve().parents[1] / "assets" / "studio.html").read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Tokens and filesystem paths must not be written to access logs.

        def headers_ok(self, mutation=False):
            host = self.headers.get("Host", "")
            allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            if host not in allowed:
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + v for v in allowed}:
                return False
            if mutation and origin not in {"http://" + v for v in allowed}:
                return False
            query = parse_qs(urlsplit(self.path).query)
            provided = self.headers.get("Authorization", "").removeprefix("Bearer ")
            if not mutation and urlsplit(self.path).path.startswith("/media/"):
                provided = query.get("token", [""])[0]
            return secrets.compare_digest(provided, session_token)

        def respond(self, code, body, mime="application/json; charset=utf-8", extra=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/" and self.headers.get("Host") in (f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"):
                self.respond(200, html, "text/html; charset=utf-8")
                return
            if not self.headers_ok():
                self.respond(403, {"error": "Local session token/host required"})
                return
            try:
                if path == "/api/state":
                    data = status(directory)
                    registry = media_registry(directory)
                    data["media"] = [{"id": key, "file": str(p.relative_to(directory)),
                                      "type": mimetypes.guess_type(p.name)[0] or "application/octet-stream"}
                                     for key, p in registry.items()]
                    data["project_directory"] = str(directory)
                    self.respond(200, data)
                elif path.startswith("/media/"):
                    registry = media_registry(directory)
                    file = registry.get(path.removeprefix("/media/"))
                    if file is None:
                        self.respond(404, {"error": "Unknown registered media"})
                        return
                    # Open only the resolved registered path, check again against the project root.
                    if not file.resolve().is_relative_to(directory):
                        raise CinemaError("Media escaped project root")
                    size = file.stat().st_size
                    start, end = 0, size - 1
                    range_header = self.headers.get("Range")
                    if range_header:
                        match = re.fullmatch(r"bytes=(\d+)-(\d*)", range_header)
                        if not match:
                            self.respond(416, {"error": "Single forward byte range required"})
                            return
                        start = int(match[1])
                        end = min(int(match[2]) if match[2] else end, size - 1)
                        if start > end or start >= size:
                            self.respond(416, {"error": "Invalid byte range"})
                            return
                    self.send_response(206 if range_header else 200)
                    self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
                    self.send_header("Content-Length", str(end - start + 1))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("Referrer-Policy", "no-referrer")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    if range_header:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    with file.open("rb") as stream:
                        stream.seek(start)
                        left = end - start + 1
                        while left:
                            block = stream.read(min(65536, left))
                            if not block:
                                break
                            self.wfile.write(block)
                            left -= len(block)
                else:
                    self.respond(404, {"error": "Unknown route"})
            except (CinemaError, OSError, ValueError, KeyError) as exc:
                self.respond(400, {"error": str(exc)})

        def do_POST(self):
            if not self.headers_ok(mutation=True):
                self.respond(403, {"error": "Same-origin authenticated session required"})
                return
            if urlsplit(self.path).path != "/api/review":
                self.respond(404, {"error": "Generation is an explicit CLI operation"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 16384 or not self.headers.get("Content-Type", "").startswith("application/json"):
                    raise CinemaError("Expected a small JSON review request")
                body = json.loads(self.rfile.read(size))
                with run_lock(directory):
                    record = review_asset(directory, body["target"], body["scope"], body["decision"],
                                          body["reviewer"], body["note"], body["sha256"], body.get("raw", False))
                self.respond(200, record)
            except (CinemaError, ValueError, KeyError, TypeError) as exc:
                self.respond(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.session_token = session_token
    server.session_url = f"http://127.0.0.1:{server.server_port}/#{session_token}"
    return server


def run(directory, port=8765, open_browser=True):
    import webbrowser
    server = create_server(directory, port)
    print(json.dumps({"studio": server.session_url, "local_only": True, "paid_calls": 0}), flush=True)
    if open_browser:
        webbrowser.open(server.session_url)
    try:
        server.serve_forever(poll_interval=0.3)
    finally:
        server.server_close()
