---
name: jira-worklog
description: Audit and log Jira worklogs across ALL DU projects (VOCO, WEST, CESP). Use when asked to check missing hours ("check worklog", "thiếu giờ", "ngày nào thiếu"), log work ("log giờ", "logwork tuần này"), or top up worklogs. Read-only audit by default; logging requires explicit user confirmation.
---

# Jira Worklog — audit & log (DU multi-project)

Audits logged hours per day (target 8h/working day) and logs work to Jira, across **all** of the user's projects at once.

## Credentials & identity

Env vars are auto-exported from `~/.claude/settings.json` → `env` into every session:
`JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEYS` (=`VOCO,WEST,CESP`), `JIRA_ASSIGNEE_ID` (the user's accountId).

If a var is empty in the Bash environment, load it from the file:

```bash
V=$(python3 -c "import json; print(json.load(open('$HOME/.claude/settings.json'))['env']['JIRA_API_TOKEN'])")
```

The user is **Quoc Le (Ryan)**, accountId `712020:1593f4b8-651d-4a4b-901f-0c2edfd570e9`, timezone `+0700` (Asia/Ho_Chi_Minh). Auth: `curl -u "$JIRA_EMAIL:$JIRA_API_TOKEN"` (always curl, never Python urllib — macOS SSL handshake fails with Atlassian).

## API facts (verified 2026-08)

- Search endpoint is **`/rest/api/3/search/jql`** — the old `/rest/api/3/search` is gone/hangs. Response: `{"issues":[...],"isLast":true}`.
- Per-issue worklogs: `GET /rest/api/3/issue/{KEY}/worklog?maxResults=1000`. Sequential fetches are SLOW (can hang minutes) → always fan out with `xargs -P 10` and `curl --max-time 25`, writing one JSON file per issue to the scratchpad. `xargs` chokes on long inline commands — put the curl in a small script file and `xargs -P 10 -n 1 script.sh`.
- Worklog day bucket = first 10 chars of the worklog's `started` field.
- POST worklog returns **201**; PUT (edit) returns **200**; DELETE returns **204**; PUT estimate returns **204**.
- **CESP does not grant "delete own worklog"** (DELETE → 400 "you do not have permission"). Editing own worklogs works (`PUT {"timeSpent":"..."}`, minimum `1m`). So post to CESP extra carefully — a mistake can only be shrunk, not removed. VOCO and WEST allow deleting own worklogs.

## Audit flow (read-only, default 8h/day, weekends skipped)

1. Resolve date range from the request (today / yesterday / a week / `--month=YYYY-MM`).
2. Find candidate issues — **never filter to a single project**:
   ```
   JQL: project IN (VOCO, WEST, CESP) AND worklogAuthor = currentUser()
        AND worklogDate >= "<start>" AND worklogDate <= "<end>"
   ```
   (fields=summary, maxResults=100 via `/rest/api/3/search/jql`)
3. Fan-out fetch each issue's worklogs (parallel, see above), keep entries where `author.accountId == $JIRA_ASSIGNEE_ID` and `started[:10]` in range, sum seconds per day.
4. Report a per-day table: date, weekday, logged, OK / SHORT (missing X). Weekends `—` unless asked. Tolerance: `>= 8h - 1s` is OK.

**Lesson learned (2026-08-14):** an audit that filtered `project = VOCO` reported 0h for a week where 17h were already logged on WEST/CESP, which then nearly caused double-logging. Always sweep all three projects, and always re-fetch existing worklogs for the target days immediately before posting.

## Logging flow

1. **Reconstruct what was done** from evidence, per day:
   - `git log --since/--until` in the relevant repo(s) (commit times + subjects → tickets).
   - Jira status transitions: `GET /rest/api/3/issue/{KEY}?expand=changelog` — who moved what to Ready for QA / Done / Deployed and when.
   - WEST convention: time is logged on **Sub-tasks** (`[FE]`/`[BE] US-xx` children, bug children of an umbrella task), not on Stories.
2. **Check existing worklogs for every target day first** (audit flow step 2–3). Only plan the *gap* up to 8h/day. Never assume a day is empty.
3. Build the plan: 8h/day, start 09:00, lunch 12:30–13:30 skipped, consecutive `started` timestamps (`YYYY-MM-DDTHH:MM:SS.000+0700`), 15-minute rounding, min 15m/ticket. Weight hours by complexity (files changed / scope).
4. **Show the full plan table and get explicit user confirmation (AskUserQuestion) before any POST.** Also ask the estimate policy (1:1 / ×1.2 / skip).
5. Post each entry (comment in **English**, concise, ADF format):
   ```bash
   curl -sS --max-time 25 -o /dev/null -w "%{http_code}" -u "$JIRA_EMAIL:$JIRA_API_TOKEN" \
     -X POST -H "Content-Type: application/json" \
     -d '{"timeSpent":"1h 30m","started":"2026-08-13T09:00:00.000+0700","comment":{"type":"doc","version":1,"content":[{"type":"paragraph","content":[{"type":"text","text":"<english comment>"}]}]}}' \
     "$JIRA_BASE_URL/rest/api/3/issue/$KEY/worklog"
   ```
6. Estimates: `GET ...?fields=timetracking`; only `PUT {"fields":{"timetracking":{"originalEstimate":"..."}}}` when `originalEstimate` is empty — never override a planning estimate.
7. **Verify**: re-run the audit for the range and confirm every day totals exactly 8h. Fix overages by deleting your just-posted entries (WEST/VOCO) or shrinking them (CESP, min 1m — compensate the residue by trimming another same-day entry).

## Rules

- Audit is read-only; logging always needs plan confirmation first (worklogs are hard to remove — impossible on CESP).
- Reply tables in the conversation language; worklog comments always in English.
- Never print `$JIRA_API_TOKEN` in output.
