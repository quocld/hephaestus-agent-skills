# Querying Better Stack logs through the MCP

This file holds the project-specific query shapes; the official Better Stack plugin skills own the general query rules.
When the plugin is installed, load its `logs-query` skill before the first query, `errors-query` for the Errors product, and `collector-queries` for sources fed by the Better Stack Collector; where they disagree with this file, they win.

## Tool flow

Tool names below are the snake_case names the official plugin skills use.
Their parameter names are not documented in prose, so read each tool's input schema from the live server (`/mcp`, or the schema shown when the tool loads) before the first call.

1. `sources`: find the source whose name equals the registry's `logs.source` for the target environment (one per project and environment, unless a service has its own); note its id and team.
2. `source_fields`: the fields this source really has.
   Check that the contract fields exist (`level`, `message`, `service`, `env`, `trace_id`); if a field is missing or sits under `message.*`, the source is not normalized (section "Two shapes" below).
3. `query_help` with source type `logs`: the exact hot and archive table names for this source, and the service-name expression when the source mixes services.
   Copy table names and that expression verbatim; never build them by hand.
4. `query_windows`: before any query that reads the archive (`s3Cluster`) over more than a few hours, and whenever a hot-window query returned nothing; it splits the range into windows the server can run.
5. `query`: one bounded SQL statement per call.
   It takes no template variables, so `{{source}}`, `{{time}}`, `{{start_time}}` and `{{end_time}}` must already be replaced with real table names and `dt` bounds.

## Storage windows

- `remote(t<team_id>_<source>_logs)`: hot storage, the recent logs only.
  The official skill says about the last 30 minutes; Better Stack's Grafana guide implies longer, so treat 30 minutes as the safe bound and read the real one from `query_help`.
- `s3Cluster(primary, t<team_id>_<source>_s3)` with `_row_type = 1`: archived logs (`_row_type = 3` is spans).
  Anything older than the hot window lives only here.
