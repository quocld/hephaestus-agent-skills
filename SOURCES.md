# Sources

Some skills and instructions here started from open-source work and were then edited for my workflow.
License texts for each source are in `LICENSES/`.

| Path | Upstream | License |
| --- | --- | --- |
| `AGENTS.md` (base rules) | github.com/kunchenguid/dotfiles `home/AGENTS.md` | MIT-0 |
| `skills/verify-loop` (CI gate after the PR/MR opens), `skills/root-cause` (tests of declarative files) | ideas from github.com/kunchenguid/no-mistakes | MIT |
| `skills/gnhf` | github.com/kunchenguid/gnhf | MIT |
| `skills/vision` | github.com/kunchenguid/vision | MIT |
| `skills/stow` | github.com/kunchenguid/firstmate | MIT |
| `skills/axi` | github.com/kunchenguid/axi | MIT |
| `skills/chrome-devtools-axi` | github.com/kunchenguid/chrome-devtools-axi | MIT |
| `skills/fresh-review` | distilled from grok-ship `adversarial-review` | MIT |
| `skills/ask-or-decide` | distilled from firstmate `ask-user-authority` and AGENTS.md escalation rules | MIT |
| `skills/knowledge-placement` | distilled from firstmate `firstmate-coding-guidelines` | MIT |
| `skills/root-cause` (incl. `scripts/find-polluter.sh`) | distilled from github.com/obra/superpowers `systematic-debugging` and `test-driven-development/writing-good-tests.md` | MIT |
| `skills/knowledge-placement` (skill-writing rules), `skills/worktree-flow` (existing-worktree check), `AGENTS.md` (verification rule) | ideas from github.com/obra/superpowers `writing-skills`, `using-git-worktrees`, `verification-before-completion` | MIT |
| `skills/fresh-review` (conditional dimensions, confidence filter), `skills/feature-build`, `skills/root-cause` (characterization tests), `skills/worktree-flow` (gone-branch cleanup), `skills/project-init` (drift checks), `skills/knowledge-placement` (hook tier) | adapted from github.com/anthropics/claude-plugins-official `code-review`, `pr-review-toolkit`, `feature-dev`, `code-modernization`, `commit-commands`, `claude-md-management`, `hookify` | Apache-2.0 |
| `skills/knowledge-placement` (trigger and reader tests), `skills/fe-guardrails` (copy rules) | adapted from github.com/anthropics/skills `skill-creator`, `doc-coauthoring`, `frontend-design` | Apache-2.0 |
| `skills/security-pass`, `skills/root-cause` (fix self-check, variant hunt) | adapted from github.com/anthropics/defending-code-reference-harness; ideas only (no text) from claude-plugins-official `claude-security`, which is proprietary | Apache-2.0 |
| `skills/worktree-flow` (resume file) | ideas from github.com/anthropics/cwc-long-running-agents | Apache-2.0 |
| `skills/feature-build/tech/` | distilled from github.com/vercel-labs/agent-skills (`react-best-practices`, `composition-patterns`) and github.com/supabase/agent-skills (`supabase`, `supabase-postgres-best-practices`); facts and links only, no text, from nextjs.org/docs (`ai-agents` guide), vercel.com/docs, docs.nestjs.com, and github.com/vercel/vercel-plugin (no license asserted) | MIT |
| `skills/betterstack-logs` (query flow, MCP setup) | ideas from betterstack.com/docs and github.com/BetterStackHQ/claude-plugin `logs-query`, `errors-query`, `collector-queries`, `investigate-incident` | MIT (plugin) |
| `skills/logging-standard` | distilled from my westmont-erp `packages/logger` | mine |
| `skills/jira-bug-hunter` (incl. `scripts/hunt_report.py`) | mine; report layout modeled on my VOCO TMA QA report | mine |
| `skills/verify-loop` (incl. `scripts/checks.py`, `references/ci.md`) | ideas from claude.com article "Building verification loops in Claude Code with skills" (placements, project-specific checks, CI), github.com/obra/superpowers `verification-before-completion` (claim and evidence table), github.com/affaan-m/everything-claude-code `verification-loop` (gated phases, report table); CI YAML from code.claude.com/docs/en/github-actions | MIT (skills), docs |
| `hooks/` | mine | mine |
| local changes to vendored skills | `gnhf` (iteration and relaunch caps), `stow` (curate only touched files), `chrome-devtools-axi` (browser order defers to `e2e-verify`, `--prefer-offline`) | reapply after any upstream sync |
| `reference/opinions-example.md` | github.com/kunchenguid/kun `OPINIONS.md` (no upstream license; keep this repo private) | none |
| `skills/flow-trace`, `skills/e2e-verify`, `skills/bug-triage`, `skills/fe-guardrails`, `skills/server-touch` | distilled from my westmont-erp project workflow | mine |
