"""Core mechanic shared by the backend server and the verification script:
accept image bytes and commit-or-update them to a file in a GitHub repo via the
GitHub Contents API. This is the exact same operation the n8n GitHub node runs
(resource: File, operation: Create / Edit) -- a PUT to
/repos/{owner}/{repo}/contents/{path}.

No secrets live in this file. The token is read from the environment
(GITHUB_TOKEN), never hard-coded, never committed.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

GITHUB_API = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns a non-success status."""


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise GitHubError(
            "GITHUB_TOKEN is not set. Export it (e.g. `export GITHUB_TOKEN=$(gh auth token)`) "
            "before running. It needs the 'repo' scope for Contents commits."
        )
    return token


def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_token()}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "puzzle-58-hero-image-upload")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        return exc.code, parsed


def get_file_sha(owner: str, repo: str, path: str, branch: str) -> str | None:
    """Return the current blob sha for path, or None if the file does not exist.

    The Contents API needs the existing sha to UPDATE a file, and the sha must be
    ABSENT to CREATE one -- so this GET is what makes the operation idempotent.
    """
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    status, payload = _request("GET", url)
    if status == 200 and isinstance(payload, dict):
        return payload.get("sha")
    if status == 404:
        return None
    raise GitHubError(f"GET contents failed ({status}): {payload}")


def commit_file(
    owner: str,
    repo: str,
    path: str,
    content_bytes: bytes,
    message: str,
    branch: str = "main",
) -> dict:
    """Create-or-update `path` in the repo with `content_bytes`, returning a
    summary dict including the real commit sha the push produced.
    """
    existing_sha = get_file_sha(owner, repo, path, branch)
    body = {
        "message": message,
        "content": base64.b64encode(content_bytes).decode("ascii"),
        "branch": branch,
    }
    if existing_sha is not None:
        body["sha"] = existing_sha  # update path

    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    status, payload = _request("PUT", url, body)
    if status not in (200, 201):
        raise GitHubError(f"PUT contents failed ({status}): {payload}")

    commit = payload.get("commit", {})
    content = payload.get("content", {})
    return {
        "action": "updated" if existing_sha is not None else "created",
        "commit_sha": commit.get("sha"),
        "commit_url": commit.get("html_url"),
        "file_sha": content.get("sha"),
        "file_path": content.get("path"),
        "download_url": content.get("download_url"),
        "html_url": content.get("html_url"),
        "size": content.get("size"),
    }
