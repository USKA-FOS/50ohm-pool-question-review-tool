# French Question Review Prototype Assessment

Technical abbreviations used below are explained in the
[French glossary](GLOSSARY.fr.md).

## Scope

This assessment covers prototype commit `859a5a5`. The implementation was read
without modification. Only this new `docs/` directory was added.

The prototype is not currently compatible with the canonical
`50ohm-question-pool` workflow and must not be connected to that repository in
write mode before the data, review, and security contracts below are resolved.

## Current Architecture

The application is a compact server-rendered FastAPI service:

- GitHub OAuth provides a user token;
- GitHub's Contents and Compare APIs provide source, baseline, and work data;
- `fragenkatalog3b.json` builds an in-memory table of contents;
- Jinja templates show German and French side by side;
- `difflib.SequenceMatcher` highlights changes between the original and WIP
  French text;
- a form writes one JSON question directly to the GitHub `WIP` branch;
- KaTeX renders formulas in the browser;
- the Dockerfile starts Uvicorn on port 8080 for Cloud Run.

Useful prototype choices worth preserving are the side-by-side review view,
per-question navigation, visible answer-key convention, word-level change
display, formula rendering, Git-backed audit trail, and SHA-based conflict
detection.

## Canonical Compatibility Gaps

### Critical: obsolete repository contract

The prototype reads and writes `questions/<number>.json` using the fixed refs
`german_orig`, `FR_orig_DeepL`, and `WIP`. The current canonical repository
stores one stable object per directory:

```text
pool/questions/<question_id>/question.meta.json
pool/questions/<question_id>/question.de.json
pool/questions/<question_id>/question.fr.json
pool/questions/<question_id>/question.it.json
```

Published numbers such as `AF610` are mutable external identifiers. The review
tool must resolve them through canonical metadata and use `question_id` as its
processing identity. Baseline and candidate revisions must be explicit inputs,
not hard-coded historical refs.

### Critical: writes bypass canonical review semantics

The save route adds `review` and `HB.comments` directly to the legacy question
JSON and commits every form submission to `WIP`. Those fields are not part of
the current localized question payload contract. Canonical approval belongs in
`question.meta.json` through `review_status_fr`; question text belongs in
`question.fr.json`.

A future write operation must update text and review metadata as one reviewed
change set. Because GitHub's Contents API commits files individually, use a
Git tree/commit transaction or a pull-request workflow when more than one
canonical file changes.

### High: review progress is not review state

The index treats every file changed between `FR_orig_DeepL` and `WIP` as
reviewed. A changed file may still be rejected or awaiting review. Progress
must be derived from canonical review status or a dedicated review artifact,
not from branch-diff membership.

The Compare API result is also incomplete for large campaigns unless all pages
and platform limits are handled.

### High: the table of contents is a hard-coded sample

`toc_helper.py` reads the bundled legacy catalog, keeps only the first chapter,
and filters question numbers to `NA`, `NB`, and `AF`. It cannot represent the
current full pool. Navigation and counts can raise lookup or empty-list errors
when GitHub returns questions outside this sample.

The table of contents must be generated from a deterministic canonical export
or a question-pool API contract. The bundled 1.3 MB catalog should not become a
second source of question truth.

## Security Findings

### Critical: unsafe HTML in the diff renderer

`render_diff()` inserts repository text into HTML strings, and the templates
mark the result as `safe`. A question or answer containing HTML can therefore
execute in a reviewer's browser. Escape every text fragment before wrapping
insertions and deletions, and return a trusted markup type only after escaping.

### Critical: OAuth flow lacks CSRF state

The authorization request and callback do not generate or verify OAuth
`state`. Add a cryptographically random, session-bound state value and reject
callbacks that do not match it.

### High: GitHub token is stored in the session cookie

Starlette's default session middleware signs cookie contents but does not make
them confidential. Storing the GitHub access token there exposes it to the
client. Store tokens server-side and keep only an opaque session identifier in
the cookie. Enforce HTTPS, `Secure`, `HttpOnly`, and an appropriate `SameSite`
policy.

### High: authentication is not authorization

Any authenticated account whose token can access the configured repository is
accepted. Add an explicit organization, team, or user allow-list and verify it
before showing or changing review data. Request the narrowest GitHub permission
set; the current OAuth `repo` scope is broad.

### High: write requests lack application CSRF protection

The edit form has no CSRF token. Add a per-session form token and verify it on
every state-changing request.

### Medium: deployment hardening is absent

Dependencies are unpinned, the container runs as root, and there is no
`.dockerignore`. `COPY . .` can include a local `.env` or `.git` directory in a
container image. Pin dependencies, exclude secrets and repository internals,
run as a non-root user, and add automated dependency and container checks.

## Reliability And Data-Quality Findings

- GitHub requests have no timeout, retry policy, or API-version header.
- OAuth token exchange and user lookup do not validate unsuccessful responses
  before storing session data.
- global mutable table-of-contents review flags are shared across requests and
  never reset, which produces stale process-local state.
- empty comments are appended because an empty form string is not `None`.
- image conditions for answers B, C, and D test `picture_a` instead of their
  corresponding image fields.
- formula display depends on public CDN assets and has no documented offline or
  availability strategy; project-specific LaTeX macros are not defined.
- exceptions are returned as raw HTML error details.
- no automated tests, lint configuration, health endpoint, or checked-in Cloud
  Run deployment workflow is present.

## Recommended Target Boundary

The review tool should remain a client of `50ohm-question-pool`:

1. create each review campaign directly from an immutable canonical commit or
   tag;
2. copy only the selected canonical objects into a disposable sandbox WIP
   branch;
3. identify questions by stable `question_id`, displaying `internal_code` only
   as a reviewer-facing label;
4. keep question content in `question.<language>.json` and the durable current
   status in `question.meta.json`;
5. keep intermediate decisions and useful comments in a small, disposable
   campaign history in the sandbox;
6. import only approved results after confirming that their canonical source
   content has not changed since the campaign baseline;
7. omit sandbox history, reviewer names, and work comments from the canonical;
8. let question-pool validation and rebuild tooling gate integration.

The detailed data flow and the justification for each retained datum are
defined in the
[canonical/sandbox review workflow](CANONICAL_SANDBOX_REVIEW_WORKFLOW.fr.md).

The first canonical adaptation should be read-only. Write support should be
enabled only after fixtures prove exact loading, LaTeX rendering, identity
resolution, review-state transitions, concurrent-edit rejection, and complete
audit persistence.

## Proposed Delivery Sequence

1. Freeze the prototype and add characterization tests around its useful UI
   behavior.
2. Define a versioned read contract in `50ohm-question-pool` for review items.
3. Replace hard-coded refs and the bundled table of contents with explicit
   configuration and canonical data.
4. Harden authentication, authorization, sessions, escaping, and CSRF before
   exposing any canonical data.
5. Implement read-only French review with deterministic LaTeX fixtures.
6. Define the minimal disposable campaign-history schema and atomic canonical
   import strategy.
7. Add reviewed branch/PR writes behind feature flags.
8. Add integration tests against a temporary Git repository before deployment.

## Decisions Required Before Implementation

- candidate selection within an immutable canonical baseline;
- exact allowed review-state transitions for French;
- reviewer authorization source and least-privilege GitHub integration model;
- image source and offline behavior;
- exact sandbox branch lifecycle and cleanup point;
- deployment owner, environment, secrets storage, and rollback procedure.
