---
name: betterstack-logs
description: >
  Use when setting up log shipping to Better Stack, connecting the Better Stack MCP, checking that logs arrive in Better Stack after a deploy, or reading a deployed environment's log history in Better Stack while debugging ("setup betterstack", "xem log trên Better Stack", "check log betterstack", "log history", "search logs", "trace_id này lỗi gì", "logs not showing in Better Stack").
  Not for live container output (`server-touch`, registry `logsCommand`) or writing code that logs (`logging-standard`).
user-invocable: true
---

# betterstack-logs

Logs are the fastest evidence of what a deployed environment did, and the easiest way to leak another team's data, burn context, or read prod without asking.
This skill sets up one source per project and environment, and reads it through the MCP with bounded queries.
What a log line contains is owned by `logging-standard`; environment facts and policies by `environments`; commands on a Docker host by `server-touch`.

## 1. Connect the MCP

- Check first: the Better Stack tools (`sources`, `query`) are already listed, or `/mcp` shows `betterstack` (or `betterstack-ro`) connected.
  `claude mcp list` showing `Needs authentication` means the server is added but not signed in: the user runs `/mcp` and signs in.
- Not connected: ask the user to install one of these, since both need their own login:
  - The official plugin, which also brings Better Stack's query skills: `/plugin marketplace add BetterStackHQ/claude-plugin`, then `/plugin install betterstack@betterstack`.
  - Or the server alone, at user scope: `! claude mcp add --transport http --scope user betterstack https://mcp.betterstack.com`.
  Then the user runs `/mcp`, selects `betterstack`, and signs in through the browser (OAuth); a new session may be needed before the tools appear.
- Tokens never go in repo files: no API token in a committed `.mcp.json`, no literal in any config; OAuth needs none.
  A client without OAuth gets the token from an environment variable (`Authorization: Bearer ${BETTERSTACK_API_TOKEN}`), set by the user.
- For a debugging-only setup, offer a read-only server next to or instead of the full one:
  `! claude mcp add --transport http --scope user betterstack-ro https://mcp.betterstack.com --header "X-MCP-Tools-Only: sources,source,source_fields,query_help,query_windows,query"`.
  Whether the allowlist header applies to an OAuth login is not documented: after `/mcp`, check that only those tools are listed, and tell the user if more appear.
- Verify: call `sources` and find the project's source names from the registry (section 3).
  Missing sources mean the wrong Better Stack team or account, not missing logs; ask the user which team holds them.
- Many MCP tools change state (incidents, dashboards, alerts, sources, team members); call one only when the user asks for that change.

## 2. Choose the shipping path

Per environment, from the registry's service `type` and `access.sharedHost`:

| Where the service runs | Path | `shipping` |
| --- | --- | --- |
| Vercel, Lambda, other serverless | `@logtail/node` in the app, flushed before every invocation ends (`logging-standard` `references/nextjs.md`) | `sdk` |
| Dedicated VPS or own cluster | In-app `@logtail/pino`, the Vector template, or the Better Stack Collector when its host metrics are wanted | `sdk`, `vector`, `collector` |
| VPS shared with other teams (`sharedHost` true or absent) | In-app `@logtail/pino`; a project-scoped Vector container only with the host owner's approval | `sdk`, `vector` |
| Supabase (Pro or higher) | Supabase log drain to its own source, `<project>-<env>-supabase` | `drain` |

- Vercel request and build logs: optionally add a Vercel drain into its own source (section 3), named in the service's registry `notes`.
  Never send the drain and the SDK into the same source.
- Never install the Better Stack Collector on a shared host.
  It mounts the host root and the Docker socket and reads every team's containers; filtering or sampling later does not undo that read, and "it is only for a test" is not an exception.
