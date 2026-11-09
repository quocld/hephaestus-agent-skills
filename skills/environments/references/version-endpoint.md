# Version endpoint: contract and recipes

Every deployed service tells what it was built from, so an agent can check whether an environment runs the newest build.
The registry's `version` commands, the deploy protocol's final check, and the version status report all read it.

## Contract

Two values, under the same names everywhere:

- `commit`: the full 40-character commit SHA the build came from. Deploy checks compare this one.
- `version`: the release name a person reads, from `APP_VERSION` (section "Where the values come from").

Where each kind of service exposes them:

| Service | Where | Registry `version` command |
| --- | --- | --- |
| API or backend over HTTP (Express, Fastify, NestJS) | `GET /health` | `curl -fsS <url>/health \| jq -r .commit` |
| Web app (Next.js, static SPA) | `GET /version.json` | `curl -fsS <url>/version.json \| jq -r .commit` |
| Worker, cron, anything without HTTP | the `app.started` log line at startup | the newest `app.started` line's `commit` (section "Workers") |

`/health` answers `200` while the process serves, with:

```json
{"status": "ok", "service": "api", "commit": "<40-character SHA>", "version": "v1.4.2", "builtAt": "2026-10-19T03:00:00Z", "env": "staging"}
```

`/version.json` answers the same object without `status`.

- Both values are fixed at build time, never read from `git` at runtime: Docker images and Vercel builds have no `.git` folder, and a runtime read on a VPS reports the checkout, not what the process was built from.
- A build that cannot find a value reports `"unknown"`; the deploy check then fails on `commit`, which is the intent.
- `/health` returns `commit` and `version` even when it also checks dependencies and answers `503`, so a broken deploy still says what it is.
  Load balancers and uptime probes that call it only read the status code; one that matches the old body (`ok`) is updated in the same change.
- Header `Cache-Control: no-store` on both, so a CDN never serves an old answer after a deploy.
- Reachable without logging in: exclude both paths from auth middleware and redirects.
- Nothing else: no env var dumps, dependency versions, hostnames, or branch names.
  A commit SHA is not sensitive; if the user still wants it private, protect it with a header token and put that token in the registry as a secret reference.
- Docker images also carry `org.opencontainers.image.revision=<commit>` and `org.opencontainers.image.version=<version>` labels.
- Databases are not versioned by this contract; their `version` is the latest applied migration.
- A project still on the older `/api/version` or `/version` with a `sha` field moves to these paths and names in one PR/MR, which also updates the registry's `version` and `verify` commands.

## Where the values come from at build time

Normalize them into `GIT_SHA`, `APP_VERSION` and `BUILT_AT` in one place in the build.

| Build runs on | `GIT_SHA` |
| --- | --- |
| Vercel | `VERCEL_GIT_COMMIT_SHA` (set automatically) |
| GitHub Actions | `GITHUB_SHA` |
| GitLab CI | `CI_COMMIT_SHA` |
| Docker build | `--build-arg GIT_SHA=$(git rev-parse HEAD)` with `ARG GIT_SHA` and `ENV GIT_SHA=$GIT_SHA` in the Dockerfile |
| VPS build in a git checkout | `git rev-parse HEAD`, read by the build config |

`APP_VERSION`:

- The project tags releases: `git describe --tags` (`v1.4.2` on a tag, `v1.4.2-3-g3f2a9c1` three commits after it); CI needs the tags fetched (`fetch-depth: 0` on GitHub Actions), Docker gets it as a build arg like `GIT_SHA`.
- No release tags, or none fetched: `git describe --tags` fails and the recipes fall back to the deployable's `package.json` `version`.
- Neither: `"unknown"`, and say so once in the PR/MR; `commit` still carries the deploy check.

## Node API: `GET /health` (Express, Fastify, NestJS)

Set the three variables in the image (`ENV`) or in the process manager's environment at deploy time, and serve them:

```ts
app.get('/health', (_req, res) => {
  res.set('Cache-Control', 'no-store').json({
    status: 'ok',
    service: 'api',
    commit: process.env.GIT_SHA ?? 'unknown',
    version: process.env.APP_VERSION ?? 'unknown',
    builtAt: process.env.BUILT_AT ?? 'unknown',
    env: process.env.APP_ENV ?? 'unknown',
  });
});
```

