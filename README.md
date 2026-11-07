# Puzzle #58 — Update a site hero image via form upload to GitHub

> The Real World / AI Automation campus, `#automate-me-this-puzzle` puzzle #58
> (2026-03-14): *"n8n workflow updating hero image via form upload to GitHub."*

A web form lets someone upload a new hero image. A workflow receives the file
and **commits it to a file in a GitHub repo** via the GitHub API, so the site's
hero image changes by pushing to the repo. This repo proves that
upload → commit-to-GitHub mechanic end to end, two ways:

1. **`n8n-workflow.json`** — the schema-correct n8n workflow (Form Trigger →
   GitHub node doing a create-or-update file commit).
2. **`server.py` + `public/index.html`** — a runnable standalone substitute that
   performs the identical mechanic and is **verified live** against a real repo.

Because `site/` is published with GitHub Pages, committing a new `site/hero.png`
is what actually changes the live site's hero:
<https://meherawadikian.github.io/puzzle-58-hero-image-upload-github/>

---

## The mechanic

The GitHub "commit a file" operation is a single call:

```
PUT /repos/{owner}/{repo}/contents/{path}
{ "message": "...", "content": "<base64 bytes>", "branch": "main", "sha": "<existing blob sha, only when updating>" }
```

To make it idempotent (create **or** update) you first `GET` the path: if the
file exists you pass its blob `sha` (update), otherwise you omit it (create).
That GET-then-PUT is exactly what `github_commit.commit_file()` does, and it is
the same thing the n8n GitHub node (resource: File, operation: Create / Edit)
does internally.

## Files

| File | What it is |
|------|-----------|
| `github_commit.py` | Core: GET-then-PUT create-or-update a repo file via the Contents API. Token from `GITHUB_TOKEN` only. |
| `server.py` | Local backend: serves the form, receives the uploaded image as JSON+base64, commits it to `site/hero.png`. |
| `public/index.html` | The upload form (drag/drop, preview, shows the resulting commit link). |
| `site/index.html`, `site/hero.png` | The demo "site" whose hero image is a committed repo file (served by GitHub Pages from the `gh-pages` branch). |
| `n8n-workflow.json` | Form Trigger → GitHub node (File → Edit). Import into n8n and set a GitHub credential. |
| `make_hero.py` | Generates labelled hero PNGs (seed + a visibly different test image). |
| `test/verify.py` | Live end-to-end check: uploads through the running backend, then confirms via the GitHub API. |

## Run the standalone version

```bash
export GITHUB_TOKEN=$(gh auth token)          # needs 'repo' scope
export GH_OWNER=MeherAwadikian GH_REPO=puzzle-58-hero-image-upload-github
py -3.13 server.py                             # open http://localhost:8058
```

Pick an image, click **Commit new hero image**. The form shows the real commit
it produced. Reload the live Pages site to see the new hero.

### Verify it live (no browser needed)

```bash
# with server.py running, and GITHUB_TOKEN exported:
py -3.13 test/verify.py
```

It uploads `test/new-hero.png` through the backend, then independently confirms
via the GitHub API that the commit exists and that the file GitHub now serves is
byte-identical (sha256) to what was uploaded.

## Security notes

`/api/upload-hero` commits to a repo with a privileged token, so it:

- accepts **only** `Content-Type: application/json`,
- refuses any request with a cross-origin `Origin` or a non-local `Host` (CSRF),
- sniffs the image's **magic bytes** and rejects a payload whose real type does
  not match the declared `content_type` (so a blob can't be mislabelled as an
  image),
- caps the image at 3 MB.

No secret is ever committed or sent to the browser; the token is read from the
environment only.

## Using the n8n workflow

The live n8n Docker container was **down this session** (recurring Docker / D:
drive flakiness, same blocker as puzzles #29/#34/#42/#53), so the node
`typeVersion`s in `n8n-workflow.json` are pinned against n8n's **documented**
schemas (`formTrigger` 2.2, `github` 1.1), *not* against the compiled container
source the way puzzle #56 could. To use it:

1. Import `n8n-workflow.json`.
2. Create a **GitHub** credential (Access Token, `repo` scope) and select it on
   the "Commit hero to GitHub" node (the committed JSON has a placeholder id).
3. The Form Trigger's file field arrives as **binary** keyed `Hero_image`
   (the field label with spaces → underscores); the GitHub node reads that key
   via `binaryPropertyName`.
4. File → **Edit** updates an existing path; switch to File → **Create** for a
   brand-new path.

## Status

- **Standalone: fully verified live.** A real form upload produced commit
  [`ac1d4b0`](https://github.com/MeherAwadikian/puzzle-58-hero-image-upload-github/commit/ac1d4b00d5ced36616c74a13997fb684f8742808),
  changing `site/hero.png`; the live Pages site now serves that exact image.
- **n8n: not imported** (container down; JSON built against documented schemas).
- **Deploy:** demo site is live on GitHub Pages (`gh-pages` branch, `repo`
  scope). The upload *backend* needs a host that can hold the token server-side;
  running it locally is the intended demo (a static Pages site can't safely hold
  a commit token).
