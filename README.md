# 50ohm Pool Question Review Tool

For the destination server deployment under `/isq/qrt/`, see [MIGRATION_ISQ.md](MIGRATION_ISQ.md). The repository's `docker-compose.yml` now targets that prefix on `127.0.0.1:18082`; the prior production Compose is preserved as `docker-compose.jp2s.yml`. The local development Compose remains separate.

On this deployment, `GET /campaigns.json` returns only the IDs and labels of active campaigns for the static site's landing page. The response does not include campaign branch names and is not cached. Restart QRT after changing its private `campaigns.json` file.

## Overview
This tool is part of the Swiss 50ohm platform. It reviews German, French, and
Italian canonical question subsets through shared Git campaign branches. The
application is a containerized FastAPI web service.

![Screenshot](/images/screenshot_review_tool.png)

## How it works
Users authenticate with GitHub. Their OAuth token reads and atomically commits
changes to configured branches of `50ohm-question-review-campaigns`. Each
campaign is addressed under `/campaign/<campaign-id>/`. Questions
keep the canonical object-centric JSON shape. Working comments are separate
campaign files, and the generated table of contents is read-only. The canonical
question pool is never written by the web application.

## Deployment

Local development and Docker use Python 3.14. From this repository, install
the locked dependencies and run tests without starting the service:

```bash
uv sync --locked
uv run --locked python -m pytest -q
```

`requirements.txt` remains the Docker runtime dependency list; keep it aligned
with `pyproject.toml` when changing runtime dependencies.

Deployment is container-based and environment-specific. This branch does not
contain an automatic Cloud Run deployment workflow. Create an environment file
from `.env.example`, keep secrets outside Git, build the image, and run it behind
the target HTTPS reverse proxy.

## Local Docker baseline

The local GitHub OAuth application must use:

- homepage URL: `http://localhost:8080`
- callback URL: `http://localhost:8080/auth/callback`

Keep secrets outside the repository, for example in
`~/.config/50ohm-review-tool/local.env`. Build and start the local baseline with:

```bash
docker build --tag 50ohm-question-review-tool:multilingual-review .

docker run --rm --detach \
  --name 50ohm-question-review-local \
  --publish 127.0.0.1:8080:8080 \
  --env-file ~/.config/50ohm-review-tool/local.env \
  --mount type=bind,src="$PWD/campaigns.json",dst=/app/config/campaigns.json,readonly \
  --env GITHUB_OWNER=isqsoft \
  --env GITHUB_REPO=50ohm-question-review-campaigns \
  --env CAMPAIGNS_FILE=/app/config/campaigns.json \
  --env DEFAULT_CAMPAIGN=review-tool-sandbox \
  --env GITHUB_CALLBACK_URL=http://localhost:8080/auth/callback \
  --env SESSION_HTTPS_ONLY=false \
  --env GITHUB_PROFILE=true \
  --env CAMPAIGN_REFRESH_SECONDS=30 \
  50ohm-question-review-tool:multilingual-review
```

The server redirects `http://localhost:8080` to the default campaign at
`http://localhost:8080/campaign/review-tool-sandbox/`. Its health endpoint is
`http://localhost:8080/healthz`.

For repeatable local use, the dedicated Compose file avoids the production
reverse-proxy network and reads the same private environment and campaign map:

```bash
docker compose -f docker-compose.local.yml up -d --build
docker compose -f docker-compose.local.yml logs -f
```

Stop and remove only this local deployment with:

```bash
docker compose -f docker-compose.local.yml down
```

`CAMPAIGNS_FILE` is the preferred campaign configuration. It points to a JSON
file mapping stable URL identifiers to Git branches, optional display labels,
and an optional `enabled` boolean. An omitted `enabled` is equivalent to
`true`. Start from the tracked examples:

```bash
cp campaigns.example.json campaigns.json
cp docker-compose.override.example.yml docker-compose.override.yml
```

