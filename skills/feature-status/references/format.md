# Status file format

This file owns the format of `docs/status/<ID>.md`, its tokens, and the state machine.
`scripts/status.py` parses and writes it; `python3 scripts/status.py <subcommand> --help` owns the exact flags.
Edit status files only through the script; `status.py check` rejects anything it cannot parse.

## ID and file name

- One file per feature: `docs/status/<ID>.md`, committed with the feature's code.
- `<ID>` is the ticket id (`WEST-123`) or, with no ticket, a kebab slug (`csv-export`).
- An ID matches `[A-Za-z0-9][A-Za-z0-9._-]*`, contains no `..`, and does not end in `.` or `.lock`.
- `docs/status/README.md` and `docs/status/.gitkeep` are not status files and are ignored, so `README` (in any case) is not a valid ID.

## Layout

```markdown
---
id: WEST-123
title: Invoice can be locked after payment
state: in-progress
branch: feat/WEST-123-invoice-can-be-locked-after-payment
picked_by: dev@example.com
picked_at: 2026-10-19T08:00:00Z
updated_at: 2026-10-19T10:12:45Z
pr:
spec: docs/specs/invoices.md#locking
---

## Acceptance criteria

- AC1: Paid invoice shows a lock icon | UT pass | IT na | E2E pass | evidence: e2e/reports/WEST-123-2026-10-19T10-00.json
- AC2: Locked invoice rejects edits with 409 | UT pass | IT pass | E2E todo

## Deferred

- Bulk unlock - not in this sprint - owner: PO

## Notes

- 2026-10-19 picked by dev@example.com on feat/WEST-123-invoice-can-be-locked-after-payment
- 2026-10-19 picked -> in-progress
```

## Frontmatter

Flat `key: value` lines between two `---` lines, no quoting, no nesting; every key is present, even when empty, and no other key is allowed.
A leading UTF-8 byte order mark (some editors add one) is ignored, and the next script edit drops it.

| Key | Value |
| --- | --- |
| `id` | The ID, equal to the file name without `.md` |
| `title` | One line, not empty |
| `state` | A state from the table below |
| `branch` | The feature branch, `<type>/<ID>-<slug>` or `<type>/<ID>`, with `<type>` one of feat, fix, refactor, chore, docs, test; `WEST-1` never accepts `feat/WEST-12-x` |
| `picked_by` | `git config user.email`, else `user.name`, of whoever ran `pick` |
| `picked_at` | UTC time of the pick, `YYYY-MM-DDTHH:MM:SSZ` |
| `updated_at` | UTC time of the last script edit, same format |
| `pr` | PR/MR URL (`http://` or `https://`), or empty |
| `spec` | Spec path or link, optional |

Deploy state (staging, prod) is never stored here; `status.py board --live` derives it from the `environments` skill's version status.

## Sections

The body has exactly these three `##` sections, in this order, and nothing else; blank lines are ignored.

### Acceptance criteria

`- AC<n>: <text> | UT <r> | IT <r> | E2E <r>` followed optionally by ` | evidence: <repo-relative path>`.

- `<n>` is a positive integer, unique within the file; the script keeps ACs sorted by it.
- `<text>` is one line and contains no `|`.
- Tiers: UT is unit, IT is integration, E2E is end to end through the real UI or API.
- `<r>` is one of the result tokens below.
- `evidence` is required when E2E is `pass` and must name a file that exists inside the repo and is the `e2e-verify` report: a `.json` file holding a non-empty JSON object with `"verdict": "PASS"` and an `"id"` equal to the ID, ignoring case.
  Any other file type (a screenshot, a log) is refused, with a message naming the `e2e-verify` format.
  `status.py ac` also warns when its `"commit"` is not an ancestor of HEAD.
- `status.py ac --text` that changes an existing AC's text resets all its tiers to `todo` (`na` included), drops its evidence, and adds a note, since a changed AC must be decided again.

| Result | Meaning |
| --- | --- |
| `todo` | Not verified yet |
| `pass` | Verified at this tier on the current spec |
| `fail` | Verified and failing |
| `stale` | Passed before, but the spec changed since; verify again |
| `na` | This tier does not apply to this AC |

