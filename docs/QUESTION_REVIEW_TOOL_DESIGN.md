# Question Review Tool Design

## Purpose

The question review tool is a Git-backed web editor for bounded multilingual
review campaigns. It lets human reviewers compare, correct, comment on, and
approve selected canonical questions without editing the canonical repository
directly.

The tool is deliberately not a second canonical database. Its output is a
committed campaign branch that must pass the canonical dry-run and import tools
in `50ohm-question-pool` before publication.

## System boundary

The workflow has three independent repositories:

1. `50ohm-question-pool` owns canonical questions, campaign export, validation,
   and controlled import.
2. `50ohm-question-review-campaigns` stores one shared Git branch per campaign,
   including its working history.
3. `50ohm-pool-question-review-tool` provides the web interface and writes only
   to the configured campaign branch.

The question pool remains authoritative. The campaign repository is durable
working memory. The application itself has no business database.

## Campaign model

One deployment serves one or more named campaign branches through
`GITHUB_OWNER`, `GITHUB_REPO`, `CAMPAIGNS_JSON`, and `DEFAULT_CAMPAIGN`.
Each campaign is exposed under `/campaign/<campaign-id>/`. A branch contains:

- `campaign.meta.json`, including immutable canonical provenance, scope,
  available languages, and editable languages;
- canonical-shaped localized question files and question metadata under
  `pool/questions/<question_id>/`;
- generated read-only navigation under `derived/`;
- optional append-only working comments under `reviews/`;
- resolved media provenance in `media.refs.json`.

No review-tool-specific field is added to localized canonical question data.
The complete format is defined by `CAMPAIGN_CONTRACT_V1.fr.md`.

## Application architecture

The application is a compact server-rendered FastAPI service:

- Jinja templates produce the overview and question editor;
- GitHub OAuth authenticates reviewers and authorizes repository operations;
- the GitHub REST API reads branch state, archives, user identity, and commit
  history;
- the GitHub GraphQL API creates one atomic commit for each review action;
- KaTeX renders formula content in the browser;
- Docker packages the application for local or server deployment.

There is no client-side application state framework, queue, worker, or local
database. Request processing is synchronous.

## Read path and cache

On the first authenticated request for a campaign, the service loads two
repository archives:

- the current campaign branch snapshot;
- the immutable campaign export snapshot used for text differences.

JSON files are parsed into an in-memory snapshot keyed by campaign id.
Navigation and question reads
then require no per-file GitHub request. After `CAMPAIGN_REFRESH_SECONDS`, the
service checks only the remote branch head. It downloads a new current archive
only when that head changed. The original export snapshot never changes.

Git blob hashes are computed locally so forms can still detect stale content.
Status and comment authors are derived from Git commit history and cached by
campaign id and blob hash.

The root URL redirects to `DEFAULT_CAMPAIGN`. Review URLs have the stable form
`/campaign/<campaign-id>/...`. GitHub OAuth uses one callback URL for the whole
deployment; the requested campaign id is kept in the signed session while the
reviewer authenticates and is used for the post-login redirect.

## Review interaction

The overview derives structure from the generated navigation index but derives
progress from current `question.meta.json` files. Export-time statuses are not
used as live state.

The reviewer can independently choose:

- any campaign language as the reference language;
- any `editable_languages` entry as the active review language.

The selections may be identical, enabling DE-to-DE, FR-to-FR, and IT-to-IT
review. Persistent browser cookies remember both languages and the last opened
question. Remembered values are accepted only when valid for the current
campaign.

The editor displays:

- the current active-language text with differences from its export version;
- the selected reference-language text;
- current review status and Git-derived author;
- existing comments and their Git-derived authors;
- an editable question field occupying one desktop column;
- full-width two-line answer text areas occupying the other two columns, with
  A-D labels beside the fields and vertical resize handles;
- an optional comment field and ordered navigation controls.

`null` and empty strings remain distinct. Image-backed `null` fields are not
turned into editable empty text.

## Write path

The interface exposes two workflow actions:

- `Commit` saves changed active-language content, appends an optional comment,
  and sets `review.<language>` to `approved`;
- `Reopen` changes only that status to `to_be_reviewed`.

All files belonging to one action are written in a single GraphQL
`createCommitOnBranch` mutation. `expectedHeadOid` binds the mutation to the
branch head read by the application. A concurrent branch update therefore
causes a conflict rather than an overwrite. The in-memory snapshot is updated
only after GitHub confirms the commit.

Comments contain text only. Reviewer identity, time, order, and exact changes
come from Git history rather than duplicated JSON metadata.

## Canonical return path

The web application never writes the canonical pool. Canonical return is an
operator-controlled process in `50ohm-question-pool`:

1. check out the committed campaign branch;
2. generate and inspect a dry-run import report;
3. run `import_question_review_campaign.py --apply`;
4. inspect the canonical diff and application report;
5. rebuild affected publication artifacts;
6. commit and push the complete canonical change.

Only approved, valid, non-conflicting question/language pairs are imported.
Campaign comments and generated navigation are never canonical input. Import
reports may snapshot the comments for traceability while keeping them outside
canonical question content and metadata.

## Principal properties

- **Canonical isolation:** reviewers cannot directly mutate the canonical pool.
- **Flexible scope:** campaign selection may come from chapters, explicit ids,
  automated findings, or any future selection policy.
- **Symmetric languages:** German, French, and Italian use one workflow.
- **Minimal metadata:** status remains in canonical-shaped question metadata;
  temporary comments remain outside canonical data.
- **Auditable collaboration:** one shared Git branch records authors, commits,
  diffs, and chronology.
- **Optimistic concurrency:** branch-head and file-hash checks prevent silent
  overwrites.
- **Non-destructive import:** current canonical divergence becomes a conflict.
- **Low infrastructure:** the application requires GitHub and one web process,
  not an application database.

## Limitations

- Campaigns must be declared in `CAMPAIGNS_JSON`; the interface does not
  discover arbitrary repository branches or offer an unrestricted branch
  selector.
- The in-memory cache is process-local. Multiple application instances each
  maintain their own snapshot and observe remote changes on their next head
  check.
- The first authenticated load downloads two complete campaign archives and is
  slower than warm navigation.
- GitHub availability, API latency, OAuth authorization, and rate limits remain
  external dependencies.
- Requests and GitHub writes are synchronous; there is no background job or
  offline editing mode.
- The OAuth access token is stored in Starlette's signed client-side session
  cookie. The cookie is integrity-protected but not encrypted. A production
  hardening step should move tokens to server-side session storage.
- All reviewers in one campaign share its branch. Git prevents silent
  overwrites, but the tool has no reservation or question-lock mechanism.
- Comments are append-only in the interface and cannot be edited or deleted.
- Drawing display requires the public GitHub raw-content service. URLs are
  resolved from `media.refs.json` at its immutable media commit; private media
  repositories are not currently proxied through the reviewer OAuth token.
- Chapter data, drawings, and photos are read-only campaign context.
- The application does not run technical correctness checks, linguistic AI
  audits, canonical builds, commits, pushes, or site publication.
- Import can apply eligible pairs while leaving conflicts or open items behind;
  operators must inspect the complete report rather than treating command
  success as campaign completion.

## Operational diagnostics

`GITHUB_PROFILE=true` enables per-call and per-request timing logs without
logging OAuth tokens, question text, or JSON payloads. `/healthz` provides a
container health endpoint. Details are documented in `GITHUB_PROFILING.md` and
`CAMPAIGN_CACHE_AND_WRITES.md`.
