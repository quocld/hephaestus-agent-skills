# verify-loop in CI

Two jobs, added separately; the first costs only runner minutes, the second also costs model tokens or subscription usage.

## 1. Project script checks on every PR

Runs every `script` check, not only the matched ones, since each must be safe on any tree.
No model involved.

```yaml
name: Project checks
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
jobs:
  checks:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v6
      # Install the project's dependencies here when a check needs them.
      - name: Run script checks
        shell: bash
        run: |
          fail=0
          for f in .agents/checks/*.md; do
            [ -e "$f" ] || continue
            grep -Eq '^kind:[[:space:]]*script[[:space:]]*$' "$f" || continue
            cmd="$(sed -nE 's/^run:[[:space:]]*//p' "$f" | head -n 1)"
            echo "== $(basename "$f" .md): $cmd"
            bash -c "$cmd" || { echo "FAIL $(basename "$f" .md)"; fail=1; }
          done
          exit "$fail"
```

Review checks need a model; they run in the job below or locally in `fresh-review`.

## 2. Claude review on every PR

Uses `anthropics/claude-code-action@v1` with the official `code-review` plugin, which posts inline comments.
Setup per the Claude Code docs (code.claude.com/docs/en/github-actions): install the Claude GitHub App, and add `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN` with `claude_code_oauth_token:`) as a repository secret; both need repo admin, so they are the user's steps.

```yaml
name: Claude review
on:
  pull_request:
    types: [opened, synchronize, ready_for_review, reopened]
concurrency:
  group: claude-review-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs:
  review:
    if: github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    timeout-minutes: 20
    permissions:
      contents: read
      pull-requests: read
      issues: read
      id-token: write
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 1
      - uses: anthropics/claude-code-action@v1
        with:
          anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
          plugin_marketplaces: "https://github.com/anthropics/claude-code.git"
          plugins: "code-review@claude-code-plugins"
          prompt: "/code-review:code-review --comment ${{ github.repository }}/pull/${{ github.event.pull_request.number }}"
          claude_args: '--max-turns 30 --allowedTools "mcp__github_inline_comment__create_inline_comment"'
```

- It skips drafts, so agents' draft PRs/MRs are not reviewed until marked ready.
- Fork PRs get no secrets, so the `if:` runs the job only for branches in the same repo.
- It reviews correctness only; the project's review checks are not in its prompt, so `fresh-review` stays the gate that applies them.
- GitLab: see code.claude.com/docs/en/gitlab-ci-cd; only job 1 carries over unchanged (as a `script:` in `.gitlab-ci.yml`).