### Deferred

`- <what> - <why> - owner: <who>`, where `<what>` contains no ` - `.

### Notes

`- <YYYY-MM-DD> <one line>`, at most 200 characters after the date.
Notes are short and link out; long reasoning goes in the PR description or a `flow-trace` file.
The script adds a note for every state change and every pick.

## States and transitions

| From | Allowed next states |
| --- | --- |
| `picked` | `in-progress`, `blocked`, `deferred`, `dropped` |
| `in-progress` | `in-review`, `blocked`, `deferred`, `dropped` |
| `in-review` | `in-progress` (failed review or QA), `merged`, `blocked`, `dropped` |
| `blocked` | `in-progress`, `deferred`, `dropped` |
| `deferred` | `in-progress`, `dropped` |
| `merged` | nothing through `set` |
| `dropped` | nothing through `set` |

- The table is what `set` allows within one pick; after `release`, a new `pick` starts a new cycle in state `picked`, also for a `dropped` feature.
- `picked`, `in-progress`, `in-review` and `blocked` are active: `pick` refuses an ID whose file on the integration branch is in one of them.
- `stale` moves `in-review` back to `in-progress` by itself, and refuses a `merged` file.
- A spec change or failed QA after the merge has one path: `release`, then `pick <ID> --slug <new-slug>` (a new branch), then `stale` in the new worktree.
- Leaving `deferred` or `blocked` for an active state fetches and requires `claim/<ID>` on origin to belong to this file's pick (same `branch` and `picked_at`), and `stale` on an `in-review` file does the same, so a released feature is never reopened without a lock.
- Setting `merged` requires at least one AC and every tier of every AC to be `pass` or `na`, with valid evidence on every E2E `pass`.
- A `merged`, `dropped` or `deferred` feature can be picked again; the new pick keeps its ACs, Deferred and Notes and resets the state to `picked`.
  The prior file is the one on the integration branch, otherwise the newest given-up branch's file.
  Its old feature branch does not block the re-pick, and neither does a branch whose own file says `deferred` or `dropped`; any other branch for the ID does, and a new branch name needs `--slug` while the old branch still exists.

## Claims

- The claim on a feature is the remote branch `claim/<ID>`; it is not a lock file in a worktree, so every clone sees it after a fetch.
- `pick` creates `claim/<ID>` and the feature branch in one `git push --atomic` with create-only leases, so of two concurrent picks exactly one wins and the loser leaves nothing behind.
- `pick --resume` by the claim's `picked_by` refuses while the claim's local worktree changed in the last 30 minutes (the newest of its private git `index`, `HEAD`, `agent-progress.md`, and its status file), since parallel agents share one git identity; `--takeover` overrides it only after the user confirms the other session is dead.
- `pick` refused on a stale claim (that pick is `merged`, `dropped` or `deferred`) suggests only `release`, never `--resume`.
- Both refs point at one commit on top of the integration branch that adds the status file in state `picked`; the commit is built with plumbing, so the checkout `pick` runs from is never modified.
- `release` deletes `claim/<ID>` only on evidence from the claim's own pick: a version of the file with the claim's `branch` and `picked_at` that is `merged` on the integration branch (the PR/MR is merged), or `dropped` or `deferred` there or on the pushed feature branch (the checkout's copy counts only when that branch is gone from origin).
  An earlier pick's merged file never releases a re-pick, and the delete is leased on the claim commit it judged, so a claim that changes meanwhile is kept.

## What `check` rejects

`check` reads the working tree; `check --ref <ref>` reads the files committed at that ref and also requires every E2E evidence file to be committed there, which is what the PR/MR hook runs.

- A file that does not follow the layout above, including an unknown frontmatter key, section, or token.
- A missing frontmatter key, an `id` that differs from the file name, an empty `title`, `branch` or `picked_by`, or a malformed timestamp or `pr`.
- An unknown state, or a `branch` that is not `<type>/<ID>` or `<type>/<ID>-<slug>`.
- An E2E `pass` without valid evidence.
- `merged` with no AC, or with any tier that is not `pass` or `na`.
