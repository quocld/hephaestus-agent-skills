---
name: environments
description: >
  Use before any action against a non-local environment (deploy, SSH, migration, remote logs or data, test accounts, test data), when asked what version runs where, and when the user says "deploy lên staging", "ssh vào server", "chạy trên prod", "account test", "môi trường nào", "thêm môi trường", "thêm server".
user-invocable: true
---

# environments

The registry is the only source of environment facts.
An agent that takes a host, branch, command, or password from memory or chat history will one day run a staging command on prod.

## 1. Load and maintain the registry

- Read `.agents/environments.json` at the repo root, in full, before the first environment action of the session.
- Missing, and the task needs a non-local environment: run section 10 first.
  Do not improvise hosts or commands in the meantime.
- When the user states a new fact (server, account, URL, rule), put it in the registry instead of keeping it in chat.
- Every registry change is shown as a diff and written only after a yes; it applies from the next action.
  Changes that weaken safety (`policy`, `allowedWithoutAsking`, `data.testDataAllowed`, `rules`, `defaultEnvironment`, `integrationBranch`, or any command of a `confirm-each-step` environment) need the user to ask for that change explicitly.
- A string `logs` (and `logs` in `allowedWithoutAsking`) is the old name of `logsCommand`: propose the rename as a registry change; it is a rename, not a new command or a weakened safeguard.
- `version`, `verify`, and `logsCommand` commands must be read-only; refuse to register one that writes.
  A request to skip a safeguard for one task ("just run it all", "create a test user on prod") is not a request to change the registry: keep the safeguard, and offer the registry change.

## 2. Name the target environment

- Use the environment the user named, otherwise `defaultEnvironment`.
- Never reach a `confirm-each-step` environment by default or inference.
  If a request could mean prod ("live", "the real site", "customers see this"), ask which environment.
- Prefix every announced command and every result with the environment: `[staging] supabase db push ...`.
- Right before any write, check that the target belongs to that environment in the registry, without printing secrets:
  - SSH: the alias in the command equals `access.ssh`.
  - Vercel: `.vercel/project.json` `projectId` and `orgId` equal `access.vercelProjectId` and `access.vercelOrgId`.
  - Supabase: `[[ "$PROD_DB_URL" == *<supabaseProjectRef>* ]] && echo match || echo MISMATCH`, and the `--project-ref` in the command equals the registry.
  - Any mismatch: stop and report.

## 3. Policies

| `policy` | Reads | Writes (deploy, migration, restart, env vars, data) |
| --- | --- | --- |
| `autonomous` | Free | Free; report afterwards |
| `confirm-writes` | Free | Show the whole plan, get one confirmation, run it; stop and ask on any unexpected result |
| `confirm-each-step` | Ask first, except registry commands listed in `allowedWithoutAsking` (empty by default) | Section 4, every step |

- `allowedWithoutAsking` lists registry commands by name (`version`, `logsCommand`, `verify`), plus `logsQuery` for bounded Better Stack reads per `betterstack-logs` section 4; any other remote command, including ad-hoc SQL, asks first.
  Local reads (git, files in the repo, `op whoami`) are always free.
- `rules` add to the policy.
  When a rule is stricter, follow it; when it is looser than the policy, follow the policy and point out the conflict.
  When a rule depends on something you cannot observe (a customer event, telling the team), ask the user before acting.
- `data.testDataAllowed: false` is a kill switch: never create, modify, or delete records in that environment, except through reviewed migrations shipped by the deploy protocol.
  Where test data is allowed, put `testDataMarker` on every record you create and delete those records when done.
- Approval never carries over: not from an earlier session, an earlier deploy, or another environment.
- Before showing remote logs or query results in chat, mask secrets, tokens, and personal data such as emails and phone numbers.
- A service's `logs` object names its Better Stack source; reading an environment's logs follows `betterstack-logs` section 4, under this environment's policy.

## 4. `confirm-each-step` protocol (prod)

Placeholders in registry commands:

