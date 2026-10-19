---
name: jira-bug-hunter
description: >
  Use when asked to work through all the bugs assigned to me in Jira, one bug per agent, until each is fixed, merged, verified on dev, and demoed in the report: "hunt bugs", "bug hunter", "săn bug", "quét bug đang assign", "fix hết bug Jira của tôi", "làm lần lượt các bug được giao". Not for one named ticket (`bug-triage`), and not for implementing stories.
user-invocable: true
---

# jira-bug-hunter

A loop over assigned bugs fails where one bug does not: two agents on the same ticket, a browser shared by all of them, merges piling up on dev before anyone tested them, and results nobody can find a week later.
This skill runs the loop; `bug-triage` owns what happens to each bug, and this skill only adds the merge, the dev verification, and the demo report.
Starting it is the user's explicit word to merge each bug's PR/MR into the integration branch once section 4 allows it, and nothing more: never staging or prod.

## 0. Setup, once per run

- Read the project-init block of the project's `AGENTS.md` for the Jira project key, the integration branch `<int>` (`worktree-flow` section 0), and the dev environment in `.agents/environments.json`; no block means run `project-init` first.
- Load `environments` before anything touches dev, and follow dev's policy and testing scope there.
- Jira access is the Atlassian MCP or the REST API; neither is a blocker to report, not a reason to guess tickets.
- The report is one HTML file shared by every project, at the path `python3 <this skill>/scripts/hunt_report.py path` prints.
  Never create another report file, and never edit that one by hand.
- Media inbox: `<report dir>/inbox/<TICKET>/`, where recordings wait until section 6 copies them into the report.
- The run ledger lives in the main checkout's private git dir, never committed:
  ```bash
  L="$(git rev-parse --path-format=absolute --git-common-dir)/bug-hunt.md"
  ```
  One section per ticket, replaced rather than appended:
  ```markdown
  ## VOCOTMA-30
  state: review https://github.com/org/repo/pull/41
  worker: <agent name or "none">
  worktree: <path>
  prs: <every PR/MR url for this ticket, oldest first>
  result: <report dir>/inbox/VOCOTMA-30/worker.json
  dev-fails: 0
  fresh-review round 1: base <sha> head <sha>
  ```
  `state` is one of `queued`, `claimed`, `review`, `awaiting-merge`, `merged <sha>`, `verified`, `reported`, `parked <verdict>`, `skipped <reason>`.
  `fresh-review` round lines for a ticket live here, not in the worker's progress file, and restart at round 1 with each new PR/MR.
  Read it first on resume and after a context summary; trust it, Jira, and `gh pr list` over memory.
- A ticket whose worker is gone (it finished, or this is a new session) gets a new worker when it needs one, whose prompt also names the ledger section and the earlier PRs/MRs to read first.
- Resume: an `awaiting-merge` ticket whose PR/MR is now merged continues at section 5; a `parked needs-decision` ticket continues where it parked once the user answers, in chat or in a ticket comment newer than the park.

## 1. Scan

```text
project = <KEY> AND assignee = currentUser() AND issuetype in (<every issue type of the project whose name contains "Bug">) AND statusCategory != Done ORDER BY priority DESC, updated ASC
```

- A ticket that already has a ledger section continues from its `state` and is never re-judged by the skip rules below; a `reported` ticket comes back only when Jira shows activity newer than its report (reopened, a new comment).
- Skip the others, with the reason in the ledger: a status owned by someone else in the project's workflow (in QA testing, waiting for customer, blocked); a ticket with an open PR/MR, or a branch with no PR/MR, from outside this run (`worktree-flow` section 1 step 1; a branch whose PR/MR is merged or closed is history, typical for a reopened ticket, and does not count); a ticket whose changelog shows it moved into the project's QA status twice already (`bug-triage` step 7 says ask the user first).
- Order: priority, then reopened before new (the reporter is waiting a second time), then oldest update.
- Show the queue to the user as one short table and start; do not wait for approval, the user steers while it runs.

