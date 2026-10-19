---
name: logging-standard
description: >
  Use when writing or reviewing code that logs, when creating or changing a logger, request or job correlation, or log redaction, and when the user says "setup log", "setup logger", "thêm log", "chuẩn hoá log", "log bị lộ token", "log quá nhiều", "review log".
user-invocable: true
---

# logging-standard

Agents debug production by querying logs with SQL (`betterstack-logs`), and a query only works when every service writes the same fields under the same names.
A log line is also a copy of data that leaves the app, so a careless line is a leak.

Implementation: Node APIs, workers and NestJS in `references/pino-node.md`, which also owns the tested versions; Next.js and serverless functions in `references/nextjs.md`.
Where logs are shipped, sources, and reading logs belong to `betterstack-logs`.

## 1. Field contract

Every line is one JSON object with these fields, as nested objects, never dotted keys (`http.status_code` is `{"http": {"status_code": 404}}`).

| Field | Type | Required | Example |
| --- | --- | --- | --- |
| `message` | string, a short human sentence with no variable data | always | `"invoice paid"` |
| `timestamp` | string, ISO 8601 UTC with milliseconds | always | `"2026-10-19T07:43:47.967Z"` |
| `time` | string, same value as `timestamp` | pino only | `"2026-10-19T07:43:47.967Z"` |
| `level` | number in pino, label once in Better Stack | always | `30` in the process, `"info"` in Better Stack |
| `service` | string, the service key in `.agents/environments.json`; without a registry, the deployable's short name, later its registry key | always | `"api"` |
| `env` | string, the registry environment name, from `APP_ENV`; `local` when unset | always | `"production"` |
| `version` | string, the commit SHA the version endpoint reports, from `GIT_SHA`; `unknown` when unset | always | `"3f2a9c1e0b7d4a6f8e2c5b1d9a0f7e6c4b3a2d1e"` |
| `trace_id` | string, 32 lowercase hex or a validated inbound id | in requests and jobs | `"4bf92f3577b34da6a3ce929d0e0e4736"` |
| `request_id` | string | in requests, and jobs a request enqueued | `"0199c7c8-5d42-4c4a-9414-325d2de609e4"` |
| `tenant_id` | string | once the tenant is known | `"org_42"` |
| `user_id` | string, the internal id only | once the caller is known | `"usr_7"` |
| `event` | string, section 2 | on every line an alert, chart or count uses | `"invoice.paid"` |
| `error` | `{type, message, stack, cause}` and nothing else, `cause` the same shape | when an error is logged | `{"type": "Error", "message": "charge failed", "cause": {...}}` |
| `http` | `{method, route, status_code, duration_ms}` | request completion lines | `{"method": "GET", "route": "/invoices/:id", "status_code": 200, "duration_ms": 3}` |
| `job` | `{name, id, attempt}`, `attempt` 1-based | inside a job | `{"name": "invoice.send", "id": "job_1", "attempt": 1}` |
| `duration_ms` | number | lines that close a non-HTTP operation | `412` |
| `sample_rate` | number | sampled lines (section 6) | `0.1` |

