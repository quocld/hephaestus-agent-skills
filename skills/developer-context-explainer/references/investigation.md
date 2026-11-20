# Shared investigation for the context explainers

Both `developer-context-explainer` and `business-context-explainer` run this file before writing a word of explanation; the two skills ship together in this plugin, so the file is always present for both.
`<int>` below is the integration branch from `worktree-flow` section 0; read-only runs that cannot settle it use the remote's default branch and say so in Sources.
It owns the read-only rule, the source inventory, the evidence labels, the asking rule, and the writing rules; each skill owns only its role's depth and output.

## 1. Read-only, for the whole run

The skill explains; it never changes anything.

- Allowed: reading files; `git fetch` and every git command that only reads (`log`, `show`, `diff`, `branch`, `status`, `worktree list`, `grep`, `rev-parse`, `merge-base`, `ls-tree`, `blame`); `gh` reads (`pr view|list|diff|checks`, `issue view|list`, `api` with GET); tracker, chat, and design reads (GET, search, view).
- Never: an edit or write tool on project files, `git switch`, `checkout`, `stash`, `commit`, `push`, `reset`, a tracker transition, assignment or comment, a spec or doc edit, a chat message, a migration.
- Running tests, builds, or the app is not part of this skill; say what would prove a point instead of running it.
- Notes you need go in the scratchpad, never in the repo.
- The user asks for a change mid-run ("fix it while you are there", "update the ticket", "write the test cases"): finish the explanation, then say this skill is read-only and name who does the change.
  Code: `feature-build` or `bug-triage`.
  A ticket, spec, or AC edit: its owner, by hand, using the wording you proposed.
  Test cases or a test plan: the project's test-plan skill when one is installed, otherwise the QC from the scenarios you listed.
  Do not start the change inside this run.

## 2. Inventory the sources before reading them

Probe every row; never report a source as unavailable without the probe that shows it.
A tool that only appears as a deferred name (Slack, Figma, a tracker MCP) is probed by loading it with ToolSearch; not finding one is the probe result.

| Source | How to find and reach it |
| --- | --- |
| Project facts | The project-init block in `AGENTS.md` on `origin/<int>`: tracker, sources of truth in priority order, decision log, API contract. Read it first; it names where everything below lives. No block: the tracker follows from the ticket id shape and the remote (`WEST-12` is Jira, `#12` on a GitHub remote is GitHub), and the priority order is the fallback in section 4. |
| Ticket | Jira: an Atlassian or Jira MCP tool, else `JIRA_*` variables and the REST API (GET only). Linear: a Linear MCP tool. GitHub issue: `gh issue view <n> --json title,body,state,labels,comments`. GitHub PR used as the ticket: `gh pr view <n> --json title,body,state,headRefName,mergedAt,comments,reviews,files` and `gh pr diff <n>`. GitLab: `glab issue view <n> --comments`. Read it whole as `bug-triage` section 1 says (read only that section): every comment and attachment, plus status, links, parent, and subtasks. |
| Specs, PRD, decision log | The block's priority order; no block: `git grep -il '<ticket id>\|<key term>' origin/<int> -- '*.md'` and the usual folders (`docs/`, `openspec/`, `specs/`). |
| Glossary, product docs | A glossary or domain file in the same folders, the README, help or onboarding docs. |
| History | Linked and older tickets; `gh pr list --state all --search '<ticket or term>'`; `git log origin/<int> --oneline -i --grep='<ticket or term>'`; `git log -S '<identifier>' origin/<int>` for when a rule appeared; the descriptions and reviews of those PRs. |
| Codebase | `git grep` and `git show origin/<int>:<path>` on the integration branch, never the main checkout; the developer's own branch or worktree only for progress. |
| Discussions | Ticket comments, PR reviews, a Slack search for the ticket id and key terms when Slack is connected. |
| Design | Figma links in the ticket, read through a Figma MCP when it is authenticated. |

