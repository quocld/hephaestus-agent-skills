---
name: server-touch
description: >
  Use before any operation on a live server running Docker Compose: "xem log docker", "pull về và recreate", "deploy lên server", "set env trên server", "seed acc trên server".
user-invocable: true
---

# server-touch

On a shared host, one global docker command takes down other teams' projects.
Every command here is scoped to one project, and nothing outside it is touched.

Server facts come from the registry (`environments` skill), never from memory: the `access.ssh` alias, `appDir`, `composeProject`, `composeFiles`, `sharedHost`, and the `deploy`/`rollback` commands.
The environment's policy decides what needs confirmation; this skill only covers the mechanics.
Below, `$DC` means the fully scoped compose command run inside `appDir`: `docker compose -p <composeProject> -f <file1> -f <file2> ...`.

## 0. Rules before any command

1. Every compose command carries `-p <composeProject>` and every file in `composeFiles`.
   Without `-p` it can act on another project; without all files it fails with errors like "service has neither image nor build context".
2. Treat the host as shared unless the registry says `sharedHost: false`.
   On a shared host, never run anything global, because it reaches other projects:
   - `docker system prune`, `docker image prune -a`, `docker volume prune`, `docker network prune`, `docker builder prune`, `docker buildx prune`.
   - Anything over `$(docker ps -aq)` or a similar sweep.
   - `docker compose down` without `-p`, and `down -v` anywhere (it deletes volumes, which means databases).
   - Restarting the Docker daemon, editing the host's reverse proxy, firewall, or system packages.
   - Installing a host-wide log collector such as the Better Stack Collector, which reads every team's containers; ship logs as `betterstack-logs` section 2 says.
   Cleanup is the user's call: ask, and scope it to this project (e.g. remove only this project's old image tags).
3. Stay inside `appDir`; never read or write another project's directory.
4. Recreate instead of down/up: `$DC up -d --force-recreate --no-build <services>`.
5. Logs never follow: use `--tail=N` or `--since=Nm`, never `-f`, which blocks the session.
   `$DC logs --tail=N` is for live container output only; history and search across services go through `betterstack-logs`.
6. SSH with `-o ConnectTimeout=15` (put it in the `~/.ssh/config` entry), one command per call.
   Before the first connection to a new host, show the user the host key fingerprint instead of blindly accepting it.
7. Back up any server file before editing it: `cp .env .env.bak.$(date +%s)`.

## 1. Deploy

- If the registry's `deploy` is a versioned deploy script, it is the only way to deploy by hand.
  Do not rebuild its steps manually: the script carries the backup, migration, health check, and auto-revert that hand commands skip.
- Read the script once before trusting it.
  It should back up the database before migrating, stop when the backup or migration fails, wait for health, and revert to the previous tag when unhealthy.
  If a piece is missing, tell the user; do not patch the script on the server.
- When CI builds the images, the server only pulls.
  Never `build` on a shared host: it takes CPU from other projects and the running stack no longer matches the CI artifact.
- Images are tagged with the commit SHA, so the running tag is the environment's `version`.
- Registry tokens that expire: log in with a project-scoped config, `DOCKER_CONFIG=<appDir>/.docker docker login ...`, never the host's global credentials.
- One-shot services such as `migrate` show `Exited (0)` after success; that is normal.
  A non-zero exit is a failed migration: stop and report.

## 2. Verify after every deploy or recreate

```bash
$DC ps --format 'table {{.Name}}\t{{.Status}}'
$DC logs --since=2m --no-color <services> | grep -iE 'error|fatal|"level":(50|60)' | tail -20
```

- Every long-running service is `Up`, and `(healthy)` where it has a health check.
- Run the environment's `verify` (real health endpoint) and `version` (running tag equals `<sha>`).
- Known harmless noise (bot 404s, an old health check path) belongs in the service's registry `notes`, so the next agent does not chase it.

## 3. Roll back in two levels

- **A. Code only:** redeploy the previous image tag with the project's rollback command.
  It keeps all data and works whenever migrations are additive, so always try it first.
- **B. Code and schema:** restore a database dump.
  It destroys every row written after the dump.
  Use it only when A cannot start because a migration removed or changed something the old code needs.
  The user decides explicitly every time; stop the writers (api, workers) first and dump the current state before restoring.
- There is no automatic schema rollback: with forward-only migrations, the dump is the only way back, and restoring it is a human decision.

## 4. Server environment variables

- Back up `.env`, then change one key.
  Secret values travel through stdin from the local secrets file, never as a literal on the command line.
- Never print `.env` or a value from it.
  Confirm by key name: `grep -c '^KEY=' .env`, or inside the container `docker exec <container> sh -c 'test -n "$KEY" && echo set || echo missing'`.
- Variables loaded through `env_file` apply only after a recreate; an env-only change needs no image rebuild.
  Recreate exactly the services that read the variable.
- Add the key name (no value) to the project's `.env.example` so the next deploy target knows it exists.

## 5. Database in the container

- Get container names from `$DC ps`; never guess them.
- `docker exec -i <db-container> psql -U <user> -d <db> -v ON_ERROR_STOP=1`, with SQL in a heredoc to avoid quoting through ssh and docker.
- Superuser roles bypass row-level security.
  Queries that must respect tenant isolation run as the app role, or set the app's session flags inside the same transaction.
- Writes follow `environments` section 8 on `confirm-writes` and `confirm-each-step` environments.

## 6. Seed accounts on a server

- Check the environment's `testing` scope and `data.testDataAllowed` first.
- Create accounts through the app's own code path (signup API, admin CLI, or the app's hashing library inside the app container), never with a hash made by another library or other parameters.
- Pass the password as an environment variable (`docker exec -e PW ...`), never as a literal argument.
- Verify with a real login against the API and check the returned role.
- Record the account in the registry (role, login, secret reference), never the password itself.

## 7. Interactive commands

Logins, token rotation, and anything that prompts: ask the user to run it with `! <command>` so the output lands in the session.

## Before handing back

- Every compose command carried `-p <composeProject>` and all compose files.
- No global or prune command ran.
- Every edited server file has a backup.
- `ps` is healthy, logs since boot show no errors, `version` matches the target.
- New facts (container names, harmless noise, env keys) are written into the registry.