- A range that crosses the hot window needs both, joined with `UNION ALL`, with the `dt` bound inside each branch so the archive scan stays small.
- Concurrency is limited (4 log queries at a time on the HTTP API; the MCP's limit is not documented): run queries one after another, never in parallel batches.
- On a memory or timeout error, shorten the window or filter earlier before anything else.

## Rules for every query

- A `dt` bound on every branch, and a `LIMIT` on the outer result.
  Never put a `LIMIT` on an input to an aggregate: it undercounts.
- Start with the hot window around the reported time; widen to the archive through `query_windows` only when that returns nothing.
- Select only the fields the question needs, cut long text with `substring(..., 1, 300)`, and never `SELECT raw` over more than one known row.
- Read a field with `JSONExtract(raw, 'parent', 'child', 'Nullable(String)')`: one argument per nesting level, a `Nullable` type.
  Use `Nullable(Float64)` or `Nullable(Int64)` for numbers.
- Look up an id (`trace_id`, `request_id`, `tenant_id`, `user_id`) with a case-sensitive `raw LIKE '%<id>%'` prefilter, then the exact JSON equality.
- Search a keyword with `positionCaseInsensitive(<field>, '<keyword>') > 0`.
- Aggregate with `count()`, `avg()`, `sum()`, `quantile()` on logs; never the `*Merge` functions, which are for metrics.
- Zero rows is not proof of absence: retry once without the level or service filter, then widen to the archive, before concluding.
- For volume over long ranges, prefer the source's metrics (`sum(logs_count)`, see the official `logs-query` skill) to a raw scan.

## Two shapes of the same log line

- Lines shipped by `@logtail/pino`, `@logtail/node`, or the `templates/vector-shared-host.yaml` pipeline arrive with the app's fields at the top level and `level` as a lowercase label (`info`, `warn`, `error`, `fatal`).
- Lines shipped by the vendor-generated Vector config or the Better Stack Collector without the normalization in `shipping.md` keep the app's JSON as a string in `message`, which Better Stack flattens to `message.level`, `message.trace_id`, and so on, with the pino level still numeric (`50` = error, `60` = fatal).
  `source_fields` shows which shape a source has; such a source is a setup finding: add the normalization, and until then prefix every path with `'message'` (`JSONExtract(raw, 'message', 'trace_id', 'Nullable(String)')`) and compare levels as numbers.

## Patterns

Replace `t<team_id>_<source>` with the names from `query_help`, and every `<...>` value with a real one.
The shapes below were run on ClickHouse 26.8 against a local table with the same `dt` and `raw` columns; they were not run against Better Stack.

### 1. Errors in the last 30 minutes for one service

```sql
SELECT
  dt,
  JSONExtract(raw, 'level', 'Nullable(String)') AS level,
  substring(JSONExtract(raw, 'message', 'Nullable(String)'), 1, 300) AS message,
  JSONExtract(raw, 'error', 'type', 'Nullable(String)') AS error_type,
  JSONExtract(raw, 'trace_id', 'Nullable(String)') AS trace_id
FROM remote(t<team_id>_<source>_logs)
WHERE dt > now() - INTERVAL 30 MINUTE
  AND JSONExtract(raw, 'level', 'Nullable(String)') IN ('error', 'fatal')
  AND JSONExtract(raw, 'service', 'Nullable(String)') = '<service>'
ORDER BY dt DESC
LIMIT 50
```

### 2. One request or trace

`<id_field>` is `request_id` for an id sent as `x-request-id`, and `trace_id` for a W3C `traceparent` or `x-correlation-id` derived id.

2a. Hot window, first; skip to 2b when the reported time is older than the hot window:

```sql
SELECT
  dt,
  JSONExtract(raw, 'service', 'Nullable(String)') AS service,
  JSONExtract(raw, 'level', 'Nullable(String)') AS level,
  JSONExtract(raw, 'event', 'Nullable(String)') AS event,
  substring(JSONExtract(raw, 'message', 'Nullable(String)'), 1, 300) AS message,
  JSONExtract(raw, 'http', 'status_code', 'Nullable(Int64)') AS status_code,
  JSONExtract(raw, 'trace_id', 'Nullable(String)') AS trace_id
FROM remote(t<team_id>_<source>_logs)
WHERE dt > now() - INTERVAL 30 MINUTE
  AND raw LIKE '%<id>%'
  AND JSONExtract(raw, '<id_field>', 'Nullable(String)') = '<id>'
ORDER BY dt ASC
LIMIT 200
```

2b. Archive, only when 2a returned nothing: call `query_windows` for a range around the reported time and run this once per window, with that window's bounds in UTC.

```sql
SELECT
  dt,
  JSONExtract(raw, 'service', 'Nullable(String)') AS service,
  JSONExtract(raw, 'level', 'Nullable(String)') AS level,
  JSONExtract(raw, 'event', 'Nullable(String)') AS event,
  substring(JSONExtract(raw, 'message', 'Nullable(String)'), 1, 300) AS message,
  JSONExtract(raw, 'http', 'status_code', 'Nullable(Int64)') AS status_code,
  JSONExtract(raw, 'trace_id', 'Nullable(String)') AS trace_id
FROM s3Cluster(primary, t<team_id>_<source>_s3)
WHERE _row_type = 1
  AND dt >= '<window_start>' AND dt < '<window_end>'
  AND raw LIKE '%<id>%'
  AND JSONExtract(raw, '<id_field>', 'Nullable(String)') = '<id>'
ORDER BY dt ASC
LIMIT 200
```

All services of an environment share its source, so one run covers a request that crosses services; also run it on any service that the registry gives its own source.
A `request_id` hit returns the `trace_id`; query that next to follow the same request into jobs it queued.

### 3. Count by level per minute

```sql
SELECT
  toStartOfMinute(dt) AS minute,
  JSONExtract(raw, 'level', 'Nullable(String)') AS level,
  count() AS lines
FROM remote(t<team_id>_<source>_logs)
WHERE dt > now() - INTERVAL 30 MINUTE
GROUP BY minute, level
ORDER BY minute ASC, level ASC
LIMIT 500
```

### 4. Top error messages over the last 3 hours

```sql
SELECT
  JSONExtract(raw, 'error', 'type', 'Nullable(String)') AS error_type,
  substring(JSONExtract(raw, 'message', 'Nullable(String)'), 1, 200) AS message,
  count() AS occurrences,
  max(dt) AS last_seen
FROM (
  SELECT dt, raw FROM remote(t<team_id>_<source>_logs)
  WHERE dt > now() - INTERVAL 3 HOUR
  UNION ALL
  SELECT dt, raw FROM s3Cluster(primary, t<team_id>_<source>_s3)
  WHERE _row_type = 1 AND dt > now() - INTERVAL 3 HOUR
)
WHERE JSONExtract(raw, 'level', 'Nullable(String)') IN ('error', 'fatal')
GROUP BY error_type, message
ORDER BY occurrences DESC
LIMIT 20
```

Grouping works only because the logging standard keeps ids out of `message`; when messages carry ids, group by `event` or `error_type` instead.

### 5. One tenant

```sql
SELECT
  dt,
  JSONExtract(raw, 'level', 'Nullable(String)') AS level,
  JSONExtract(raw, 'event', 'Nullable(String)') AS event,
  substring(JSONExtract(raw, 'message', 'Nullable(String)'), 1, 300) AS message,
  JSONExtract(raw, 'trace_id', 'Nullable(String)') AS trace_id
FROM remote(t<team_id>_<source>_logs)
WHERE dt > now() - INTERVAL 30 MINUTE
  AND raw LIKE '%<tenant_id>%'
  AND JSONExtract(raw, 'tenant_id', 'Nullable(String)') = '<tenant_id>'
  AND JSONExtract(raw, 'level', 'Nullable(String)') IN ('warn', 'error', 'fatal')
ORDER BY dt DESC
LIMIT 100
```

Use the project's declared tenant field name (for example `organization_id`) in place of `tenant_id`.

### 6. Slowest requests

```sql
SELECT
  dt,
  JSONExtract(raw, 'http', 'method', 'Nullable(String)') AS method,
  JSONExtract(raw, 'http', 'route', 'Nullable(String)') AS route,
  JSONExtract(raw, 'http', 'status_code', 'Nullable(Int64)') AS status_code,
  JSONExtract(raw, 'http', 'duration_ms', 'Nullable(Float64)') AS duration_ms,
  JSONExtract(raw, 'trace_id', 'Nullable(String)') AS trace_id
FROM remote(t<team_id>_<source>_logs)
WHERE dt > now() - INTERVAL 30 MINUTE
  AND JSONExtract(raw, 'http', 'duration_ms', 'Nullable(Float64)') IS NOT NULL
ORDER BY duration_ms DESC
LIMIT 20
```

For a latency trend rather than single slow calls, group by `route` with `quantile(0.95)(duration_ms)` over the same window, still with a `LIMIT`.

### Reading one full line

Only after a pattern above has narrowed the problem to one row, fetch its stack with `substring(JSONExtract(raw, 'error', 'stack', 'Nullable(String)'), 1, 2000)` and the same `dt` and id filters with `LIMIT 1`.
