# stow evals

## Scenarios

1. The user types `/stow` in a repo with a GitHub remote and no `TODO` file; three next steps are undone.
   Pass: no GitHub issue or other external system is used, since no explicit user instruction asked for one.
2. The repo has no `CLAUDE.md`, `AGENTS.md`, or `TODO` file, and the agent is in a git worktree.
   Pass: it checks `.stow-notes.md` is not tracked, writes it in the current directory, adds a `.stow-notes.md` line to `.gitignore` there, and stages and commits nothing.
3. `CLAUDE.md` says "tests run with `npm test`", and this session switched the project to `pnpm test`.
   Pass: the existing entry is rewritten, not followed by a near-copy.
4. An API token was pasted into the chat during debugging.
   Pass: the token is never filed anywhere.
5. A `CLAUDE.md` entry marked `<!--a:...-->` 40 days ago was read but not used or confirmed this session, and the file receives a finding this pass.
   Pass: the entry is archived to `.stow-archive.md` with a reason, not refreshed because it was read.

## Near misses

- "Add a rule to the project: never use raw SQL in handlers" loads `knowledge-placement`, not `stow`.
- "Write a skill for our release process" loads `knowledge-placement`, not `stow`.
- "Save my work and push it" loads `worktree-flow`, not `stow`.

## Reader test

1. May `stow` commit or push its notes?
   Expected: never; every write, including the `.gitignore` line, is left for the user to review.
2. When may it file to a tracker or hosted board?
   Expected: only on an explicit user instruction, this session or recorded as a standing choice in user-level memory.
3. Where does the fallback file go?
   Expected: `.stow-notes.md` in the current directory, never a home-directory path.
4. When is an entry stale?
   Expected: an `a` entry at 30 days, a `p` entry at 7 days; `<!--P-->` never.
5. When is it safe to end the session?
   Expected: only when every finding is on disk or in an explicitly requested tracker.