- `local` or `unknown` on a line from a deployed environment is a deploy bug: set `APP_ENV` and `GIT_SHA` there.
- Domain ids go at the top level in snake_case (`invoice_id`), as ids, never as objects.
- No second name for a contract field: not `msg`, `err`, `reqId`, `correlationId`, `svc`, or `name` for the service.
- The one allowed alias: a project may keep an existing tenant field name (Westmont's `organization_id`) if its agent setup block from `project-init` declares it in one line, e.g. `Logging: tenant field is organization_id (logging-standard alias).`
- `level` stays numeric in pino because pino's multi-target transports require it, `@logtail/pino` maps numbers to labels on ship (0.5.8 turns any string level into `fatal`), and existing scripts grep numeric levels.
  Better Stack stores the label; a Vector or collector path must map the number to the label before shipping (`betterstack-logs`).
- `time` exists because `@logtail/pino` turns it into Better Stack's `dt` and version 0.5.8 throws without it.

## 2. Levels and events

| Level | Use for |
| --- | --- |
| `fatal` | The process cannot continue; logged once, right before exit |
| `error` | An operation failed and someone must act: a 5xx, a job's final failure, a failed payment webhook |
| `warn` | Handled but abnormal: a 4xx, a job attempt that will retry, a fallback taken, a limit nearly reached |
| `info` | Business events and the one completion line per request or job |
| `debug` | Detail for development; off in production |

- Production runs at `info` from `LOG_LEVEL`; raise one service to `debug` only for a bounded investigation and set it back.
- One completion line per HTTP request: 2xx and 3xx `info`, 4xx `warn`, 5xx `error`; no separate "request received" line above `debug`.
- An expected 4xx (validation failed, not found, permission denied) is that one line: the handler sets its `event` and fields on the completion line (`setRequestOutcome` in `pino-node.md`, `scope.outcome` in `nextjs.md`) and logs no second line.
  Every completion line carries `http`, so queries select completion lines by `http`, not by event.
- Health, liveness and readiness probes are never logged.
- An event name is `<domain>.<entity>.<past-tense verb>` or `<domain>.<past-tense verb>`: lowercase, dot-separated, words in snake_case (`invoice.paid`, `auth.login.failed`, `job.attempt_failed`).
- Never put ids, counts, or user input in an event name or in `message`; they go in fields.
- Each service keeps its event names as constants in one file, so adding or renaming one is a visible diff.
- Renaming an event breaks the alerts and saved queries that use it: treat it as a contract change and update them in the same change (`betterstack-logs`).
- Reserved names, emitted by the reference code: `http.request.completed`, `http.request.failed`, `job.completed`, `job.attempt_failed`, `job.failed`, `app.started`, `app.stopping`, `app.crashed`.

## 3. Correlation

- Inbound, in this order: a valid W3C `traceparent` with a non-zero trace id gives `trace_id`; else a valid `x-correlation-id`; else a new 32-hex id.
  A valid `x-request-id` gives `request_id`; else a new UUID.
- Inbound ids are attacker-controlled: accept only `^[A-Za-z0-9._:-]{1,128}$` (and the exact `traceparent` format), replace anything else, and never log the rejected value.
  The same check applies to any id read from a path, query or header before it goes on a line.
- Return `x-request-id` on every response, so a user's bug report or a browser trace leads to the lines.
- Calls to the project's own services send `x-correlation-id: <trace_id>`; with OpenTelemetry installed, let OTel propagate `traceparent` and inject `trace_id`, and do not generate a second id.
- The ids live in an AsyncLocalStorage context that the logger reads on every line; auth sets `tenant_id` and `user_id` into it once, from the authenticated caller, never from a header or path the caller controls, and code never passes them by hand.
  An app with no auth yet may set `tenant_id` from the route's tenant parameter after the `safeId` check, with a `TODO(auth)` comment at that line, and leaves `user_id` unset.
- Enqueuing a job copies `trace_id`, `request_id`, `tenant_id` and `user_id` into the job payload; the worker re-enters that context and adds `job`.
  A scheduled job with no request starts a new `trace_id` per run.

## 4. Errors

- Log an error once, at the boundary that handles it: the request's completion line, the job wrapper, `onRequestError` in Next.js, a script's top-level catch, or the catch that recovers (then at `warn`).
- Never log and rethrow.
  "The extra context helps" is not an exception: wrap the error with `new Error('charge failed', { cause: err })` and let the boundary log the chain.
  "The caller might not log it" is not an exception either: then the caller is missing its boundary; add it there.
- The job wrapper is the one place that logs and rethrows, and only because the queue library needs the throw to schedule a retry and logs nothing itself.
  Work with no queue to retry it ends that rethrow with an empty catch, since the wrapper already logged it.
- Pass the Error object (`{ error }` or `{ err }`), never `err.message` or `String(err)`, so `type`, `stack` and the `cause` chain survive.
- Expected outcomes (validation failed, not found, permission denied) are `warn` or `info`, never `error`: inside a request they name the completion line (section 2), elsewhere they are one line with an `event`.
- Error messages can carry personal data (a database message quoting the duplicate email); messages you write never include it, and redaction cannot scrub it (section 5).

## 5. Redaction and PII

- Log ids, not objects: `user_id`, not the user; `invoice_id`, not the invoice; never request or response bodies, header bags, or full URLs (query strings carry tokens; log the route template).
- Never log an error's own extra properties: a body parser's error carries the raw body, an HTTP client's carries the request headers.
  A 4xx caused by the request (malformed or oversized body) is logged by its completion line alone, without the error.
- The logger's redaction list is the safety net, not the plan; the defaults in each reference cover credentials, emails, phones and card fields, and a project adds paths without removing defaults.
- Censor with `[REDACTED]` by default, so a reader and the test can see the guard fired; remove the key instead (pino `remove: true`) only when its presence alone tells something sensitive or the value is large.
- Redaction matches keys, never text: tokens, passwords, emails, phone numbers, card data and addresses never go into `message` or into error messages you construct.
- IP addresses and user agents are personal data under GDPR; log them only where a feature needs them, and say so in review.
- A secret found in shipped logs: rotate the secret first, then fix the code, then tell the user, who decides about deleting the logs in Better Stack.

## 6. Volume and cost

- A line stays under 100 KiB, Better Stack's recommended maximum; the reference loggers replace a larger line with a summary marked `truncated: true`.
- No bodies, no lists of records, no whole database rows: log counts and ids (`item_count`, `invoice_ids` only when short).
- In loops, log once per batch with counts, not once per item.
- Sample only high-volume `info` success events (cache hits, polling), with `sample_rate` on the line so counts can be scaled.
  Never sample `warn` and above, audit events, or events an alert counts.
- `debug` off and probes silent in production (section 2).

## 7. Tests

Every service that logs has these tests, built on the project's real logger factory and its real middleware registration, never a copy:

1. Contract and redaction: capture lines from a destination stream while a real request runs through the app's middleware and a handler logs an object holding a password and an authorization header.
   Assert the secret strings appear in no line, `[REDACTED]` appears, the health probe left no line, and the completion line has every always-required field, the right numeric level, the four `http` keys, and no `req` dump.
2. Error once: a route that throws an error with a cause and an extra property produces exactly one line at `error` or above, with `error.cause` and no keys beyond the four.
3. Malformed body: invalid JSON holding a card token and an email gives a 400 and one `warn` line that contains neither.
4. Job correlation: a job enqueued inside a request logs that request's `request_id` and `tenant_id`.
5. Proof the guards are mounted: remove the default redaction paths once and watch test 1 fail; make the error handler answer every error as a 500 with the error attached and watch test 3 fail; restore both.

Templates: the `Tests` section of each reference.