Register it before auth middleware; it stays out of the logs as a probe (`logging-standard` section 2).
For NestJS, a controller marked public in the project's own auth convention; with a global prefix the path becomes `/api/health`, and the registry command uses that path.

## Web app: `GET /version.json`

### Next.js (App Router)

`next.config` runs at build time, and values under `env` are inlined into the server bundle, so they survive any runtime environment:

```ts
// next.config.ts
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

function git(args: string): string | undefined {
  try {
    return execSync(`git ${args}`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() || undefined;
  } catch {
    return undefined;
  }
}

const GIT_SHA = process.env.GIT_SHA ?? process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GITHUB_SHA ?? process.env.CI_COMMIT_SHA ?? git('rev-parse HEAD') ?? 'unknown';
const pkgVersion: string | undefined = JSON.parse(readFileSync('package.json', 'utf8')).version;
const APP_VERSION = process.env.APP_VERSION ?? git('describe --tags') ?? pkgVersion ?? 'unknown';

const nextConfig = {
  env: { GIT_SHA, APP_VERSION, BUILT_AT: new Date().toISOString() },
};

export default nextConfig;
```

Merge this into the existing config instead of replacing it.

```ts
// app/version.json/route.ts
export const dynamic = 'force-dynamic';

export function GET() {
  return Response.json(
    { service: 'web', commit: process.env.GIT_SHA ?? 'unknown', version: process.env.APP_VERSION ?? 'unknown', builtAt: process.env.BUILT_AT ?? 'unknown', env: process.env.APP_ENV ?? 'unknown' },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
```

Then add `/version.json` to the public paths in `proxy.ts` or `middleware.ts` (or whatever guards routes) and check it with a logged-out request.
In a project that follows `logging-standard`, wrap this handler with its `route()` wrapper (`references/nextjs.md`), so each call writes the info line that `betterstack-logs` section 5 looks for.
Never also ship a `public/version.json`: it would shadow or conflict with the route.

### Static SPA (Vite or any build with no server)

Write the file into the build output as the last build step, `"build": "vite build && node scripts/write-version.mjs dist"`:

```js
// scripts/write-version.mjs
import { execSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

const git = (args) => { try { return execSync(`git ${args}`, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim() || undefined; } catch { return undefined; } };
const pkg = JSON.parse(readFileSync('package.json', 'utf8'));
const out = process.argv[2] ?? 'dist';

writeFileSync(`${out}/version.json`, JSON.stringify({
  service: 'web',
  commit: process.env.GIT_SHA ?? process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GITHUB_SHA ?? process.env.CI_COMMIT_SHA ?? git('rev-parse HEAD') ?? 'unknown',
  version: process.env.APP_VERSION ?? git('describe --tags') ?? pkg.version ?? 'unknown',
  builtAt: new Date().toISOString(),
  env: process.env.APP_ENV ?? 'unknown',
}) + '\n');
```

Serve it with `Cache-Control: no-store` from the host's header config (`vercel.json` `headers`, an nginx `location = /version.json` block), and make sure the SPA fallback does not answer `/version.json` with `index.html`.

## Workers: the startup log line

A process without HTTP writes one `info` line when it is ready to take work, through the project's logger, so the `logging-standard` base fields put `commit` and `version` on it:

```ts
logger.info({ event: EVENT.APP_STARTED, queues: ['invoice.send'] }, 'worker started');
```

The registry's `version` command for a worker is one of these, in order of preference:

1. The running container's label, which says what image runs: `ssh <alias> "docker inspect -f '{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' <container>"`.
2. The newest startup line in the platform's own logs, which for a recreated container hold only this build's lines: `ssh <alias> 'docker logs <container> 2>&1' | grep '"event":"app.started"' | tail -n 1 | jq -r .commit`.

The label alone does not prove the build started; after a deploy, also read the startup line: option 2, or in Better Stack pattern 7 of `betterstack-logs` `references/queries.md` (a query, not a registry command, under `betterstack-logs` section 4).
A worker that restarts in a loop writes many `app.started` lines; that is a failed deploy, not a version answer.

## Proving it works

1. Locally: build with a known `GIT_SHA` and `APP_VERSION`, start, and the endpoint (or the worker's first line) prints both: `curl -fsS localhost:<port>/health | jq '{commit, version}'`.
2. Logged out: `/health` and `/version.json` return 200 JSON, not a redirect to the login page.
3. After the first deploy to each environment: the registry `version` prints the deployed `commit`.
