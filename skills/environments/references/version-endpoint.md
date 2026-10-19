# Version endpoint: contract and recipes

Every HTTP service the project deploys exposes the commit it was built from.
The registry's `version` commands, the deploy protocol's final check, and the version status report all read it.

## Contract

`GET /api/version` (web apps) or `GET /version` (API services) returns `200` with:

```json
{"service": "web", "sha": "<full 40-character commit SHA>", "builtAt": "2026-10-19T03:00:00Z", "env": "staging"}
```

- `sha` is fixed at build time, never read from `git` at runtime: Docker images and Vercel builds have no `.git` folder, and a runtime read on a VPS reports the checkout, not what the process was built from.
- A build that cannot find its SHA reports `"unknown"`; the deploy check then fails, which is the intent.
- Header `Cache-Control: no-store`, so a CDN never serves an old answer after a deploy.
- Reachable without logging in: exclude the path from auth middleware and redirects.
- Nothing else: no env var dumps, dependency versions, hostnames, or branch names.
  A commit SHA alone is not sensitive; if the user still wants it private, protect it with a header token and put that token in the registry as a secret reference.
- The registry command prints only the SHA: `curl -fsS <url>/api/version | jq -r .sha`.
- Services without HTTP (workers, cron): log the SHA at startup, and label Docker images with `org.opencontainers.image.revision=<sha>`; the registry `version` reads the running container's label or image tag.
- Databases are not versioned by this endpoint; their `version` is the latest applied migration.

## Where the SHA comes from at build time

| Build runs on | Variable |
| --- | --- |
| Vercel | `VERCEL_GIT_COMMIT_SHA` (set automatically) |
| GitHub Actions | `GITHUB_SHA` |
| GitLab CI | `CI_COMMIT_SHA` |
| Docker build | `--build-arg GIT_SHA=$(git rev-parse HEAD)` with `ARG GIT_SHA` and `ENV GIT_SHA=$GIT_SHA` in the Dockerfile |
| VPS build in a git checkout | `git rev-parse HEAD`, read by the build config |

Normalize all of them into one variable, `GIT_SHA`, plus `BUILT_AT`, in a single place in the build.

## Next.js (App Router)

`next.config` runs at build time, and values under `env` are inlined into the server bundle, so they survive any runtime environment:

```ts
// next.config.ts
import { execSync } from "node:child_process";

function gitSha(): string {
  const fromCi = process.env.GIT_SHA ?? process.env.VERCEL_GIT_COMMIT_SHA ?? process.env.GITHUB_SHA ?? process.env.CI_COMMIT_SHA;
  if (fromCi) return fromCi;
  try {
    return execSync("git rev-parse HEAD").toString().trim();
  } catch {
    return "unknown";
  }
}

const nextConfig = {
  env: { GIT_SHA: gitSha(), BUILT_AT: new Date().toISOString() },
};

export default nextConfig;
```

Merge this into the existing config instead of replacing it.

```ts
// app/api/version/route.ts
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(
    { service: "web", sha: process.env.GIT_SHA ?? "unknown", builtAt: process.env.BUILT_AT ?? "unknown", env: process.env.APP_ENV ?? "unknown" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
```

Then add `/api/version` to the public paths in `middleware.ts` (or whatever guards routes) and check it with a logged-out request.
In a project that follows `logging-standard`, wrap this handler with its `route()` wrapper (`references/nextjs.md`), so each call writes the info line that `betterstack-logs` section 5 looks for.

## Node API (Express, Fastify, NestJS)

Set `GIT_SHA` and `BUILT_AT` in the image (`ENV`) or in the process manager's environment at deploy time, and serve them:

```ts
app.get("/version", (_req, res) => {
  res.set("Cache-Control", "no-store").json({ service: "api", sha: process.env.GIT_SHA ?? "unknown", builtAt: process.env.BUILT_AT ?? "unknown", env: process.env.APP_ENV ?? "unknown" });
});
```

Register it before auth middleware.
For NestJS, a controller marked public in the project's own auth convention.

## Proving it works

1. Locally: build with a known SHA, start, `curl -fsS localhost:<port>/api/version | jq -r .sha` prints it.
2. Logged out: the same request returns 200 JSON, not a redirect to the login page.
3. After the first deploy to each environment: the registry `version` prints the deployed SHA.