Keep `CAMPAIGNS_FILE=/app/config/campaigns.json` and the selected
`DEFAULT_CAMPAIGN` in `.env`. Docker Compose automatically reads the local
override and mounts `campaigns.json` read-only. Neither local file is tracked.
`CAMPAIGNS_JSON` remains a compatible one-line fallback; `CAMPAIGN_BRANCH`
remains the legacy single-campaign fallback. When `CAMPAIGNS_FILE` is set, it
takes precedence over both.

To close a completed campaign without deleting its Git history, set
`"enabled": false` in `campaigns.json`. Disabled campaigns cannot be opened,
including through a direct URL. If another campaign remains active,
`DEFAULT_CAMPAIGN` must identify an active campaign. If none remains active,
the application continues to run and its root page reports that no campaign is
active; an empty `{}` configuration is also valid. Keep the completed campaign
branch unchanged for audit and traceability.

Reviewers receive the relevant campaign URL. All campaigns share the same
GitHub OAuth callback and application process.

Changing only `campaigns.json` does not require rebuilding the Docker image.
Recreate the container so the application reloads the mounted file:

```bash
docker compose up -d --no-deps --force-recreate question-review
```

With profiling enabled, follow only the timing lines with:

```bash
docker logs --follow 50ohm-question-review-local 2>&1 \
  | grep -E '\[(github|request)_profile\]'
```

See [GitHub operation profiling](docs/GITHUB_PROFILING.md) for the log format
and interpretation.
The cache and write invariants are documented in
[Campaign cache and atomic writes](docs/CAMPAIGN_CACHE_AND_WRITES.md).

The browser keeps the selected reference language, active review language, and
last opened question in persistent preference cookies. On a later visit, valid
preferences are restored automatically. Values that are not available in the
current campaign are ignored.

Campaign progress is calculated from the current `question.meta.json` files,
not from review statuses copied into the derived navigation index at export
time. `Commit` and `Reopen` are therefore reflected on the overview immediately.

The current campaign integration loads the current branch and its original
export as two GitHub archives, then serves navigation and question reads from
an in-memory snapshot. The remote branch head is checked at most once per
`CAMPAIGN_REFRESH_SECONDS`. An open question is completed with one `Commit`
action: one atomic GraphQL commit writes changed text in the active language,
appends an optional working comment, and sets `review.<language>` to
`approved`. An approved question exposes `Reopen`, which only restores
`to_be_reviewed`. The expected branch-head SHA rejects concurrent changes.

The rendered active-language panel compares the current campaign text with the
export snapshot that introduced `campaign.meta.json`. This is the exact
content copied during export and does not require the reviewer's OAuth token to
access the separate canonical repository. Insertions and deletions therefore
remain visible after the correction has been committed.

Question drawings are resolved from `media.refs.json` and loaded from the
public media repository at the exact immutable commit recorded by the campaign.
The interface does not infer a published-site image URL from the numeric media
identifier.

After GitHub login, the interface reads `languages` and `editable_languages`
from `campaign.meta.json`. The reference and review languages are selected in
the table-of-contents page and carried through every navigation link. They may
be identical, which supports DE→DE, FR→FR, and IT→IT linguistic reviews.
Campaigns may contain only one language; in that case the same language is
selected automatically for reference and review.
Only a language listed in `editable_languages` can be selected for review. The
current example campaign exports and makes editable German, French, and
Italian, so all nine reference/review combinations are available.

The interface does not expose separate status or comment actions. `Commit` and
`Reopen` are the complete reviewer workflow. Rejecting a proposed correction
means committing the original text. The interface resolves the reviewer from
the latest Git commit that actually changed that language's status.

Comments are optional append-only working notes stored outside canonical
question data under `reviews/<question_id>.json`. They are submitted with
`Commit`, and the displayed author is derived from the commit that introduced
the comment.

Campaigns may optionally authorize structured detail editing through
`editable_metadata_fields` and `editable_picture_fields`. The editor then adds
conditional `Content` and `Metadata` tabs. Supported metadata paths use fixed
widgets; picture choices are limited to entries already resolved in
`media.refs.json`. The visible question number is accompanied by its copyable
canonical `question_id`, and editable question and answer fields fit their
initial content while remaining vertically resizable.