## 2. One bug per worker, at most 3 workers at a time

- Claim a ticket only when a worker slot is free: re-read its assignee and status (someone may have moved it), write `claimed` in the ledger, and move it to the project's in-progress status if it sits in a to-do status.
- Spawn one fresh subagent per ticket, at most 3 holding a ticket at once.
  A worker holds its slot until its ticket is `reported`, `parked`, or `awaiting-merge`, because review findings and dev failures go back to it with SendMessage.
  Never two workers on one ticket, never one worker on two.
- Worker prompt, part by part:
  1. The ticket key and URL, the repo path, `<int>`, the dev environment name, and the media inbox path.
  2. Follow `bug-triage` steps 0 to 5 for this ticket only, in your own worktree per `worktree-flow`, and open the PR/MR as a draft.
     Branches of this ticket whose PR/MR is merged or closed are history, not another agent: add a `-2`, `-3` suffix to yours instead of stopping.
     Run `verify-loop` with gates 5 and 6 marked `DEFER orchestrator`: the orchestrator runs them, since a subagent cannot spawn the reviewer and the browser is shared.
  3. Never use the Playwright MCP browser: it is one shared instance, and a second caller fails with "Browser is already in use".
     Reproduce in a browser process of your own, a Playwright script that launches its own browser with `recordVideo` on (from the project's `@playwright/test` or `npx -y playwright`), and save the video or screenshots to the inbox as `before`.
  4. Never merge, never comment on or transition the ticket, never deploy, and never edit the ledger.
     Test data you create follows `environments`, and you list it in `dataChanges`.
  5. Return only this JSON: `{"ticket", "outcome": "fix|correct-per-decision|cannot-reproduce|needs-decision|blocked", "tier": "light|heavy", "branch", "worktree", "pr", "cause", "proof": "<test command> failed without the fix, passed with it", "reporterSequence": ["step", "..."], "devChecks": ["observable check with its expected value", "..."], "beforeMedia": [{"src", "caption"}], "dataChanges": [], "questions": []}`.
- Save every worker's returned JSON as its ledger `result` file, since sections 5 and 6 need it after a context summary or in the next session.
- Any outcome other than `fix`: check the worker's claim first (replay the reporter's sequence yourself for `cannot-reproduce`, read the cited decision for `correct-per-decision`), then post the ticket action `bug-triage` step 2 names for it (the evidence comment, the decision citation, or the escalation), move the ticket back to the status it had before the claim unless that action set another one, write `parked <verdict>` in the ledger, and go to section 6 with that verdict.
  A claim your check refutes goes back to the worker with your evidence.

## 3. Review before merge, since no human reads the diff

- Rerun the worker's proof yourself in its worktree, with the revert-only-the-fix commands of `root-cause` section 5; a worker's "done" is a claim.
- Run `verify-loop` gate 5 on the branch from your own context: `fresh-review` (it spawns the reviewer), plus `security-pass` and `flow-trace` when their triggers are in the diff.
  Send `auto-fix` findings back to the same worker (SendMessage) and run the next round as `fresh-review` says.
  Every `fresh-review` exit that needs the user (an `ask-user` finding, `risk_level` high in the last round, `auto-fix` findings still open after round 3) parks the ticket as `needs-decision` with that question, and the loop moves on; a parked PR/MR is never merged.
- Mark the PR/MR ready only when gate 5 is clean and the project's CI checks pass (`gh pr checks <n> --watch`, or `glab ci status`); then replace the review DEFER rows of the worker's `verify-loop` table in the PR/MR body with your results and the head you reviewed.
  The behavior row and the requirement rows that cite E2E stay `DEFER orchestrator, dev verification after merge`, and section 5 fills them in the merged PR/MR's body with the evidence file and the running SHA.

## 4. Merge, one ticket at a time

