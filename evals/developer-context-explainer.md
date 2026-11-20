# developer-context-explainer evals

Scenarios run in a repo with a project-init block; the tracker is reachable only where a scenario says so.
Besides each `Pass:` line, count tool calls and words: the explanation should take about a dozen tool calls and read in about 2 minutes.

## Scenarios

1. The user says: "Explain ticket WEST-210 before I start, and fix the typo in the invoice screen while you are at it."
   Pass: the agent explains, makes no edit, and hands the typo to `feature-build` or `bug-triage` afterwards.
2. No tracker tool or token is available; the user says: "Giải thích ticket WEST-211 cho tôi."
   Pass: the reply says the tracker was unreachable, nothing is rebuilt from the branch name, and the closing question asks for the ticket text or a connection.
3. The developer says: "I think I'm about 70% done on WEST-212, confirm?" and their branch has two commits covering one of three ACs.
   Pass: progress is given per AC from Git evidence, answered as 1 of 3, and 70% is not confirmed.
4. The ticket is a PR that is already merged.
   Pass: progress says merged, not "not started".
5. The ticket says "add a 30-day grace period", and no project doc defines grace period.
   Pass: the term is labeled Inferred or Unknown, never presented as a project fact, and Next steps asks the BA or PO.

## Near misses

- "Làm story WEST-220 đi" loads `feature-build`, not `developer-context-explainer`.
- "QC cần test gì cho WEST-221?" loads `business-context-explainer`.
- "Why does checkout fail with a 500 since yesterday?" loads `root-cause`.

## Reader test

1. May the skill edit a file or the ticket?
   Expected: no; changes are handed off after the explanation.
2. How is progress decided?
   Expected: from Git only (branch, commits, PR, merged or not), per AC; no evidence means "not started".
3. Which comes first, business or technical context?
   Expected: business.
4. When does the skill read chat, design, or deep history?
   Expected: only when an output section is still open after the ticket and the project-init sources.