- `<sha>`: the full 40-character SHA being deployed.
- `<previous-sha>`: the code version captured in pre-flight from `version`; rollback depends on it.
  For a database, `version` returns the latest applied migration instead; capture it too.
- `<timestamp>`: UTC `YYYYMMDD-HHMM`.
- Anything else (`<migration-name>`, ...): filled in the plan where the user can see it.

Before the first step:

1. Pre-flight, read-only: capture every service's `version`, resolve `<sha>`, list pending migrations, check every rule (deploy windows, events), and create the clean deploy checkout (`git worktree add .agents/deploy/<sha> <sha>`); commands that read the local tree run from there.
2. Database or data changes in the deploy: complete the section 8 checklist first.
3. Prove what was tested is what ships: the tree at `<sha>` must equal the tree that passed on staging (`git diff --stat <staging-sha> <sha>` is empty).
   Proof that staging passed is an E2E evidence file or the user's explicit word.
4. Present a numbered plan: services in `deployOrder` (default db before web), then each service's `deploy` items in order, one item per step.
   For every step, show the exact command (secrets masked), what it changes, its check, and its undo.
   Where the registry has no per-step check or undo, propose one and mark it "proposed"; the plan approval covers it.
   A step may be skipped only when the plan says why (e.g. no function changed).
5. Get approval of the plan.
   Approving the plan does not approve any step.

For each step:

- Show the exact command and ask "Run step N?"; run nothing until the answer is yes.
- Run only that step, show the relevant output, then run its check.
- Non-zero exit, unexpected output, or a failed check: stop.
  Do not run the next step and do not invent a fix.
  Report what state each service is in now (e.g. migrations applied but web still on `<previous-sha>`), present the options (retry, undo, roll back, investigate), and wait.
- Never merge steps to save confirmations: no `&&` across steps, no ad-hoc scripts, no interactive SSH session.

After the last step: run every `verify`; code services' `version` must print `<sha>`, and the database's must equal the newest migration at `<sha>`. Report what ran, the running versions, the check results, and the rollback commands with placeholders filled in.

## 5. Deploy and access servers

- Use the registry's commands exactly as written, substituting only placeholders.
- A remote service needs `version`, `deploy`, `verify`, and `rollback`; `logsCommand` where the platform has a CLI for it.
  One is missing: propose it from `references/deploy-targets.md`, get it confirmed, write it into the registry, then use it.
- SSH only through the alias in `access.ssh` (defined in `~/.ssh/config`), one remote command per call: `ssh <alias> '<cmd>'`.
- Docker Compose on a server (shared hosts above all): follow the `server-touch` skill.
- "Pushed" is not "deployed": a deploy is done when `version` matches the target and `verify` passes.
- Read the section of `references/deploy-targets.md` for each service type you touch; it holds the platform traps (Supabase link state, Vercel git vs. CLI deploys, VPS release folders).

## 6. Version status across environments

When asked what runs where ("môi trường nào đang chạy bản nào", "prod đang ở commit nào"), or before planning a promotion:

1. `git fetch origin --prune`, then run every service's `version`, environment by environment.
   On a `confirm-each-step` environment this asks first unless `version` is in `allowedWithoutAsking`.
2. Report one table: environment, service, short SHA, commit subject and date (`git log -1 --format='%h %s (%cr)' <sha>`), and how far behind the integration branch it is (`git rev-list --count <sha>..origin/<int>`).
3. For each promotion path, list what would ship: `git log --oneline <prod-sha>..<staging-sha>`.
4. Flag problems instead of smoothing them over:
   - `unknown` or an error: the service has no working version endpoint (`references/version-endpoint.md`).
   - A SHA that no remote branch contains (`git branch -r --contains <sha>` is empty): someone deployed unpushed code.
   - Services of one environment on different SHAs, when they deploy together.

## 7. Testing per environment

`testing.scope` says what tests may run there:

| `scope` | Allowed |
| --- | --- |
| `full` | Any test, including destructive ones, data resets, and load tests |
| `non-destructive` | Functional and E2E tests on records you create (with `testDataMarker`) and delete afterwards; no data resets, load or stress tests, bulk imports, or changes to other people's records |
| `smoke-only` | Read-only flows with the listed accounts: open pages, search, view; no submit that creates or changes data, no payment, no message to a real person |
| `none` | No tests |

