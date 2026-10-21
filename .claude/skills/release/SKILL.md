---
name: release
description: >
  Use in this repo when asked to release a version or redeploy the docs: "release", "release version", "cut a release", "ra bản mới", "release bản mới", "deploy docs", "cập nhật version lên docs".
user-invocable: true
---

# release

Releases are cut by hand from this machine: tag `main`, publish the GitHub release, check the docs cover every skill and hook, build the docs site at that version and deploy it to Vercel with the local CLI.
CI never tags or deploys; `checks.yml` only tests.
The user's "release" is the explicit word for tagging `main` and deploying the `docs` environment this once; still load `environments` (its `docs` entry in `.agents/environments.json` holds the URL, Vercel ids and rollback).

## 1. Pin the commit

```bash
git fetch origin --prune --tags
SHA="$(git rev-parse origin/main)"
MAIN="$(git worktree list --porcelain | sed -n 's/^worktree //p' | head -n 1)"
WT="$(dirname "$MAIN")/$(basename "$MAIN").worktrees/release-${SHA:0:12}"
git worktree add --detach "$WT" "$SHA"
```

Every command below runs in `$WT`, never in the main checkout.

## 2. Pick the version

```bash
python3 .github/scripts/next_version.py
```

`release=false`: HEAD is tagged or nothing changed since the last tag; say so and stop (a docs-only redeploy of the current tag skips to section 4 with `VERSION` set to that tag).
Otherwise `VERSION` is its `version`: `!` or a `BREAKING CHANGE:` footer is major, any `feat` minor, the rest patch.
Show the user `VERSION`, the previous tag and `git log --no-merges --format='%h %s' <previous>..HEAD`, and get one yes for the tag, release and deploy together; a different number they name wins.

## 3. Docs cover everything

```bash
python3 .claude/skills/release/scripts/check_docs.py
bash .github/scripts/test_next_version.sh
bash hooks/test.sh
bash skills/feature-status/scripts/test_status.sh
python3 skills/harness-map/scripts/test_harness_map.py
python3 skills/project-init/scripts/test_doctor.py
python3 .github/scripts/check_skill_refs.py
```

The rest are the `checks.yml` suites, rerun on the exact commit being tagged.
`check_docs.py` checks every skill is in the README skill table, a pillar's `covered_by.skills` and `lifecycle.json` `skills`, and every hook in both hook tables.
Any gap or failure stops the release: fix it in a `worktree-flow` PR into `main`, and come back after the user merges it.
Also read the rendered site in section 4 before deploying: a new skill's page, the wheel popover and the install page must look right, per `AGENTS.md`'s UI bar.

## 4. Tag, build, deploy

```bash
gh release create "$VERSION" --target "$SHA" --title "Hephaestus Skills $VERSION" \
  --notes "Docs: https://hephaestus-skills-docs.vercel.app" --generate-notes
git fetch --tags --force
SITE="$(mktemp -d)/hephaestus-skills-docs"
python3 skills/harness-map/scripts/harness_map.py --docs-only "$SITE" --version "$VERSION" \
  --site-url https://hephaestus-skills-docs.vercel.app
python3 .claude/skills/release/scripts/check_docs.py --site "$SITE" --version "$VERSION" --sha "$SHA"
```

Pass `--gsc-token` (or `GOOGLE_SITE_VERIFICATION`) when the user has the Search Console token, or the verification tag drops from the live site.
Deploy only after the site check prints 0 gaps; the Vercel ids come from the registry, so the CLI never asks to link or creates a new project:

```bash
cd "$SITE" && VERCEL_ORG_ID=team_yweEZEcfhBe9DEWQPiEOmXBX VERCEL_PROJECT_ID=prj_Aqtz9C2gXkFE0058DfeSQL4S88Cr \
  npx --yes vercel@64.5.0 deploy --prod --yes
```

`npx vercel whoami` failing is a blocker to report (the user logs in with `! npx vercel login`); never read a stored token.

## 5. Verify and clean up

```bash
curl -fsS https://hephaestus-skills-docs.vercel.app/version.json   # {"sha": "$SHA", "version": "$VERSION"}
gh release view "$VERSION" --json tagName,targetCommitish,url
```

Retry the curl for about two minutes before calling it failed; then smoke the live site per the registry's `testing.rules` in a real browser.
A bad deploy rolls back with the registry's `rollback` command; a bad tag is reported, never deleted or moved without the user's word.
Remove `$WT` (`git worktree remove "$WT"`) and `$SITE`.

## Report

Version, tag commit, release URL, the docs check result, live `version.json`, smoke result, and anything left for the user.
