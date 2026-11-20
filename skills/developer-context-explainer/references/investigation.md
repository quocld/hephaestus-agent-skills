# Shared investigation for the context explainers

Both `developer-context-explainer` and `business-context-explainer` run this file before writing a word of explanation.
It owns the read-only rule, the source inventory, the evidence labels, the asking rule, and the writing rules; each skill owns only its role's depth and output.

## 1. Read-only, for the whole run

The skill explains; it never changes anything.

- Allowed: reading files, `git fetch`, `git log`, `git show`, `git diff`, `git branch`, `git status`, `git worktree list`, `git grep`, `gh pr view|list`, `gh issue view|list`, tracker and chat reads (GET, search, view).
- Never: an edit or write tool on project files, `git switch`, `checkout`, `stash`, `commit`, `push`, `reset`, a tracker transition, assignment or comment, a spec or doc edit, a chat message, running the app against shared data, a migration.
- Notes you need go in the scratchpad, never in the repo.
- The user asks for a change mid-run ("fix it while you are there", "update the ticket"): finish or stop the explanation, say this skill is read-only, and name the skill that does the change (`feature-build`, `bug-triage`, or the tracker by hand).
  Do not start the change inside this run.

## 2. Inventory the sources before reading them

Probe every row; never report a source as unavailable without the probe that shows it.

| Source | How to find and reach it |
| --- | --- |
| Project facts | The project-init block in `AGENTS.md` on `origin/<int>` (`worktree-flow` section 0): tracker, sources of truth in priority order, decision log, API contract. Read it first; it names where everything below lives. |
| Ticket | The tracker the block names. Jira: an Atlassian or Jira MCP tool in this session, else `JIRA_*` variables and the REST API (GET only). Linear: a Linear MCP tool. GitHub: `gh issue view <n> --comments`. GitLab: `glab issue view <n> --comments`. Read it whole per `bug-triage` section 1, plus status, links, parent, subtasks. |
| Specs, PRD, decision log | The block's priority order; no block: `git grep -il '<ticket id>\|<key term>' origin/<int> -- '*.md'` and the usual folders (`docs/`, `openspec/`, `specs/`). |
| Glossary, product docs | A glossary or domain file in the same folders, the README, help or onboarding docs. |
| History | Linked and older tickets; `gh pr list --state all --search '<ticket or term>'`; `git log origin/<int> --oneline --grep='<ticket or term>' -i`; `git log -S '<identifier>' origin/<int>` for when a rule appeared; PR descriptions and review comments of those PRs. |
| Codebase | `git grep` and `git show origin/<int>:<path>` on the integration branch, never the main checkout; the developer's own branch or worktree only for progress. |
| Discussions | Ticket comments, PR reviews, a Slack MCP search for the ticket id and key terms when Slack is connected. |
| Design | Figma links in the ticket, read through a Figma MCP when it is authenticated. |

- Each row ends as one of: `checked` (found something), `checked, nothing found`, `not connected` (no tool or token in this session), `needs login` (with the command or `/mcp` step the user runs).
- A ticket id with no tracker access: say so in the first lines, ask the user to paste the ticket or connect the tracker, and continue with what the repo holds; never reconstruct the ticket from its title or branch name.

## 3. Investigate in this order, and stop early

1. The ticket and every comment, then its links, parent, and subtasks.
2. The specs and decisions that govern it, newest signed decision first.
3. History: earlier tickets, PRs, and commits that touched the same rule or screen, and why they did it.
4. The current behavior, read in code only as deep as the calling skill's role needs.

- Search by ticket id first, then by the domain terms the ticket uses, then by the code identifiers those terms map to.
- Read the lines that answer a question, not whole folders.
- Stop when every output section has an answer or an `Unknown`; a section with nothing to say is dropped, not padded.

## 4. Label every important claim

| Label | Means | Must carry |
| --- | --- | --- |
| Verified | A source states it | The source: ticket comment author and date, `path:line` at the ref you read, commit sha, PR number, doc section |
| Inferred | Follows from sources, not stated by any | What it was inferred from, in a few words |
| Unknown | Not found | What would settle it, and who can answer |

- General domain knowledge (how invoicing usually works, what an SLA usually means) is never a project fact: label it `Inferred (general knowledge, not confirmed here)` or leave it out.
- Sources disagree: show both with their dates and the project's priority order; a newer signed decision beats an older spec, and a business conflict that no recorded decision settles stays open for the PO, never resolved by you.
- Past behavior explained from history ("it works this way because PR #41 chose X after incident Y") is only Verified when that PR or ticket says so.

## 5. Ask only what the sources could not answer

- Investigate first; never ask the user something the inventory could have found.
- Deliver the explanation with its `Unknown`s; do not hold it back for answers.
- When one gap blocks understanding and the user can likely answer it (they wrote the ticket, they know the client), end with exactly one question: what you understood, what is missing, and the options you see.
  Ask the next one only after that answer.
- Gaps only the PO, client, or another team can close go in the role's questions list, addressed to them, not to the user.

## 6. Write for a reader in their first week

- Answer first: the first three lines say what the ticket is, why it exists, and the single most important thing the reader must know.
- Default length is a 2-3 minute read (about 400-700 words); detail goes in later sections, and the end offers what you can go deeper on.
- Plain language, as a senior colleague onboarding a new teammate; the reply is in the user's language, with domain terms kept as the project spells them.
- Every term, acronym, or entity is explained at its first use, with an example from this project (a real screen, record, or status) rather than a textbook one, and never with another unexplained term.
- Explain relationships, not only definitions: which actor uses the term, where it sits in the workflow, what it changes, and why it matters to this ticket.
- A timeline only when at least two dated, related events were found.
- End with one `Sources` line: each inventory row and its result from section 2.