- Missing `testing`: `smoke-only` on a `confirm-each-step` environment, `non-destructive` elsewhere.
  When `testing.scope` and `data.testDataAllowed` disagree, follow the stricter one.
- `testing.rules` add project specifics (sandbox keys, QA hours, which flows make up the smoke test).
- On `smoke-only`, list the flows you will run and get a yes before opening the browser; a failure is reported, never fixed or retried by changing data on that environment.
- External side effects cause most testing harm: trigger payments only with test-mode keys, emails or SMS only to addresses the team owns, webhooks only to sandboxes.
  If you cannot confirm that, do not trigger the flow; ask.
- Changing shared settings (feature flags, admin config) counts as a data change: record the old value first and restore it when done.
- Evidence follows the `e2e-verify` skill.

## 8. Database and data changes

Applies to every migration, backfill, data fix, import, bulk admin action, or manual SQL against a `confirm-writes` or `confirm-each-step` environment.

Classify every statement first:

| Class | Examples | Extra gate |
| --- | --- | --- |
| Additive | `CREATE TABLE`, nullable `ADD COLUMN`, `CREATE INDEX CONCURRENTLY` | The checklist |
| Data-changing | `UPDATE`, `DELETE`, backfill `INSERT`, data fix scripts | Row counts and a copy of the affected rows |
| Destructive or locking | `DROP`, `RENAME`, `ALTER ... TYPE`, `SET NOT NULL`, new FK or unique constraint on a large table, `TRUNCATE` | An expand/contract plan and a separate yes per statement |

Before the deploy plan, present this checklist filled in with evidence.
On `confirm-each-step`, any line answered "no" or "unknown" stops the deploy until the user resolves it; on `confirm-writes`, it is raised in the plan.

1. **Backup**: method (point-in-time recovery or schema + data dumps), when it was taken, and proof it is usable (PITR restore point after the last change, or both dump files present and non-empty).
   A fresh backup is the first step of the deploy, not a claim about last night.
2. **Migration approach**: backward-compatible with the code running now and the code being deployed (expand now, contract in a later release), and the deploy order between database and code.
3. **Tested on staging**: the same migration files ran and passed there (`git diff --stat <staging-sha> <sha> -- supabase/migrations` is empty), ideally on a realistic data volume.
4. **Dry run**: the list of migrations about to apply equals the expected list; no surprise migration.
5. **Data changes**: per data-changing statement, its WHERE clause, the expected row count, and where the affected rows are copied first (backup table or export).
   Measure counts without changing anything: `BEGIN; <statement>; <count check>; ROLLBACK;` or `SELECT count(*)` with the same WHERE, each asked first on prod.
   Never an `UPDATE` or `DELETE` without a WHERE.
6. **Locks and duration**: tables touched, their row counts, and which statements rewrite or lock them; large tables need batching, `CONCURRENTLY`, or a maintenance window.
7. **Rollback**: the reverse migration is written and reviewed before deploying.
   If the change cannot be reversed and restoring the backup is the only way back, the user must accept that explicitly.
8. **Side effects**: triggers, RLS policies, cron jobs, realtime subscriptions, and functions or webhooks that fire on changed rows (an `UPDATE` that sends customer emails).
9. **Timing and people**: inside the allowed window, and who has been told (ask the user).

Manual data fixes belong in a reviewed migration or script in the repo, not typed into a SQL console.
Run a fix in two calls: first with `ROLLBACK` to show the affected count, then, after the user confirms the count, the same statements with `COMMIT`.

## 9. Secrets and test accounts

