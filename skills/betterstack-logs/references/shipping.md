# Shipping paths to Better Stack

Pick the path with the decision table in the skill's section 2, which also owns the shared-host, Collector and Docker socket rules; this file holds the mechanics of each path.
The app-side logger (fields, levels, redaction, transport, flush, versions) is owned by `logging-standard`: `references/pino-node.md` for long-running Node, `references/nextjs.md` for Next.js and serverless functions.
Every path reads the same two values per environment: `BETTER_STACK_SOURCE_TOKEN` and `BETTER_STACK_INGESTING_HOST`, both copied from the source page, never typed from memory.
The host is region-specific; always pass it explicitly, since the SDKs' built-in default endpoint is a legacy one.

## SDK: `@logtail/pino` and `@logtail/node`

- Install and wire them per `logging-standard` (`pino-node.md` for the two-target transport and tested versions, `nextjs.md` for `@logtail/node` with a flush per invocation).
- What Better Stack receives: `@logtail/pino` sends `time` as `dt`, maps the message key to `message`, turns the numeric level into its label, drops `v`, and copies every other field as is; observed in a local test against a fake ingest endpoint.
- `@logtail/node` adds `context.runtime` and `context.system` to every line (`captureStackContext`, on by default); set `captureStackContext: false` when those bytes are not wanted.
- Its burst protection drops logs above 10000 per 5 seconds and a full send queue drops more; a high-volume worker either raises those options or gets its own source (skill section 3).
- `@logtail/next` nests every field under `fields.*`, which breaks the contract the queries rely on; a project that keeps it for web vitals alone sets `BETTER_STACK_INGESTING_URL=https://<ingesting host>` (a full URL, which that package reads) next to the token.

## Vector container on a host shared with other teams

Only with the host owner's recorded approval (skill section 2).
Use `templates/vector-shared-host.yaml`: it reads only containers labelled with this project's compose project, merges the app's JSON to the top level, and maps pino's numeric level to the same labels `@logtail/pino` produces, so queries work the same on both paths.
The vendor setup script (`telemetry.betterstack.com/setup-vector/...`) generates a config with no container filter that ships every container on the host.

1. Copy the template to the repo, for example `ops/vector.yaml`.
2. Add a service to the project's compose file and give every service log rotation:

```yaml
x-logging: &default-logging
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"

services:
  # api, worker, ...: add `logging: *default-logging` to each

  log-shipper:
    image: timberio/vector:0.58.0-debian
    restart: unless-stopped
    command: ["--config", "/etc/vector/vector.yaml"]
    environment:
      VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION: "true"
      COMPOSE_PROJECT: ${COMPOSE_PROJECT_NAME:?}
      BETTER_STACK_INGESTING_HOST: ${BETTER_STACK_INGESTING_HOST:?set in the environment's env file}
      BETTER_STACK_SOURCE_TOKEN: ${BETTER_STACK_SOURCE_TOKEN:?set in the environment's env file}
    volumes:
      - ./ops/vector.yaml:/etc/vector/vector.yaml:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - vector-data:/var/lib/vector
    logging: *default-logging

volumes:
  vector-data:
```

- `${COMPOSE_PROJECT_NAME}` resolves to the `-p` value the compose command runs with (checked with `docker compose -p acme-staging config`), so each environment's stack ships only itself.
- Every service of the project ships to the one source in `BETTER_STACK_SOURCE_TOKEN`; the app logs `service`, and the template falls back to the compose service name.
- Vector 0.58 substitutes `${...}` in its config only when `VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true` is set; without it the sink fails validation with "invalid uri character".
- The app runs with neither Better Stack variable set, so it writes stdout only and Vector ships it once.
- Before deploying, validate locally: `docker run --rm -e VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true -e COMPOSE_PROJECT=<project> -e BETTER_STACK_INGESTING_HOST=example.invalid -e BETTER_STACK_SOURCE_TOKEN=dummy -v "$PWD/ops:/etc/vector:ro" timberio/vector:0.58.0-debian validate --no-environment /etc/vector/vector.yaml`.
- Keep a structural check in CI that the filter is still there: `grep -q 'com.docker.compose.project=' ops/vector.yaml`.
- Deploy and restart the shipper through `server-touch`, scoped to the project.