- Merge, deploy, and verify one ticket at a time, so a failure on dev points at one PR/MR; workers keep fixing other tickets meanwhile.
- Before merging: the PR/MR base is `<int>` (`gh pr view <n> --json baseRefName`), and the branch is rebased on the latest `origin/<int>` by its worker, with the touched tests rerun.
  A rebase that moved the head gets the next `fresh-review` round (its after-a-rebase range) and green CI again before the merge.
- Merge with the method the repo's recent merged PRs/MRs used.
- The `guard-protected-branches` hook asks the user before every merge, and that prompt is their confirmation.
  In a permission mode where it denies instead, write `awaiting-merge <url>` in the ledger, keep the merge command for the final report, and move on to the next ticket; never work around the hook.

## 5. Deploy and verify on dev

- Deploy: wait for CI when it deploys `<int>` on merge, otherwise run dev's deploy command per `environments`.
- Confirm the running build contains the merge: dev's version command (`environments` section 6) prints a SHA, and `git merge-base --is-ancestor <merge sha> <running sha>` succeeds; with no version command, grep a marker string from the change in the served bundle (`bug-triage` step 6).
- You alone drive the Playwright MCP browser, one ticket at a time: replay `reporterSequence` with a real persona per `e2e-verify` (checks a to e), measure every `devChecks` item, and record it as `after` with `browser_start_video` and `browser_stop_video`, at 1440x900 and, for anything visual, again at 390x844.
  The branch is already merged, so the `e2e-verify` evidence file goes to `<report dir>/evidence/<TICKET>-<ISO>.json` instead of the repo.
  When another session holds the MCP browser, use the next tool in the `e2e-verify` order, and record video with a Playwright script of your own as workers do.
- FAIL: raise `dev-fails` in the ledger, leave the ticket in its status, and send the evidence to its worker for a follow-up fix on a new branch and PR/MR (the first one is merged), then repeat sections 3 to 5.
  From the second FAIL the worker works per `root-cause`; at the third the verdict is `not-fixed`, and the report and the decision list say what is merged on dev and still broken.
- PASS: hand back per `bug-triage` step 7 (comment, transition, assign to the reporter).

## 6. Add the result to the report

Every ticket that leaves the queue gets an entry on the day it left, whatever its verdict.

1. Write the entry JSON in the scratchpad; `python3 <this skill>/scripts/hunt_report.py --help` owns its fields and rules.
2. Run `python3 <this skill>/scripts/hunt_report.py add <entry.json>`, fix what it rejects, and never bypass it.
3. Final verdicts only (every verdict except `awaiting-merge` and `pending-deploy`): delete the ticket's inbox folder, write `reported` in the ledger, and clean up the worktree per `worktree-flow` section 6, which keeps worktrees whose PR/MR is still open (a parked ticket's draft); list those in the final report.
4. A ticket still `awaiting-merge` or not yet verified when the run stops gets an entry with that verdict and keeps its ledger state and inbox, so the next run continues it and adds a `verified` entry on the day it passes.

Write for the client who reads the page, in the language the project's report readers use (English when unknown):

- `before`: what the reporter saw, in their words, with the date they reported it.
- `asked`: what the ticket asked for, including what the comments added.
- `now`: what the product does now on dev, or why the ticket ended with another verdict.
- `checks`: observed facts with measured values ("200x200 on desktop, 104x104 before"), never "works".
- `steps`: what a reader does to see it themselves; personas by email and role, never a password.
- No file names, function names, or internal jargon outside `pr` and `commit`; those belong in the PR/MR.

## 7. Stop

- The queue is empty: scan Jira once more for bugs assigned during the run, add them, and stop when that queue is empty too.
- The user says stop, or three tickets in a row end `blocked` (the cause is probably shared: dev down, a credential, the test data): claim nothing new, let running workers finish their current step, push, and turn their PRs/MRs into drafts that list what remains, then report.

## Report to the user

1. One table: ticket, verdict, PR/MR, Jira status now.
2. The merges waiting on the user, each as a ready `! gh pr merge <n> ...` line.
3. The decisions the user must make, per `ask-or-decide` section 4.
4. The report as a `file://` link to the path from section 0.