- On a shared host, the Vector container needs the Docker socket, which gives it control of the host and every team's containers.
  Use it only with explicit approval from the host owner or admin (usually not this session's user), recorded in the service's registry `notes`; otherwise ship in-app.
  Never run Better Stack's generated Vector setup on a shared host; it has no container filter, so use `templates/vector-shared-host.yaml`.
- A Collector or vendor Vector path is not done until its source is normalized to the contract: app JSON parsed to the top level and pino's numeric levels mapped to labels (`references/shipping.md`).
- Mechanics and tested snippets per path: `references/shipping.md`.

## 3. Sources and the registry

- One source per project per environment, `<project>-<env>`, such as `acme-staging` or `acme-prod`.
  Services share it and are told apart by the `service` field (`logging-standard`), so a mixed-up token shows up as a wrong `env` value rather than silently mixed logs.
- A platform drain gets its own source, `<project>-<env>-<platform>` (`acme-prod-vercel`), never the app source.
- A very high-volume service may get its own source, `<project>-<service>-<env>`, only by recording it as that service's `logs.source`.
  It needs its own token value in that service's secret store, so it ships in-app; the Vector template ships one source.
- The user creates the source (Telemetry, Sources, Connect source: HTTP for Vector or drains, JavaScript for the SDK) in the region the client's data must stay in.
  Create one through the MCP only when the user asks for exactly that.
- Record the source on each service's entry in `.agents/environments.json`, through the `environments` registry-change rule (diff, then a yes):

```json
"logs": { "provider": "betterstack", "source": "acme-staging", "sourceId": 123456, "shipping": "vector" }
```

- `sourceId` is optional; fill it from `sources` once the source exists.
- The registry holds no token.
  The ingest token is `BETTER_STACK_SOURCE_TOKEN` and the host `BETTER_STACK_INGESTING_HOST`, one value per environment, stored where that environment keeps runtime secrets (Vercel project env vars, the server's env file via `server-touch`, a Kubernetes Secret).
  On Vercel, set them only for the Vercel environment that maps to the registry environment: Preview gets the staging values or none, never prod's.
  The user pastes the token there, never into chat; list both names with empty values in `.env.example`.
- Reading logs needs only the MCP, never the ingest token.

## 4. Query logs while debugging

1. Name the environment (`environments` section 2), then find its service's `logs.source` in the registry.
   No `logs` object: Better Stack holds no history for it; read recent output with the service's `logsCommand` (`server-touch` on a Docker host), and propose a source only if the user wants history.
2. Policy: a Better Stack query against a `confirm-each-step` environment is a remote read; ask first, unless `allowedWithoutAsking` contains `logsQuery`.
   Ask once with a bounded plan: the source, each query with its window and `LIMIT`, and the number of polls.
   The yes covers that plan plus the metadata calls (`sources`, `source_fields`, `query_help`, `query_windows`); a new query, a wider window, or more polls asks again.
   Under other policies reads are free.
3. Run `sources`, `source_fields`, and `query_help` once per source and session (`references/queries.md`, tool flow).
   When Better Stack's plugin skills are installed, load `logs-query` (and `errors-query` or `collector-queries` when relevant) before the first query.
4. Know roughly when it happened: ask the user for the approximate time when it is unknown, then query the hot window before the archive (`references/queries.md`).
5. Start from the most specific key you have:
   - A failing request: an id the user or a test sent as `x-request-id` is matched on `request_id`; a W3C `traceparent` or `x-correlation-id` derived id, or a `trace_id` from a response header or a handover from `e2e-verify` or `root-cause`, on `trace_id` (pattern 2).
   - A tenant-scoped report: filter by the tenant id (`tenant_id`, or the project's declared name such as `organization_id`).
   - Nothing specific: counts by level per minute, then top error messages, then single rows.
6. Every query follows the rules and patterns in `references/queries.md`; never pull `raw` over many rows.
7. There is no live tail.
   To watch a reproduction, poll the last 2 to 5 minutes with `ORDER BY dt DESC LIMIT 20`, a few times, not in a loop.
8. Mask results before showing them (`environments` section 3); show ids, not people.
9. Report with the environment prefix and the query window: `[staging] 14:02-14:32 UTC: 3 errors, all StripeError on POST /invoices/:id/pay, trace 4bf9...`.
   Zero rows is reported as "none in this window and source", never as "no errors".

## 5. Verify shipping

Run after setting up a source and after any deploy that touches logging or the shipper.
Use the target environment; prod only when the user asks or the registry allows it.

1. Emit one uniquely tagged line in that environment, read-only: a request to a route that writes an `info` completion line (not the excluded health check) with a fresh id, for example `curl -sS -H "x-request-id: shipcheck-$(date -u +%Y%m%d%H%M%S)-$RANDOM" <url><route>`.
   On Next.js the proxy line is `debug`; use `/api/version`, which writes an info completion line through the `route()` wrapper in `logging-standard` `references/nextjs.md`.
2. Query the source with pattern 2a of `references/queries.md`, `request_id` equal to the sent id; batching delays lines by a few seconds, so poll up to about 2 minutes.
3. Check the row against the `logging-standard` contract: `level` is a label, `message`, `service`, `env` and `version` are set, `version` equals the environment's `version` command, `request_id` equals the sent id, `dt` is within a minute of the request.
4. No row after 2 minutes, in this order:
   - The line is in the container's or platform's own logs (`server-touch` for Docker, the platform's CLI or dashboard otherwise): if not, the app did not log it.
   - Both variables are set in that environment, checked by presence only.
   - The shipping package (`@logtail/pino` or `@logtail/node`) is a dependency of the running app.
   - Vector path: the shipper container's own logs show its HTTP responses; 403 means a wrong token, 413 a too large batch.
   - The query used the right source and team.
5. Report the source, the test id, the fields checked, and anything missing as a finding for `logging-standard`.
