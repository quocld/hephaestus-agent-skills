---
name: environments
description: >
  Work safely across a project's environments (dev, staging, prod, ...) from one registry file, `.agents/environments.json`: URLs, servers and SSH aliases, deploy targets (VPS, Vercel, Supabase, Docker), deploy/verify/rollback commands, test accounts, and per-environment rules, with step-by-step confirmation on prod.
  Use before any action against a non-local environment: deploying, SSH into a server, running a migration, reading remote logs, logging in with a test account, creating test data; when the user says "deploy lên staging", "ssh vào server", "chạy trên prod", "account test", "môi trường nào"; and to create or update the registry ("init environments", "thêm môi trường", "thêm server").
user-invocable: true
---

# environments

The registry is the only source of environment facts.
An agent that takes a host, branch, command, or password from memory or chat history will one day run a staging command on prod.

## 1. Load and maintain the registry

- Read `.agents/environments.json` at the repo root, in full, before the first environment action of the session.
- Missing, and the task needs a non-local environment: run section 7 first.
  Do not improvise hosts or commands in the meantime.
- When the user states a new fact (server, account, URL, rule), put it in the registry instead of keeping it in chat.
- Every registry change is shown as a diff and written only after a yes; it applies from the next action.
  Changes that weaken safety (`policy`, `allowedWithoutAsking`, `data.testDataAllowed`, `rules`, `defaultEnvironment`, or any command of a `confirm-each-step` environment) need the user to ask for that change explicitly.
- `version`, `verify`, and `logs` commands must be read-only; refuse to register one that writes.
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
| `confirm-each-step` | Free only for kinds in `allowedWithoutAsking`; ask for every other remote command | Section 4, every step |

- `allowedWithoutAsking` lists registry commands by name (`version`, `logs`, `verify`); any other remote command, including ad-hoc SQL, asks first.
  Local reads (git, files in the repo, `op whoami`) are always free.
- `rules` add to the policy.
  When a rule is stricter, follow it; when it is looser than the policy, follow the policy and point out the conflict.
  When a rule depends on something you cannot observe (a customer event, telling the team), ask the user before acting.
- `data.testDataAllowed: false` is a kill switch: never create, modify, or delete records in that environment, except through reviewed migrations shipped by the deploy protocol.
  Where test data is allowed, put `testDataMarker` on every record you create and delete those records when done.
- Approval never carries over: not from an earlier session, an earlier deploy, or another environment.
- Before showing remote logs or query results in chat, mask secrets, tokens, and personal data such as emails and phone numbers.

## 4. `confirm-each-step` protocol (prod)

Placeholders in registry commands:

- `<sha>`: the full 40-character SHA being deployed.
- `<previous-sha>`: the code version captured in pre-flight from `version`; rollback depends on it.
  For a database, `version` returns the latest applied migration instead; capture it too.
- `<timestamp>`: UTC `YYYYMMDD-HHMM`.
- Anything else (`<migration-name>`, ...): filled in the plan where the user can see it.

Before the first step:

1. Pre-flight, read-only: capture every service's `version`, resolve `<sha>`, list pending migrations, check every rule (deploy windows, events), and create the clean deploy checkout (`git worktree add .agents/deploy/<sha> <sha>`); commands that read the local tree run from there.
2. Prove what was tested is what ships: the tree at `<sha>` must equal the tree that passed on staging (`git diff --stat <staging-sha> <sha>` is empty).
   Proof that staging passed is an E2E evidence file or the user's explicit word.
3. Present a numbered plan: services in `deployOrder` (default db before web), then each service's `deploy` items in order, one item per step.
   For every step, show the exact command (secrets masked), what it changes, its check, and its undo.
   Where the registry has no per-step check or undo, propose one and mark it "proposed"; the plan approval covers it.
   A step may be skipped only when the plan says why (e.g. no function changed).
4. Get approval of the plan.
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
- A remote service needs `version`, `deploy`, `verify`, and `rollback`; `logs` where the platform has a CLI for it.
  One is missing: propose it from `references/deploy-targets.md`, get it confirmed, write it into the registry, then use it.
- SSH only through the alias in `access.ssh` (defined in `~/.ssh/config`), one remote command per call: `ssh <alias> '<cmd>'`.
- "Pushed" is not "deployed": a deploy is done when `version` matches the target and `verify` passes.
- Read the section of `references/deploy-targets.md` for each service type you touch; it holds the platform traps (Supabase link state, Vercel git vs. CLI deploys, VPS release folders).

## 6. Secrets and test accounts

- The registry is committed and holds no secret values; the schema rejects literals in fields named like password, token, secret, key, DB URL, or connection string.
- A secret is a reference:
  - `{"secret": "env:NAME"}`: from the shell environment or the gitignored `.agents/secrets.env`; commands use it as `"$NAME"`.
    Every shell call starts fresh, so load the file in the same call: `set -a; . .agents/secrets.env; set +a; <cmd>`.
    If the file holds `op://` values, use `op run --env-file .agents/secrets.env -- <cmd>` instead.
    Loading secrets this way does not count as changing a registry command.
  - `{"secret": "op://vault/item/field"}`: 1Password, read on demand without printing: `NAME="$(op read 'op://...')" <cmd>`.
- Never let a value appear in output, files, commits, command lines as a literal, logs, tickets, or chat, unless the user asks to see it.
- Browser logins: prefer a saved session (Playwright storage state) per account; when a password must be typed, it goes only into the login field, never into a reply.
- A reference does not resolve: tell the user which reference and why (`op whoami` fails = not signed in; item not found = missing entry; env var empty = missing line in `.agents/secrets.env`).
  Ask them to fix it there, not to paste the value into chat, and do not fall back to another account.
- Pick accounts by `role` from the target environment only.
  Never log in as a real customer; on prod use only the accounts listed there.

## 7. Create the registry

1. Draft from repo evidence first: `.env*.example` (variable names only), `.vercel/project.json`, `vercel.json`, `supabase/config.toml`, `Dockerfile`, compose files, `ecosystem.config.*`, CI workflows, deploy scripts, README.
2. Ask the user only what the repo cannot tell, in one batch: the environment list and URLs, SSH aliases, test account roles and logins, rules such as deploy windows.
3. Write `.agents/environments.json` based on `templates/environments.json`, and copy `templates/environments.schema.json` next to it.
4. Defaults: local and dev `autonomous`; staging `confirm-writes`; prod `confirm-each-step` with `allowedWithoutAsking: ["version", "logs", "verify"]` and `testDataAllowed: false`.
   Writing a looser prod setting needs the user's explicit words.
5. Add `.agents/secrets.env` and `.agents/backups/` to `.gitignore`, and create `.agents/secrets.env.example` listing every `env:` name with an empty value.
6. Validate: `npx -y ajv-cli@5.0.0 validate --spec=draft2020 -s .agents/environments.schema.json -d .agents/environments.json`.
7. Run each remote service's `version` and `verify` once (read-only) to prove the access works, and report anything that fails.