## Better Stack Collector (dedicated host or own cluster only)

- It bundles OpenTelemetry, Vector, an eBPF agent and Prometheus exporters, configured remotely from the Better Stack UI.
- It sees every container and process on the host, which is why section 2 of the skill limits it to dedicated hosts.
- Budget per host or node: 4 vCPU and 4 GiB with eBPF (the default), 2 vCPU and 2 GiB without, plus about 9 GB of disk buffers.
- Install: Docker Compose hosts run the official `install.sh` with `COLLECTOR_SECRET`; Kubernetes uses the `better-stack/collector` Helm chart.
  Read the exact commands and options from the Collector docs page at install time, since they change between releases.
- Required: normalize the source before using it.
  The Collector ships pino output as a string in `message` with numeric levels; add this VRL in the source's Configure, Transform settings, then check with `source_fields` that `level`, `service` and `trace_id` are top-level fields:

```vrl
if is_string(.message) {
  parsed, err = parse_json(string!(.message))
  if err == null && is_object(parsed) {
    app = object!(parsed)
    if !exists(app.message) && exists(app.msg) {
      app.message = del(app.msg)
    }
    . = merge(., app)
  }
}
if is_integer(.level) {
  n = int!(.level)
  .level = if n <= 10 { "trace" } else if n <= 20 { "debug" } else if n <= 30 { "info" } else if n <= 40 { "warn" } else if n <= 50 { "error" } else { "fatal" }
}
if exists(.time) {
  .dt = del(.time)
}
del(.v)
```

- Tested with `vector vrl` 0.58.0 on the Collector's Docker line shape (`dt`, `docker`, `platform`, the app line in `message`): pino JSON is merged to the top level with label levels, and plain text lines pass unchanged.
  It has not run inside Better Stack; check one line in the source's live tail for `_ingest.transform_error` after saving it.

## OpenTelemetry exporter

- For an app that already uses the OpenTelemetry SDK, point the OTLP exporter at the source with the standard variables:
  `OTEL_EXPORTER_OTLP_ENDPOINT=https://<ingesting host>` and `OTEL_EXPORTER_OTLP_HEADERS=Authorization=Bearer%20<source token>`, plus `OTEL_SERVICE_NAME`.
  The SDK appends `/v1/logs`; tested locally with `@opentelemetry/exporter-logs-otlp-http` 0.223.0, which sent `POST /v1/logs` with the bearer header.
- Better Stack documents `http/protobuf` and gRPC on port 443; whether it accepts the OTLP JSON that the `-otlp-http` JS exporter sends is unverified, so prefer the `-otlp-proto` exporter.
- An OpenTelemetry Collector uses the `otlphttp` exporter with `endpoint: https://<ingesting host>` and the same `Authorization` header.
- On a dedicated host running the Better Stack Collector, send OTLP to the collector instead (`http://localhost:4318`), enabled with `COLLECT_OTEL_HTTP_PORT` at install.

## Platform drains

- Vercel: the Better Stack integration in the Vercel marketplace adds a log drain (Vercel Pro or Enterprise), configured under the source's ingest settings with environments and a sampling rate.
  It carries Vercel's request and build logs into its own source per environment (`<project>-<env>-vercel`, skill section 3), never the SDK's source; app fields arrive only through the SDK (`@logtail/node`).
  Point each Vercel environment at its own drain source, so preview and production do not share one.
- Supabase (Pro or higher, paid per drain): create an HTTP source, then in Supabase add a log drain of type Custom endpoint with URL `https://<ingesting host>?source_token=<source token>`.
  Supabase logs do not follow the field contract; add a VRL transform on the Better Stack source that moves `timestamp` to `dt` and sets `level`, and read the exact field paths from `source_fields` once data arrives.
  Self-hosted Supabase drains are undocumented; on a VPS, ship its containers with the Vector template instead.
- A drain is configured in the platform's dashboard by the user; the agent records the source in the registry (`"shipping": "drain"` for Supabase, the service's `notes` for a Vercel drain).
