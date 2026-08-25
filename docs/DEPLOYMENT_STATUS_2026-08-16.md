# Deployment status on 2026-08-16

This document records the exact state reached while deploying the question
review tool on `jp2s`. It intentionally contains no OAuth client secret, session
secret, access token or browser cookie.

## Repositories and branches

The application is an independent Git repository:

- local path: `/home/jjcarron/docker/jp2s/50ohm-pool-question-review-tool`;
- remote: `git@github.com:USKA-FOS/50ohm-pool-question-review-tool.git`;
- active branch: `design/object-centric-canonical`;
- upstream: `origin/design/object-centric-canonical`;
- deployment changes are not committed yet.

The reverse proxy is a second independent repository:

- local path: `/home/jjcarron/docker/jp2s/jp2s_rproxy`;
- active branch: `master`;
- the branch was already one commit ahead of `origin/master` before the QRT
  exception was added;
- the QRT proxy changes are not committed yet.

The parent repository `/home/jjcarron/docker/jp2s` must not absorb the
application repository. The application keeps its own `.git` directory.

## Running deployment

The application is available at:

```text
https://qrt.jp2s.ch/
```

Docker state at the time of this snapshot:

- Compose service: `question-review`;
- container: `50ohm-question-review`;
- image: `50ohm-pool-question-review-tool:local`;
- internal port: `8080`;
- no host port is published;
- network: external `rproxy_net`;
- restart policy: `unless-stopped`;
- health status: `healthy`.

The non-secret runtime settings are:

```dotenv
APP_HOST=qrt.jp2s.ch
GITHUB_OWNER=jjcarron
GITHUB_REPO=50ohm-question-pool-test
GITHUB_CALLBACK_URL=https://qrt.jp2s.ch/auth/callback
SESSION_HTTPS_ONLY=true
```

The real `.env` exists only on the server, is ignored by Git and must remain
private. It also contains `LETSENCRYPT_EMAIL`, `GITHUB_CLIENT_ID`,
`GITHUB_CLIENT_SECRET` and `SESSION_SECRET`.

## Implemented deployment changes

The application working tree currently contains:

- `docker-compose.yml` for `nginx-proxy` and `rproxy_net`;
- `.dockerignore` and `.gitignore`, including `.env` and `.work/` exclusions;
- a non-root container user with UID `10001`;
- a `/healthz` endpoint and Docker health check;
- required configuration validation at startup;
- secure session cookies;
- OAuth `state` validation;
- explicit OAuth callback configuration and HTTP timeouts;
- the Starlette 1.6-compatible `TemplateResponse(request, name, context)` calls;
- deployment instructions in `README.md` and `.env.example`.

The proxy working tree currently contains:

- `.gitignore` exception for `vhost.d/qrt.jp2s.ch_location`;
- `vhost.d/qrt.jp2s.ch_location`, containing:

```nginx
auth_request off;
auth_basic off;
```

The proxy exception is required because `vhost.d/default_location` applies
Authelia to every new virtual host. QRT uses GitHub OAuth instead; keeping
Authelia would produce an unnecessary double authentication.

## Completed validation

The following checks passed:

- the Docker image builds successfully;
- the application runs as UID `10001`, not root;
- `docker compose ps` reports the container as healthy;
- `https://qrt.jp2s.ch/healthz` returns `{"status":"ok"}`;
- `https://qrt.jp2s.ch/` returns HTTP 200;
- `https://qrt.jp2s.ch/login` returns HTTP 307 to GitHub;
- the OAuth redirect uses callback
  `https://qrt.jp2s.ch/auth/callback`;
- nginx includes `vhost.d/qrt.jp2s.ch_location` in the generated QRT server;
- GitHub successfully redirects back to `/auth/callback`;
- Python compilation and `git diff --check` passed;
- temporary test containers, Python caches and repository clones were removed.

## Unresolved issues

### GitHub API authorization

OAuth login completes, but the application receives HTTP 403 while reading the
configured private repository through the GitHub API. The response body and the
relevant GitHub headers have not yet been captured, so the exact cause is not
proven. Missing Git references would normally produce HTTP 404, not HTTP 403.

The next diagnostic must record, without exposing the token:

- the GitHub JSON error message;
- `X-OAuth-Scopes`;
- `X-Accepted-OAuth-Scopes`;
- `X-GitHub-SSO`, when present;
- the authenticated GitHub login.

### Prototype data model mismatch

The legacy prototype expects:

```text
questions/<key>.json
FR_orig_DeepL
german_orig
WIP
```

Both `USKA-FOS/50ohm-question-pool` and the private test copy
`jjcarron/50ohm-question-pool-test` were inspected with `git ls-remote`. They
have the same references, but neither contains the three legacy references.
The checked-out repository also has no `questions/` directory. Its current
object-centric structure includes:

```text
pool/
raw/
review/
builds/
```

No artificial `FR_orig_DeepL`, `german_orig` or `WIP` branch was created, and no
commit or push was made to the private test repository. Creating those names at
`master` would not make the editor functional because the expected files do not
exist.

## Agreed next direction

Continue on `design/object-centric-canonical` and adapt the application to the
canonical object-centric model instead of reproducing the obsolete branch
workflow.

Recommended sequence for the next session:

1. Improve safe GitHub error diagnostics and resolve the current HTTP 403.
2. Read the canonical workflow documents and inspect representative files under
   `pool/`, `raw/` and `review/`.
3. Specify which objects are displayed, compared and edited, and where review
   work is written.
4. Implement read-only canonical browsing first.
5. Add write operations only after the target review/sandbox workflow is
   explicitly validated.
6. Test exclusively against `jjcarron/50ohm-question-pool-test` before enabling
   access to the `USKA-FOS` repository.

## Resume commands

Application status and logs:

```bash
cd /home/jjcarron/docker/jp2s/50ohm-pool-question-review-tool
git status --short --branch
docker compose ps
docker compose logs --since 10m --tail 200 question-review
```

Public checks:

```bash
curl -fsS https://qrt.jp2s.ch/healthz
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' \
  https://qrt.jp2s.ch/login
```

Proxy state:

```bash
cd /home/jjcarron/docker/jp2s/jp2s_rproxy
git status --short --branch
docker exec nginx-proxy nginx -t
```

Do not print `.env`, OAuth cookies or Docker environment variables containing
secrets in logs or documentation.
