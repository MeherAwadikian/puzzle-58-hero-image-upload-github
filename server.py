"""Standalone substitute for the n8n workflow.

A web form (served at `/`) lets someone upload a new hero image. The browser
base64-encodes the file and POSTs it to `/api/upload-hero`; this backend decodes
it and COMMITS it to `site/hero.png` in a GitHub repo via the Contents API --
the identical mechanic the n8n Form-Trigger -> GitHub-node workflow performs.

Because the repo's `site/` is published with GitHub Pages, committing a new
hero image is what actually changes the live site's hero.

The GitHub token is read from the environment only (GITHUB_TOKEN) and is never
sent to the browser. Run:

    export GITHUB_TOKEN=$(gh auth token)
    export GH_OWNER=YourUser GH_REPO=your-repo HERO_PATH=site/hero.png
    py -3.13 server.py            # then open http://localhost:8058
"""

from __future__ import annotations

import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import github_commit

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "8058"))
OWNER = os.environ.get("GH_OWNER", "MeherAwadikian")
REPO = os.environ.get("GH_REPO", "puzzle-58-hero-image-upload-github")
BRANCH = os.environ.get("GH_BRANCH", "main")
HERO_PATH = os.environ.get("HERO_PATH", "site/hero.png")

# Only accept real raster image types, capped so the endpoint can't be used to
# push arbitrary large blobs into the repo.
ALLOWED = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
MAX_BYTES = 3 * 1024 * 1024
LOCAL_ORIGINS = {f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"}


def _magic_type(data: bytes) -> str | None:
    """Sniff the real image type from the leading bytes, so a caller can't
    mislabel an arbitrary blob as an image via the content_type field."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: dict) -> None:
        self._send(status, json.dumps(obj).encode("utf-8"), "application/json")

    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        if self.path in ("/", "/index.html"):
            html = (HERE / "public" / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return
        if self.path == "/config":
            self._json(200, {"owner": OWNER, "repo": REPO, "branch": BRANCH, "path": HERO_PATH})
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/upload-hero":
            self._json(404, {"error": "not found"})
            return

        # CSRF / cross-origin hardening: this endpoint commits to a repo with a
        # privileged token, so only accept same-origin JSON from a local host.
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
            self._json(415, {"error": "Content-Type must be application/json"})
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin not in LOCAL_ORIGINS:
            self._json(403, {"error": "cross-origin request refused"})
            return
        host = self.headers.get("Host", "").split(":")[0]
        if host not in ("localhost", "127.0.0.1"):
            self._json(403, {"error": "non-local Host refused"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            payload = json.loads(raw.decode("utf-8"))
            content_type = payload.get("content_type", "")
            b64 = payload.get("content_b64", "")

            if content_type not in ALLOWED:
                self._json(415, {"error": f"unsupported type {content_type!r}; allowed: {list(ALLOWED)}"})
                return

            image_bytes = base64.b64decode(b64, validate=True)
            if not image_bytes:
                self._json(400, {"error": "empty image"})
                return
            sniffed = _magic_type(image_bytes)
            if sniffed != content_type:
                self._json(
                    415,
                    {"error": f"declared type {content_type!r} does not match actual bytes ({sniffed!r})"},
                )
                return
            if len(image_bytes) > MAX_BYTES:
                self._json(413, {"error": f"image too large ({len(image_bytes)} bytes, max {MAX_BYTES})"})
                return

            result = github_commit.commit_file(
                owner=OWNER,
                repo=REPO,
                path=HERO_PATH,
                content_bytes=image_bytes,
                message=f"Update hero image via form upload ({len(image_bytes)} bytes)",
                branch=BRANCH,
            )
            self._json(200, {"ok": True, **result})
        except github_commit.GitHubError as exc:
            self._json(502, {"ok": False, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface the real reason to the form
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, *args) -> None:  # keep the console quiet
        return


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Hero-image uploader on http://localhost:{PORT}  ->  commits {OWNER}/{REPO}:{HERO_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
