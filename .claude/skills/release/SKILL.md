---
name: release
description: >
  Use in this repo when asked to release a version or redeploy the docs: "release", "release version", "cut a release", "ra bản mới", "release bản mới", "deploy docs", "cập nhật version lên docs".
user-invocable: true
---

# release

Releases are cut by hand from this machine: check the commit, check the docs cover every skill and hook, build the docs site at the new version, then tag `main`, publish the GitHub release and deploy the site with the local Vercel CLI.
CI never tags or deploys; `checks.yml` only tests.
The user's "release" is the explicit word for tagging `main` and deploying the `docs` environment this once; still load `environments` (its `docs` entry in `.agents/environments.json` holds the URL, Vercel ids and rollback).
Nothing public happens before section 5, so any failure before it leaves no tag and no deploy behind.

Each Bash call starts a fresh shell: every block below begins by loading the state file, and sections 1 and 2 write it.

## 1. Pin the commit

```bash
git fetch origin --prune --tags
STATE="${TMPDIR:-/tmp}/hephaestus-release.env"
SHA="$(git rev-parse origin/main)"
MAIN="$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)"
WT="$(dirname "$MAIN")/$(basename "$MAIN").worktrees/release-${SHA:0:12}"
SITE="$(mktemp -d)/hephaestus-skills-docs"
git worktree add --detach "$WT" "$SHA"
printf 'SHA=%s\nMAIN=%s\nWT=%s\nSITE=%s\n' "$SHA" "$MAIN" "$WT" "$SITE" > "$STATE"
```

## 2. Pick the version

```bash
. "${TMPDIR:-/tmp}/hephaestus-release.env" && cd "$WT"
python3 .github/scripts/next_version.py
```

`release=false`: HEAD is tagged or nothing changed since the last tag; say so and stop, unless the user wants the current tag's docs redeployed, then set `VERSION` to that tag and `REDEPLOY=1`.
Otherwise `VERSION` is its `version`: `!` or a `BREAKING CHANGE:` footer is major, any `feat` minor, the rest patch; a different number the user names wins.
Record it: `printf 'VERSION=%s\nREDEPLOY=%s\n' "<version>" "<1 or empty>" >> "${TMPDIR:-/tmp}/hephaestus-release.env"`.

## 3. Checks on this exact commit

```bash
. "${TMPDIR:-/tmp}/hephaestus-release.env" && cd "$WT"
python3 .claude/skills/release/scripts/check_docs.py
python3 .github/scripts/check_skill_refs.py
bash .github/scripts/test_next_version.sh
bash hooks/test.sh
bash skills/feature-status/scripts/test_status.sh
python3 skills/harness-map/scripts/test_harness_map.py
python3 skills/project-init/scripts/test_doctor.py
```

`check_docs.py` checks every skill is in the README `## Skills` table, a pillar's `covered_by.skills` and `lifecycle.json` `skills`, and every hook in the README `## Hooks` table and `hooks/README.md`; the rest are the `checks.yml` suites.
Any gap or failure stops the release: fix it in a `worktree-flow` PR into `main`, and start again at section 1 after the user merges it.

## 4. Build and look at the site

```bash
. "${TMPDIR:-/tmp}/hephaestus-release.env" && cd "$WT"
GSC="$(curl -fsS https://hephaestus-skills-docs.vercel.app/ | sed -n 's/.*google-site-verification" content="\([^"]*\)".*/\1/p' | head -n 1)"
python3 skills/harness-map/scripts/harness_map.py --docs-only "$SITE" --version "$VERSION" \
  --site-url https://hephaestus-skills-docs.vercel.app ${GSC:+--gsc-token "$GSC"}
python3 .claude/skills/release/scripts/check_docs.py --site "$SITE" --version "$VERSION" --sha "$SHA"
npx --yes vercel@64.5.0 whoami
```

The live site's Search Console token is carried over, so a release never drops it.
The site check must print 0 gaps (every skill page and sitemap entry, `index.html`, the install page, `version.json`).
Then open `$SITE/index.html` in a real browser: the wheel popover, a new skill's reader page and the install page must look right, per `AGENTS.md`'s UI bar.
`whoami` failing is a blocker to report (the user logs in with `! npx vercel login`); never read a stored token.

## 5. Confirm, tag, deploy

Show the user `VERSION`, the previous tag and `git -C "$WT" log --no-merges --format='%h %s' <previous>..HEAD`, and get one yes for the tag, release and deploy together (a redeploy: one yes for the deploy).

```bash
. "${TMPDIR:-/tmp}/hephaestus-release.env" && cd "$WT"
[ -n "$REDEPLOY" ] || gh release create "$VERSION" --target "$SHA" --title "Hephaestus Skills $VERSION" \
  --notes "Docs: https://hephaestus-skills-docs.vercel.app" --generate-notes
cd "$SITE" && VERCEL_ORG_ID=team_yweEZEcfhBe9DEWQPiEOmXBX VERCEL_PROJECT_ID=prj_Aqtz9C2gXkFE0058DfeSQL4S88Cr \
  npx --yes vercel@64.5.0 deploy --prod --yes
```

The Vercel ids come from the registry, so the CLI never asks to link or creates a new project.
A failed release create stops before the deploy; a failed deploy after the tag is retried, and the tag stays (a tag is never deleted or moved without the user's word).

## 6. Verify and clean up

```bash
. "${TMPDIR:-/tmp}/hephaestus-release.env"
curl -fsS https://hephaestus-skills-docs.vercel.app/version.json   # {"sha": "$SHA", "version": "$VERSION"}
gh release view "$VERSION" -R quocld/hephaestus-agent-skills --json tagName,url
```

Retry the curl for about two minutes before calling it failed; then smoke the live site per the registry's `testing.rules` in a real browser.
A bad deploy rolls back with the registry's `rollback` command.
Clean up from the main checkout: `git -C "$MAIN" worktree remove "$WT"`, `rm -rf "$(dirname "$SITE")" "${TMPDIR:-/tmp}/hephaestus-release.env"`.

## Report

Version, tag commit, release URL, the docs check result, live `version.json`, smoke result, and anything left for the user.
