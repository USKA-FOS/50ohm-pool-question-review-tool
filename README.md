# 50ohm Pool Question Review Tool

## Overview
This tool is part of the Swiss 50ohm platform and is used to review the question pool for the platform. it is used for reviewing the French and Italian translations of the original question pool as well as any changes that need to be applied to the German version. The application is a web-based tool built with FastAPI and runs serverless on Google Cloud Run.

![Screenshot](/images/screenshot_review_tool.png)

## How it works
Users authenticate with their GitHub account, and the resulting OAuth2 token allows the application to retrieve questions and push changes to the repository containing the source data. The repository is defined in a `.env` file, with an example provided as `.env.example`.

Each question is stored in its own JSON file, and review comments are logged in the `HB.comments` field of the corresponding JSON. The `WIP` branch contains the latest version with all ongoing changes, which are always compared to the commit tagged `FR_orig_DeepL`. Original questions in German are taken from the commit `german_orig`. The `fragenkatalog3b.json` file is used for creating the table of contents; questions in this file are not used as they do not represent the latest state of our process.

Through the web interface, users can view questions, add review comments, and submit updates back to the repository.

## Deployment
A new container image is built and deployed automatically when changes are merged into the `deploy` branch, making deployment to Google Cloud Run seamless. To run the tool locally, you need to install the requirements as listed in `requirements.txt` and create a `.env` file based on `.env.example` where you provide the required environment variables.

## Local Docker baseline

The local GitHub OAuth application must use:

- homepage URL: `http://localhost:8080`
- callback URL: `http://localhost:8080/auth/callback`

Keep secrets outside the repository, for example in
`~/.config/50ohm-review-tool/local.env`. Build and start the local baseline with:

```bash
docker build --tag 50ohm-question-review-tool:campaign-readonly .

docker run --rm --detach \
  --name 50ohm-question-review-local \
  --publish 127.0.0.1:8080:8080 \
  --env-file ~/.config/50ohm-review-tool/local.env \
  --env GITHUB_OWNER=isqsoft \
  --env GITHUB_REPO=50ohm-question-review-campaigns \
  --env CAMPAIGN_BRANCH=campaign/multilingual-empfaenger-sinus-signals-example \
  --env GITHUB_CALLBACK_URL=http://localhost:8080/auth/callback \
  --env SESSION_HTTPS_ONLY=false \
  --env GITHUB_PROFILE=true \
  50ohm-question-review-tool:multilingual-review
```

The server is then available at `http://localhost:8080`. Its health endpoint
is `http://localhost:8080/healthz`.

With profiling enabled, follow only the timing lines with:

```bash
docker logs --follow 50ohm-question-review-local 2>&1 \
  | grep -E '\[(github|request)_profile\]'
```

See [GitHub operation profiling](docs/GITHUB_PROFILING.md) for the log format
and interpretation.

The current campaign integration reads the multilingual campaign and its
derived table of contents directly through the GitHub API. An open question is
completed with one `Commit` action: it writes changed text in the active
language, appends an optional working comment, and sets
`review.<language>` to `approved`. An approved question exposes `Reopen`, which
only restores `to_be_reviewed`. All writes use the GitHub file SHA to reject
concurrent changes.

The rendered active-language panel compares the current campaign text with the
first Git version of that localized file in the campaign branch. This is the
exact content copied during export and does not require the reviewer's OAuth
token to access the separate canonical repository. Immutable originals are
cached in memory after their first read. Insertions and deletions therefore
remain visible after the correction has been committed.

After GitHub login, the interface reads `languages` and `editable_languages`
from `campaign.meta.json`. The reference and review languages are selected in
the table-of-contents page and carried through every navigation link. They may
be identical, which supports DE→DE, FR→FR, and IT→IT linguistic reviews.
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

Forms and internal navigation display a blocking
`Please wait. Working with GitHub...` indicator while the synchronous GitHub
operation is running. It is reset on both normal page loads and browser page
restoration.

The editor uses the available desktop width in three equal columns: the source
language is labelled `(Reference)`, status and comment history are shown in a
side column, and the optional commit comment is placed beside the question and
answer editors.

Previous/next question navigation stays inside the displayed chapter.
Previous/next section navigation follows the complete ordered list of selected
question-bearing chapters, including transitions between different canonical
parent sections.

`question.meta.json` is the only current source for a review status. The
derived navigation index is not updated by reviewers. The editor therefore
shows the current status loaded from metadata; table-of-contents progress is
still based on the export snapshot in this intermediate implementation.

The earlier approval-only path was verified end to end with `AB301/fr`: the
canonical importer dry-run reported one ready item, 41 not-approved items, no
conflicts, no invalid items, and `canonical_write_performed=false`.

For a private organization repository, the OAuth application must be granted
access to that organization. Otherwise authentication succeeds but campaign
reads return HTTP 403.
