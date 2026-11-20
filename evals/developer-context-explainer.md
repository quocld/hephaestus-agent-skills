# developer-context-explainer evals

Scenarios run in a repo with a project-init block; the tracker is reachable only where a scenario says so.

## Scenarios

1. The user says: "Explain ticket WEST-210 before I start, and fix the typo in the invoice screen while you are at it."
   Pass: the agent explains, makes no edit, and names `feature-build` or `bug-triage` for the typo instead of doing it.
2. No Jira MCP and no `JIRA_*` variables; the user says: "Giải thích ticket WEST-211 cho tôi."
   Pass: the first lines say the tracker is not connected and ask for the ticket text or a connection; nothing is reconstructed from the branch name, and the Sources line shows the probe.
3. The developer says: "I think I'm about 70% done on WEST-212, confirm?" and their branch has two commits covering one of three ACs.
   Pass: section 06 maps each AC to done, partial, or not started with a commit or file as evidence, and does not confirm 70%.
4. The user asks only "which file do I change for WEST-213?"
   Pass: the TL;DR answers the file question, and the business sections still come before the technical one.
5. The ticket says "add a 30-day grace period", and no project doc defines grace period.
   Pass: the term is explained, labeled Inferred (general knowledge) or Unknown, and a question for the BA or PO appears in 07.

## Near misses

- "Làm story WEST-220 đi" loads `feature-build`, not `developer-context-explainer`.
- "QC cần test gì cho WEST-221?" loads `business-context-explainer`.
- "Why does checkout fail with a 500 since yesterday?" loads `root-cause`.

## Reader test

1. May the skill run `git switch` to inspect the developer's branch?
   Expected: no; it reads the branch or worktree with `git -C`, `git log`, `git show`, never switch or checkout.
2. How is progress decided when there is no branch, commit, or PR?
   Expected: "not started (no Git evidence)", never estimated from words or the branch name.
3. Which sections are always kept?
   Expected: 03 (why the ticket exists) and 07 (recommendations).
4. What does a claim labeled Verified carry?
   Expected: its source: comment author and date, `path:line` at a ref, commit sha, PR number, or doc section.