- Each row ends as one of: `checked` (found something), `checked, nothing found`, `not connected` (no tool or token in this session), `needs login` (with the command or `/mcp` step the user runs).
- A search that returns nothing for a term you know exists (a PR title you have seen) means the search failed, not that nothing exists: list without the search (`gh pr list --state all --limit 200 --json number,title,headRefName`) and filter.
- A ticket id with no tracker access: say so in the TL;DR, continue with what the repo holds, and make "paste the ticket or connect the tracker" the one closing question from section 5; never reconstruct the ticket from its title or branch name.
- Private messages (DMs, private channels): use the decision they record and cite channel and date; never quote them in a reply meant for someone else.

## 3. Investigate in this order, and stop early

1. The ticket and every comment, then its links, parent, and subtasks.
2. The specs and decisions that govern it, newest signed decision first.
3. History: earlier tickets, PRs, and commits that touched the same rule or screen, and why they did it.
4. The current behavior, read in code only as deep as the calling skill's role needs.

- Search by ticket id first, then by the domain terms the ticket uses, then by the code identifiers those terms map to.
- Read the lines that answer a question, not whole folders.
- Stop when every output section has an answer or an `Unknown`, after the calling skill's own investigation steps have run; those steps are never skipped to stop early.
- No acceptance criteria in the ticket: write "no AC list" as `Unknown`, add it to the questions for whoever owns the ticket, and when you derive criteria from the description, label each one `Inferred`.

## 4. Label every project fact

| Label | Means | Must carry |
| --- | --- | --- |
| Verified | A source states it | The source: ticket comment author and date, `path:line` at the ref you read, commit sha, PR number, doc section |
| Inferred | Follows from sources, not stated by any | What it was inferred from, in a few words |
| Unknown | Not found | What would settle it, and who can answer |

- Every project fact in sections 02-07 carries a label; the overview (01) may carry plain ticket fields.
- General domain knowledge (how invoicing usually works, what an SLA usually means) is never a project fact: label it `Inferred (general knowledge, not confirmed here)` or leave it out.
- Sources disagree: show both with their dates.
  A recorded, signed decision settles a conflict when one covers it; the project's priority order (without a project-init block: newest signed decision, spec, ticket comments, ticket description, current code) only says which source describes the system as built or documented today.
  A business conflict that no recorded decision settles stays open for the PO, never resolved by you, even when the priority order favors one side.
- Every `Inferred (general knowledge, not confirmed here)` and every `Unknown` that changes the requirement becomes a question in the role's questions list, addressed to who can answer.
- Past behavior explained from history ("it works this way because PR #41 chose X after incident Y") is only Verified when that PR or ticket says so.
- Before sending, recheck every Verified history claim against its sha or PR; history is where wrong claims creep in.

## 5. Ask only what the sources could not answer

- Investigate first; never ask the user something the inventory could have found.
- Deliver the explanation with its `Unknown`s; do not hold it back for answers.
- When one gap blocks understanding and the user can likely answer it (they wrote the ticket, they know the client), end with exactly one question: what you understood, what is missing, and the options you see.
  Ask the next one only after that answer.
- Gaps only the PO, client, or another team can close go in the role's questions list, addressed to them, not to the user.

## 6. Write for a reader in their first week

- Answer first: the TL;DR line says what the ticket is, why it exists, and the single most important thing the reader must know; a narrow question ("which file?", "am I done?") is answered there too.
- Length: a 2-3 minute read, about 500-800 words of prose, not counting tables and the Sources line (Vietnamese text counted by `wc -w` runs about 1.3 times higher).
  To fit, write each section in 1-4 lines, say a thing once and point back to it, and leave detail for the follow-up offer.
- Plain language, as a senior colleague onboarding a new teammate; the reply is in the user's language, with domain terms kept as the project spells them.
- Every term, acronym, or entity is explained at its first use, with an example from this project (a real screen, record, or status) rather than a textbook one, and never with another unexplained term.
- Explain relationships, not only definitions: which actor uses the term, where it sits in the workflow, what it changes, and why it matters to this ticket.
- A section the calling skill does not keep always is dropped when it has nothing to say; a kept section with nothing found holds one `Unknown` line saying what would settle it.
- A timeline only when at least two dated, related events were found.
- The reply ends in this order: one "Deeper on request: <topics>" line, the `Sources` line (each inventory row and its result from section 2), then the one question from section 5 when there is one.
