# Campaign Workflow Discussion Draft

## Scope

This document summarizes the currently intended review-campaign workflow in a
form suitable for validation with the person who designed the existing
`50ohm-review-workflow-tool` process.

This is a discussion draft only. It does not yet define the final
implementation contract.

## Core Principles

- The canonical repository remains the only durable source of truth.
- A review campaign always starts from a frozen canonical baseline commit or
  tag.
- Campaign work is exported into the review-tool repository.
- Reviewers work independently on separate Git branches.
- Intermediate campaign state is stored in Git, not in a database.
- `HB.state` and `HB.comment` are campaign-only fields.
- `HB.state` and `HB.comment` are never consolidated back into the canonical
  repository.
- Import back into canonical is explicit, controlled, and item-based.
- Partial import must be possible.

## High-Level Workflow

### 1. Campaign creation

A campaign is created from a frozen canonical baseline.

The baseline must be an explicit Git commit or tag so that the source material
is stable and traceable.

### 2. Campaign export into the review repository

The export step creates the campaign files inside the review-tool repository.

These files contain at least:

- a campaign manifest;
- the list of review items;
- the source content needed by reviewers;
- the control metadata required for later reintegration.

At this stage, the canonical repository is not modified.

### 3. Independent reviewer branches

Each reviewer creates a separate Git branch from the campaign state.

The reviewers therefore work independently and do not share mutable in-progress
state.

The branch is the reviewer’s working area.

### 4. Intermediate work state

All intermediate review state is stored in the campaign files committed in the
reviewer branch.

This includes:

- reservation/claim state;
- work-in-progress state;
- completion state;
- reviewer comments needed during the campaign.

`HB.state` and `HB.comment` are intended for this temporary campaign-level use.

They are not part of the durable canonical data model.

### 5. First review

The first reviewer processes the assigned items and advances them through the
first-review stages.

The exact stage labels can remain aligned with the current workflow, for
example:

- ` `: free;
- `1W`: reserved for first review;
- `1A`: first review in progress;
- `1F`: first review completed.

### 6. Optional second review

The second review stage must remain flexible.

Depending on the campaign, an item may:

- go through a full second human review;
- go through a lighter validation step;
- be checked by AI;
- skip second review entirely.

The current second-review stage family can still be used when needed:

- `2W`;
- `2A`;
- `2F`.

However, the workflow must not require this stage in every campaign.

### 7. Consolidation

The approved reviewer results are consolidated into a reference campaign branch.

This consolidated branch becomes the authoritative campaign result for later
integration.

It is the review-campaign equivalent of an approved working state, but it is
still separate from canonical.

### 8. Explicit import into canonical

Reintegration into canonical is performed from the consolidated campaign branch
through a dedicated import step.

The import is applied item by item.

This is important because the import must never block the whole campaign if one
item has become outdated or conflicting.

### 9. Partial import

Partial import must be supported.

If some items are valid and others are no longer applicable, the valid items
should still be integrated.

Items that cannot be integrated must be reported and removed from the active
campaign flow.

### 10. Removal from active campaign scope

Once an item has been successfully imported into canonical, it must no longer
be available as an active item in the campaign.

It may still remain visible in Git for audit and traceability, but it must no
longer appear as open work.

### 11. Canonical persistence rules

After import, only durable approved content and durable workflow metadata may
remain in canonical.

The following campaign-only information must not be preserved in canonical:

- `HB.state`;
- `HB.comment`;
- reviewer reservations;
- campaign branch mechanics;
- intermediate operational history.

### 12. Handling source changes during a campaign

The import process must never block globally if the canonical source has
changed since the campaign started.

Instead, reconciliation must happen item by item.

In practice, German source changes are the main case to consider.

If the German source changes and this affects translation validity, the import
or post-import workflow may update the durable translation review metadata, for
example by setting `review_status_fr` and/or `review_status_it` to
`to_be_reviewed`.

## What This Implies

### Campaign state lives in Git

The workflow state is not owned by a database.

The review repository and its branches carry the effective campaign state.

### `WIP` is not a core business concept

`WIP` may still exist as a branch name or local convention, but it should not
be treated as the main business abstraction.

The actual source of truth during a campaign is the set of versioned campaign
files in Git.

### The review tool is a client of canonical

The review system must not become a second canonical repository.

It should:

- receive exported work from canonical;
- support reviewer work;
- consolidate approved results;
- hand them back through a controlled import.

## Current Understanding Summary

The intended workflow is therefore:

1. Create a campaign from a frozen canonical baseline.
2. Export campaign files into the review repository.
3. Let each reviewer work independently on a separate Git branch.
4. Store all intermediate campaign state in Git-managed campaign files.
5. Use `HB.state` and `HB.comment` only during the campaign.
6. Consolidate approved work into a reference campaign branch.
7. Import approved results explicitly back into canonical.
8. Allow partial import.
9. Remove imported items from the campaign’s active work pool.
10. Keep campaign-only state out of canonical.

## Open Points To Confirm

The following points should be confirmed with the owner of the current workflow:

- whether the current branch strategy already matches this model closely enough;
- whether campaign consolidation should happen through merge, manual selection,
  or a dedicated consolidation tool;
- whether second review may be skipped per campaign or per item;
- whether AI review should be modeled as a formal stage or only as an optional
  validation mechanism;
- how imported items should be marked in campaign artifacts after partial
  integration.
