# Deploy targets: default commands and gotchas

Use these only to propose commands for a registry that lacks them.
Once confirmed, the commands live in `.agents/environments.json`; the registry wins over this file.
A remote target needs `version`, `deploy`, `verify`, and `rollback`; `logsCommand` where the platform has a CLI for it.
`version` prints exactly one value: the commit SHA the running process was built from, or for a database the latest applied migration version.

## Any target: deploy from a clean checkout of `<sha>`

CLIs that read the local tree (`supabase db push`, `supabase functions deploy`, `vercel deploy`) ship whatever is on disk, not the tested commit.
Run them from a dedicated checkout: `git worktree add .agents/deploy/<sha> <sha>`, and remove it after the deploy.
Rollbacks that redeploy code run from a checkout of `<previous-sha>`.

## Any target: expose the running commit

The most reliable `version` is an endpoint the app serves itself; the contract and recipes are in `version-endpoint.md`.
If the project has no such endpoint, propose adding one; "pushed" is not "deployed" until the running SHA matches.

## vps (Next.js or any Node app over SSH)

- Access only through a `~/.ssh/config` alias (`Host acme-prod` with `HostName`, `User`, `IdentityFile`); the registry stores the alias, never the IP or key path.
- One remote command per step: `ssh <alias> '<cmd>'`.
  Never open an interactive shell on a confirm-each-step environment.
- Prefer release folders over building in place: `releases/<sha>` plus a `current` symlink.
  Building in place overwrites `.next` while the old process still runs, and a failed build leaves nothing to roll back to.
  Rollback then becomes "repoint the symlink and reload", which takes seconds.
- Process manager: `pm2 reload <name> --update-env` (zero-downtime for cluster mode), `systemctl restart <unit>`, or `docker compose up -d` for the Docker variant.
- Name release folders by the full SHA.
- `version`: ask the running process, `ssh <alias> 'curl -fsS http://localhost:<port>/api/version' | jq -r .sha`.
  Reading the `current` symlink shows what is linked, not what pm2 is running.
- `logsCommand`: `ssh <alias> 'pm2 logs <name> --lines 200 --nostream'` or `journalctl -u <unit> -n 200 --no-pager`.
- `verify`: `curl -fsS -o /dev/null -w '%{http_code}' <url>/api/health` plus the public version endpoint.
- Keep the production env file on the server (`shared/.env.production`) and copy or symlink it into each release; never commit it, never print it.
- Disk fills with old releases; keep the last 3-5 and treat cleanup as its own confirmed step.

## docker-compose (on a VPS)

The `server-touch` skill owns the mechanics: scoping every command with `-p` and all compose files, the commands forbidden on a shared host, verify, and two-level rollback.
Registry fields: `access.composeProject`, `access.composeFiles`, `access.sharedHost`.

- Prefer the project's versioned deploy script as `deploy` when one exists.
- Pin image tags to the commit SHA, not `latest`; otherwise `version` and `rollback` have nothing to point at.

## vercel

- Find how the project deploys before proposing commands.
  Git-integrated projects deploy by pushing to the production branch, so the deploy step is the `git push`, not `vercel deploy`.
  CLI-driven projects use `vercel deploy` (preview) and `vercel deploy --prod`.
- Set `trigger: git` for git-integrated projects: the push or merge into the production branch is the deploy, so it follows the environment's policy (`environments` section 3).
- A Vercel deployment has no commit SHA unless you put one there.
  Git-integrated deployments carry it in their metadata (`githubCommitSha`); CLI deployments get it with `vercel deploy --prod --meta gitSha=<sha>`, and `version` reads it back from the live deployment's metadata (`vercel inspect <url>`, or the REST API's deployment `meta`).
  Prove the exact command once, then record it; the app's own version endpoint stays the better choice when it exists.
- Record `access.vercelTeam`, `access.gitAccount`, and `access.tokenEnv`; `environments` section 2 checks them before every write.
- Always pass `--scope <team>` and run inside the linked folder; before a write, check `.vercel/project.json` `projectId` and `orgId` equal the registry's `vercelProjectId` and `vercelOrgId`.
- Push an exact commit to the deploy branch (`git push origin <sha>:refs/heads/<branch>`), not whatever the local branch holds.
- `rollback`: `vercel rollback [deployment-url]`; `vercel promote <deployment-url>` to promote a known good deployment.
  Both act on production deployments, so a staging environment should be its own Vercel project deploying to its production target, not preview deployments.
- `logsCommand`: `vercel logs <deployment-url>`.
- Env vars: `vercel env ls <environment>` to read; `vercel env add <NAME> <environment>` to write, value on stdin, never as an argument.
  Changing an env var does not affect running deployments; a redeploy is required, which is its own step.

## supabase

- The CLI keeps one linked project per repo (`supabase/.temp/project-ref`).
  Switching links between environments is how staging migrations land on prod.
  Prefer `--db-url "$ENV_DB_URL"` for database commands and `--project-ref <ref>` for functions and secrets, so every command names its target.
  If a command relies on the link, check `cat supabase/.temp/project-ref` equals the registry ref right before running it.
- `version`: `psql "$DB_URL" -tAc "select max(version) from supabase_migrations.schema_migrations"`; after deploy it must equal the newest file in `supabase/migrations/` at `<sha>`.
  `supabase migration list` is useful in the plan but prints a table, not one value.
- `deploy`, in this order:
  1. Backup (prod): `supabase db dump` saves only the schema by default; take two dumps, `supabase db dump --db-url "$DB_URL" -f .agents/backups/<env>-<timestamp>-schema.sql` and `supabase db dump --db-url "$DB_URL" --data-only -f .agents/backups/<env>-<timestamp>-data.sql`, or confirm a point-in-time restore point exists in the dashboard.
     Dumps contain customer data: `.agents/backups/` is gitignored; delete dumps when no longer needed.
  2. `supabase db push --db-url "$DB_URL" --dry-run`, and show the list of migrations it would apply.
  3. `supabase db push --db-url "$DB_URL"`.
  4. `supabase functions deploy <name> --project-ref <ref>`.
  5. Secrets: `supabase secrets set --env-file <file> --project-ref <ref>`; never `NAME=value` on the command line.
- Write the migration file first, then apply it; never change the remote schema from the dashboard or SQL editor, or the repo and the database drift.
- Deploy migrations and functions before the code that needs them, and keep both backward-compatible with the running web code (add a column first, drop it in a later release).
  A function is rolled back by redeploying it from a checkout of `<previous-sha>`.
  Then a failed web deploy leaves a working site.
- `rollback`: migrations are forward-only.
  Roll back with a new migration that reverses the change (`supabase migration new revert_<name>`, write the SQL, push); restoring the backup is a last resort the user decides.
- `logsCommand`: the dashboard (Logs Explorer) via `dashboardUrl`, or `supabase functions logs` where the CLI version supports it.

## local

- `deploy` starts things (`pnpm dev`, `supabase start`); it runs in the background, and `verify` checks the port.
- `supabase db reset` wipes local data: keep it out of `deploy` and run it only when asked.
- Local is still not a place for real customer data: never restore a prod dump locally without the user saying so.

## custom

Anything else (Netlify, Cloudflare, Fly, Railway, Kubernetes, FTP).
Write the commands from the project's own scripts and CI workflow, not from memory, and get them confirmed before the first use.
