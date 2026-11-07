"""Live, end-to-end verification of the upload -> commit-to-GitHub mechanic.

It does what the browser form does: POST the test image (base64) to the running
backend at /api/upload-hero, which commits it to site/hero.png in the real repo.
Then it INDEPENDENTLY confirms, via the GitHub API, that:
  1. the backend returned a commit sha,
  2. that commit actually exists in the repo (author/message/date),
  3. the file bytes now served by GitHub at that path hash-match the image we
     uploaded (so the live file really is the one we pushed, not a coincidence).

Run server.py first, then: py -3.13 test/verify.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import github_commit  # noqa: E402

PORT = int(os.environ.get("PORT", "8058"))
OWNER = os.environ.get("GH_OWNER", "MeherAwadikian")
REPO = os.environ.get("GH_REPO", "puzzle-58-hero-image-upload-github")
BRANCH = os.environ.get("GH_BRANCH", "main")
HERO_PATH = os.environ.get("HERO_PATH", "site/hero.png")
TEST_IMAGE = HERE / "new-hero.png"


def post_upload(image_bytes: bytes, content_type: str) -> dict:
    body = json.dumps(
        {"content_type": content_type, "content_b64": base64.b64encode(image_bytes).decode("ascii")}
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://localhost:{PORT}/api/upload-hero",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(path: str) -> tuple[int, dict]:
    return github_commit._request("GET", f"{github_commit.GITHUB_API}{path}")


def main() -> int:
    image_bytes = TEST_IMAGE.read_bytes()
    uploaded_sha256 = hashlib.sha256(image_bytes).hexdigest()
    print(f"[1] Uploading {TEST_IMAGE.name} ({len(image_bytes)} bytes, sha256 {uploaded_sha256[:12]}...) "
          f"through the live form backend on :{PORT}")

    result = post_upload(image_bytes, "image/png")
    if not result.get("ok"):
        print(f"    FAIL: backend rejected the upload: {result}")
        return 1
    commit_sha = result["commit_sha"]
    print(f"    backend committed: action={result['action']} commit={commit_sha}")
    print(f"    file url: {result['html_url']}")

    print("[2] Confirming the commit exists in the repo via the GitHub API")
    status, commit = api_get(f"/repos/{OWNER}/{REPO}/commits/{commit_sha}")
    if status != 200:
        print(f"    FAIL: commit {commit_sha} not found ({status})")
        return 1
    msg = commit.get("commit", {}).get("message")
    author = commit.get("commit", {}).get("author", {})
    files = [f.get("filename") for f in commit.get("files", [])]
    print(f"    commit found: '{msg}' by {author.get('name')} at {author.get('date')}")
    print(f"    files changed: {files}")
    if HERO_PATH not in files:
        print(f"    FAIL: commit did not touch {HERO_PATH}")
        return 1

    print("[3] Fetching the file GitHub now serves at that commit and hashing it")
    status, content = api_get(f"/repos/{OWNER}/{REPO}/contents/{HERO_PATH}?ref={commit_sha}")
    if status != 200:
        print(f"    FAIL: could not read {HERO_PATH} at {commit_sha} ({status})")
        return 1
    remote_bytes = base64.b64decode(content["content"])
    remote_sha256 = hashlib.sha256(remote_bytes).hexdigest()
    print(f"    remote file: {len(remote_bytes)} bytes, sha256 {remote_sha256[:12]}...")

    if remote_sha256 == uploaded_sha256:
        print("\nPASS: the image the form uploaded is byte-identical to the one GitHub now serves.")
        print(f"      commit {commit_sha}")
        return 0
    print("\nFAIL: hash mismatch -- remote file is not the uploaded image.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
