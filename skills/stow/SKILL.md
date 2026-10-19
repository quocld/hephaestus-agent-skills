---
name: stow
description: >
  Use when the user invokes /stow, asks to save or write down what was learned this session, or before a context reset or long break.
user-invocable: true
---

# stow

File the durable knowledge that exists only in this chat, so the next session starts from a compact, current map rather than a growing journal.
Every file this skill touches must come out more accurate, not merely longer.

## Steps

1. **Sweep once.** Read back over the session one time and collect:
   - User preferences stated in passing (working style, tooling, formatting, approvals).
   - Project facts (build, test, deploy, architecture, conventions).
   - Operational gotchas (sharp edges, workarounds, non-obvious causes).
   - Standing decisions (an approach settled on, an option ruled out, a convention agreed).
   - Undone next steps, with what each one waits on when it is blocked.
   If a finding already lives authoritatively elsewhere (README, config, docs, code), file a one-line pointer to that owner, not a copy.
2. **Discover local conventions.** Look for a project memory file (`CLAUDE.md`, `AGENTS.md` or equivalent), a readable user-level memory file, and a tracked `TODO`, `BACKLOG` or `NOTES` file.
   Do not scan for or infer an issue tracker.
3. **Route local-first, in this order.**
   1. An explicit user instruction, given this session or recorded as a standing choice in user-level memory, wins; it is the only path to an external system such as a tracker or hosted board, and a git remote or `.github` folder is never grounds on its own.
   2. Otherwise the existing local convention: project memory for facts, gotchas and decisions; the `TODO`/`BACKLOG`/`NOTES` file for next steps; user-level memory for preferences when one is reachable.
   3. Otherwise the fallback `.stow-notes.md` in the current directory, never a home-directory path.
      In a git worktree, first check it is not tracked; if it is, write nothing there and report the fallback as blocked.
      Then add a `.stow-notes.md` line to a plain `.gitignore` in the current directory (not git's internal exclude file); if that write fails, still write the notes and tell the user to ignore the file manually.
4. **Ask once and remember.** When two existing local conventions both fit, ask once which one to use.
   When the user names a non-local system as a standing choice, offer once to remember it.
   Record either choice only with the user's explicit permission, in user-level memory (an existing file or one the user agrees to); never set a convention silently.
5. **Write only to real destinations.** Use only an existing convention, the fallback, or a destination the user just approved; never invent new shared files, folders or tracker categories.
   Never create or edit a skill as a destination.
   If nothing is writable, say so and leave the finding unfiled.
6. **Inspect, then update.** Read each destination once, in full (for a `TODO` entry, the whole item), before writing to it.
   Classify each finding as new, duplicate, superseding or obsolete, and rewrite the existing entry rather than append a near-copy.
   Never overwrite a file wholesale; a superseded entry worth keeping is archived, not dropped in the rewrite.
   Never add markers to a `TODO`/`BACKLOG`/`NOTES` file.
7. **Curate only touched files.** Apply the decay rules below to files that received a finding this pass, plus `.stow-notes.md` when it exists.
   Curate every memory file only when the user asks for a full sweep (for example `/stow --sweep`).
   In a curated file, also archive what is no longer current (completed chronology, stale paths or versions, transient task state, resolved alternatives) and merge duplicates.
   Never remove a unique current fact: archive it, or fold it into a stronger owner that keeps it.
   A `.stow-notes.md` entry leaves only by promotion to a tracked file the user approves, folding into user-level memory, archiving, or deletion as a duplicate of a stronger owner.
   You may propose, never perform, moving a situational entry from an always-loaded file or `.stow-notes.md` to an on-demand home; the user creates that home, and the entry leaves only once it exists.
8. **Report briefly** (at most about 15 lines).
   - One action per file touched or considered: `unchanged`, `added`, `rewritten`, `archived` or `routed`.
   - Anything not captured, and why, plus any proposed move still awaiting approval.
   - If `.stow-notes.md` was used: it is private to this project, and how the `.gitignore` line actually went; a preference filed there applies to this project only.
   - A safe-to-end verdict: safe only when every finding is on disk or in an explicitly requested tracker; a blocked fallback or archive means not safe.
   - A copy-pasteable resume pointer listing only files written, for example `To resume, load: CLAUDE.md (project conventions), .stow-notes.md (private notes)`.

## Decay

Entries in a project memory file or `.stow-notes.md` carry one trailing marker:
- `<!--a:YYYY-MM-DD-->` - the default; the date is when the fact was last confirmed.
- `<!--p:YYYY-MM-DD-->` - perishable; the text must name a checkable expiry (a ticket, version or date), otherwise it is an `a` entry.
- `<!--P-->` - pinned; never decays.
User-level memory is pinned by default and needs no markers.
At 30 days an `a` entry is stale, and at 7 days a `p` entry is stale.
A stale entry is re-validated (date refreshed) or archived in that pass; refresh only on real evidence from this session (used, confirmed or re-derived), never because it was read.
Unmarked entries are never age-decayed: only entries that carry a marker, which are the entries this skill wrote, decay; consolidation (duplicate, superseded, no longer current) still applies.
A legacy `<!-- memory tiers: ... -->` header that names `pinned` as the file's default is honored: entries written there stay unmarked.
Legacy markers read as plain `a` entries: a `/N` suffix is ignored, `<!--g-->` (no date) is due for re-validation now, and both are normalized when the entry is next rewritten.
Archive to `.stow-archive.md` in the source file's directory with the source filename, date and a one-line reason; recovery is search and copy back.
In a git worktree, check the archive is not tracked before writing (if it is, report archival as blocked), and add a `.stow-archive.md` line to the `.gitignore` there.

## Never

- Stage, commit or push anything, including the `.gitignore` lines; every write is left for the user to review.
- File credentials, secrets or other sensitive material.
- File to an external system on inference.
