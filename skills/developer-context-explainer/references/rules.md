# Rules for both context explainers

Shared by `developer-context-explainer` and `business-context-explainer`, which ship together; each skill adds only its role's focus and output.

- Read-only: read the tracker, repo, docs, and chat; never edit files, the ticket, or a spec, and never post anything.
  A change the user asks for comes after the explanation, handed to its owner: code to `feature-build` or `bug-triage`, a ticket or AC edit to the person who asked, by hand, full test cases or a test plan to the project's test-plan skill or the QC.
  Running the app, tests, or scripts, and setup skills such as `project-init`, are not part of explaining.
- Read code on the integration branch (`origin/<int>`), never the main checkout.
- Gather only what the answer needs: the whole ticket and the sources the project-init block in `AGENTS.md` names (when it has one) come first; history, code, chat, and design only when an output section is still open.
- A source you could not reach is named as unreachable, never filled in by guessing or rebuilt from a title, branch name, or commits.
  Without the ticket itself, explain only what Git shows and ask for the ticket text.
- Label the facts that matter: Verified (with its source: comment, `path:line`, commit, PR), Inferred (from what), or Unknown (who can answer).
  General domain knowledge is never a project fact.
- A business conflict or missing rule becomes a question for whoever owns the ticket (the PO or client, or its author when there is none); never decide it, and never invent a role or a rule.
  A ticket with no business layer (an internal or technical fix) is said to be one; rules read from code are Inferred, not business rules.
- A ticket already done or merged is said to be done; there is nothing to plan or test beyond what it changed.
- Ask the user at most one question, at the end, and only what no source answered.
- Write answer first, in the user's language, plain words, each term explained at first use with an example from this project, about a 2-minute read.
  Drop a section with nothing to say.
  End with `Sources:` (what you read, what was unreachable) and an offer to go deeper.