Forms and internal navigation display a blocking
`Please wait. Working with GitHub...` indicator while the synchronous GitHub
operation is running. It is reset on both normal page loads and browser page
restoration.

The comparison area uses the available desktop width in three equal columns:
the source language is labelled `(Reference)`, and status and comment history
are shown in the third column. In the edit area, the question occupies one
third and the four answer editors use the remaining two thirds. Answer letters
sit directly beside two-line, vertically resizable text areas. The optional
commit comment is placed below the text editors.

Previous/next question navigation stays inside the displayed chapter.
Previous/next section navigation follows the complete ordered list of selected
question-bearing chapters, including transitions between different canonical
parent sections.

`question.meta.json` is the only current source for a review status. The
derived navigation index is not updated by reviewers. Both the editor and the
table-of-contents progress use current metadata from the campaign snapshot.

The earlier approval-only path was verified end to end with `AB301/fr`: the
canonical importer dry-run reported one ready item, 41 not-approved items, no
conflicts, no invalid items, and `canonical_write_performed=false`.

For a private organization repository, the OAuth application must be granted
access to that organization. Otherwise authentication succeeds but campaign
reads return HTTP 403.

## Remembering the current campaign

The browser remembers the last active campaign in the persistent
`50ohm_last_campaign` cookie. Opening a campaign (including edit pages and
error responses for a valid campaign) updates the preference before the user
needs to log in. Logout clears the authentication session but preserves this
separate preference.

The root URL and login/logout without a campaign parameter choose:
1. An explicitly requested active campaign, when provided.
2. The browser's last campaign, if it still exists and is enabled.
3. DEFAULT_CAMPAIGN, if active.

An explicit invalid or disabled login URL remains a 404; a stale remembered
campaign or logout target falls back safely. With no active campaign, the
application displays the existing no-active-campaign page and does not start
OAuth. The OAuth callback still validates state and rechecks that the stored
campaign is active before returning to it.

The cookie lasts one year, uses path /, HttpOnly and SameSite=Lax, and is Secure
when SESSION_HTTPS_ONLY=true. It contains only a validated campaign identifier,
not a GitHub token. It is a browser preference, not access authorization, and
is local to the review-tool host. A link from the beta landing page updates it
when the campaign is opened. Selecting a campaign overrides an older preference.

Expired/revoked GitHub tokens are not renewed automatically. A GitHub 401 now
clears authentication and offers Login while retaining the active campaign
instead of returning to the global default. No OAuth callback, DNS or private .env changes
are required. Rebuild and recreate question-review to deploy this code change.

## Expired GitHub sessions and unsaved inputs

A GitHub HTTP 401 during campaign loading, editing or saving clears only the
authentication session and displays a reconnect page. The persistent campaign
preference is retained. HTTP 403 and 404 do not trigger logout: permissions,
policy restrictions or missing resources need diagnosis rather than a login loop.
No extra token-validation request is made before normal operations.

For a save with an expired/missing token, submitted editable fields (including
comments and repeated rationales) are preserved as a copyable JSON backup on the
reconnect page. When browser sessionStorage is available, a draft is saved locally
for that exact campaign, question and reference/review language pair. After signing
in, reopen that question with the same language pair to restore the inputs once.
Current SHA fields and action buttons are never restored; no write is replayed.
A banner asks the reviewer to check GitHub state before committing, because an
operation may have completed before a later API call returned 401.

Drafts contain review text/comments, not tokens, and remain local to that browser
tab and review-tool origin. Closing the tab clears them. If storage is blocked,
copy the displayed backup before leaving the reconnect page. Disabled inputs are
not overwritten; their values remain visible in the draft backup. Restoration
consumes the draft to avoid inserting an old comment after a successful commit.
Draft values are encoded safely as text/JSON, not interpreted as HTML.