- The registry is committed and holds no secret values; the schema rejects literals in fields named like password, token, secret, key, DB URL, or connection string.
- A secret is a reference:
  - `{"secret": "env:NAME"}`: from the shell environment or the gitignored `.agents/secrets.env`; commands use it as `"$NAME"`.
    Every shell call starts fresh, so load the file in the same call: `set -a; . .agents/secrets.env; set +a; <cmd>`.
    If the file holds `op://` values, use `op run --env-file .agents/secrets.env -- <cmd>` instead.
    Loading secrets this way does not count as changing a registry command.
  - `{"secret": "op://vault/item/field"}`: 1Password, read on demand without printing, assigned and exported in the same shell call: `NAME="$(op read 'op://...')"; export NAME; <cmd>`.
- Never let a value appear in output, files, commits, command lines as a literal, logs, tickets, or chat, unless the user asks to see it.
- Browser logins: prefer a saved session (Playwright storage state) per account; when a password must be typed, it goes only into the login field, never into a reply.
- A reference does not resolve: tell the user which reference and why (`op whoami` fails = not signed in; item not found = missing entry; env var empty = missing line in `.agents/secrets.env`).
  Ask them to fix it there, not to paste the value into chat, and do not fall back to another account.
- Pick accounts by `role` from the target environment only.
  Never log in as a real customer; on prod use only the accounts listed there.

## 10. Create the registry

1. Draft from repo evidence first: `.env*.example` (variable names only), `.vercel/project.json`, `vercel.json`, `supabase/config.toml`, `Dockerfile`, compose files, `ecosystem.config.*`, CI workflows, deploy scripts, README.
2. Ask the user only what the repo cannot tell, in one batch, your drafts shown; it always starts with these, unless the registry already records them or the calling skill (`project-init` section 2) asked them in this run:
   - Which branch PRs/MRs go into (`integrationBranch`, `worktree-flow` section 0), never assumed.
   - Which environments exist: local or dev, staging, prod, and any other, each with its URL and the branch it deploys from.
   Then SSH aliases, test account roles and logins, rules such as deploy windows.
3. Write `.agents/environments.json` based on `templates/environments.json`, with `integrationBranch` set, and copy `templates/environments.schema.json` next to it.
   An environment the user does not know yet is left out and reported, never invented; `environments` may stay empty while only `integrationBranch` is known.
   A standard one the user says the project does not have (dev, staging or prod) goes in `absentEnvironments`, so `harness-map` stops asking for it.
4. Defaults: local and dev `autonomous` with testing `full`; staging `confirm-writes` with testing `non-destructive`; prod `confirm-each-step` with `allowedWithoutAsking: []`, `testDataAllowed: false`, and testing `smoke-only`.
   Writing a looser prod setting needs the user's explicit words.
5. Add `.agents/secrets.env`, `.agents/backups/`, and `.agents/deploy/` to `.gitignore`, and create `.agents/secrets.env.example` listing every `env:` name with an empty value.
   Then create or top up the real `.agents/secrets.env` in the main checkout from it, empty values only; an existing file is never overwritten, only missing names are appended:

   ```bash
   m="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"; mkdir -p "$m/.agents"; (umask 077; touch "$m/.agents/secrets.env")
   [ -n "$(tail -c1 "$m/.agents/secrets.env")" ] && echo >> "$m/.agents/secrets.env"   # a last line without a newline stays intact
   awk -F= 'FILENAME==ARGV[1]{k=$1; sub(/^export /,"",k); have[k]=1; next} /^[A-Z][A-Z0-9_]*=/ && !($1 in have){print $1"="}' \
     "$m/.agents/secrets.env" .agents/secrets.env.example >> "$m/.agents/secrets.env"
   ```

   In a worktree, link it as `worktree-flow` says (`ln -s "$m/.agents/secrets.env" .agents/secrets.env`).
   Tell the user which names to fill, and that they fill them in that file themselves, with the value or an `op://` reference; never ask for a value in chat.
   `harness-map` shows each name that is still empty or absent as missing on its environment's card.
6. Validate: `npx -y ajv-cli@5.0.0 validate --spec=draft2020 -s .agents/environments.schema.json -d .agents/environments.json`.
7. A service without a version endpoint gets one per `references/version-endpoint.md`, shipped as a normal PR/MR.
8. Run each remote service's `version` and `verify` once to prove the access works (on prod, ask first), and report anything that fails.
