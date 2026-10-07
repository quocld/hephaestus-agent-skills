---
name: jira-touch
description: Quick Jira operations on DU projects (VOCO, WEST, CESP) — find/view tickets, transition status, comment, assign, create issues/sub-tasks. Use when asked to "check ticket", "chuyển status", "comment vào ticket", "tạo ticket/sub-task", or any lightweight Jira read/write that isn't worklog logging (use jira-worklog for hours).
---

# Jira Touch — quick ops (DU multi-project)

Lightweight Jira interactions for `https://digital-unicorn-group.atlassian.net`.

## Credentials & identity

Auto-exported from `~/.claude/settings.json` → `env`: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEYS` (=`VOCO,WEST,CESP`), `JIRA_ASSIGNEE_ID`. If empty in Bash, read from the file with python3+json. Auth via `curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN"` — always curl (Python urllib fails SSL with Atlassian on macOS). Never echo the token.

User = **Quoc Le (Ryan)**, accountId `712020:1593f4b8-651d-4a4b-901f-0c2edfd570e9`, TZ +0700.

## Projects

| Key | Name | Notes |
|---|---|---|
| VOCO | DU0429 - Voco | speaker directory; UAT bug tickets `[UAT][...]` |
| WEST | DU0431 - Westmont | Sprint work on **Sub-tasks** (`[FE]/[BE] US-xx` children of US Stories; bug children of umbrella tasks). BA/QA log daily `[dd/mm]` sub-tasks under WEST-1/WEST-165 |
| CESP | DU0386 - CESP | no delete-own-worklog permission; statuses include Ready for QA, QA In Progress, In UAT Review, Deployed, Declined |

## Endpoints (verified 2026-08)

Old `/rest/api/3/search` is **gone** — use `/rest/api/3/search/jql`. Add `--max-time 30` to every curl; parallelize bulk per-issue fetches with a script file + `xargs -P 10 -n 1`.

**Search** (`--data-urlencode` for jql/fields/maxResults):
```bash
curl -sS --max-time 30 -u "$JIRA_EMAIL:$JIRA_API_TOKEN" -G \
  "$JIRA_BASE_URL/rest/api/3/search/jql" \
  --data-urlencode 'jql=project IN (VOCO,WEST,CESP) AND assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC' \
  --data-urlencode 'fields=summary,status,issuetype,parent,assignee,updated' \
  --data-urlencode 'maxResults=50'
```

**View issue** (add `&expand=changelog` for status history — who moved it, when):
`GET $JIRA_BASE_URL/rest/api/3/issue/{KEY}?fields=summary,status,description,assignee,parent,timetracking`

**Transition**: first `GET /rest/api/3/issue/{KEY}/transitions` to list ids, then
`POST /rest/api/3/issue/{KEY}/transitions` with `{"transition":{"id":"<id>"}}` (204 = OK).

**Comment** (body must be ADF, English):
```bash
curl -sS --max-time 30 -u "$JIRA_EMAIL:$JIRA_API_TOKEN" -X POST -H "Content-Type: application/json" \
  -d '{"body":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"..."}]}]}}' \
  "$JIRA_BASE_URL/rest/api/3/issue/$KEY/comment"
```

**Assign**: `PUT /rest/api/3/issue/{KEY}/assignee` with `{"accountId":"$JIRA_ASSIGNEE_ID"}` (204).

**Create issue / sub-task** (`POST /rest/api/3/issue`, 201):
```json
{"fields":{"project":{"key":"WEST"},"issuetype":{"name":"Sub-task"},"parent":{"key":"WEST-xxx"},
 "summary":"[FE] ...","assignee":{"accountId":"..."},
 "description":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"..."}]}]}}}
```

**Estimate**: `PUT /rest/api/3/issue/{KEY}` with `{"fields":{"timetracking":{"originalEstimate":"2h"}}}` (204). Don't override an existing estimate.

## Rules

- Read ops: just do them. Write ops (transition, comment, create, assign): show what will change and confirm with the user first unless they already gave the exact instruction.
- Comments/summaries on Jira in **English**; conversation replies in the user's language.
- Worklog/hours tasks → use the `jira-worklog` skill instead.
