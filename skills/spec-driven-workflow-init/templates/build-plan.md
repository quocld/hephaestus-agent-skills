# Build plan — {{PROJECT_NAME}}

## Legend

- `[x]` Done — every item in the change's proposal scope shipped; zero open Defer. Production-ready.
- `[~]` Partial — code merged but at least one item is deferred with a named owner. Stays `[~]` until owner ships.
- `[ ]` Not started.

A `Defer:` note in the comment column **does not** upgrade `[~]` to `[x]`. The note column documents; the tick authorises.

## Tracker

| # | Item | Sprint | Change id | Specs | BE | FE | Done | Notes |
|---|------|--------|-----------|-------|----|----|------|-------|
|   |      |        |           | [ ]   | [ ]| [ ]| [ ]  |       |

## Defer registry

Every deferred item that doesn't roll into a sibling change goes here as its own `[ ]` row. NOT as a note inside a `[x]` row.

| Origin change | Item | Owner | Target |
|---------------|------|-------|--------|
|               |      |       |        |

## Archived changes

Move each shipped change to `openspec/changes/archive/<YYYY-MM>-<id>/`. Reference here for traceability.

| Archived | Change id | Date | Summary |
|----------|-----------|------|---------|
|          |           |      |         |
