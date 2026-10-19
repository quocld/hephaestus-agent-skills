# Node: pino for APIs, workers and NestJS

The implementation of the `logging-standard` contract for long-running Node processes.
Serverless functions and Next.js use `nextjs.md` instead, because a pino worker transport loses lines when the platform freezes the process.

## Versions

This file owns the tested version set; other skills point here instead of repeating it.
Every block below ran as written on Node 22 with pino 10.3.1, pino-http 11.0.0, @logtail/pino 0.5.12, express 5.3.0, nestjs-pino 5.3.1 and @nestjs/core 11.2.7.

```bash
npm install --save-exact pino@10.3.1 pino-http@11.0.0 @logtail/pino@0.5.12
npm dedupe && npm ls pino   # must show one pino version; a nested copy under pino-http breaks the logger
```

- pino-http 11 requires pino 10: a project on pino 9 upgrades both together, and still runs the `npm dedupe` check above, because the upgrade can leave a nested pino under pino-http.
- Pin exact versions and upgrade on purpose, then rerun the tests below.
- Install `@logtail/pino` in every app that runs the logger, not only in a shared package: the transport target is a string resolved at runtime, so a missing dependency fails only in production with the token set.

## Plain JavaScript

The blocks are TypeScript; in a JavaScript project name the files `.js` and delete the type annotations, `interface` and `type` declarations, `type` imports and `as` casts.
Nothing else changes; the same code with only the types stripped passes the same tests.

## Files

Put these four files in `src/logging/` (or `src/` of a shared `packages/logger`), and import them everywhere; no service builds its own pino instance.
The wiring and tests below import them from that folder.

### events.ts

```ts
// src/logging/events.ts - every event name this service logs; adding or renaming one is a visible diff.
export const EVENT = {
  // Reserved: emitted by the files below.
  HTTP_REQUEST_COMPLETED: 'http.request.completed',
  HTTP_REQUEST_FAILED: 'http.request.failed',
  JOB_COMPLETED: 'job.completed',
  JOB_ATTEMPT_FAILED: 'job.attempt_failed',
  JOB_FAILED: 'job.failed',
  APP_STARTED: 'app.started',
  APP_STOPPING: 'app.stopping',
  APP_CRASHED: 'app.crashed',
  // The service's own events follow.
  INVOICE_VIEWED: 'invoice.viewed',
  INVOICE_ACCESS_DENIED: 'invoice.access.denied',
} as const;
```

### logger.ts

```ts
// src/logging/logger.ts - one logger for API, worker and scripts; the field contract lives in the logging-standard skill.
import { AsyncLocalStorage } from 'node:async_hooks';
import { randomBytes } from 'node:crypto';
import { pino, type DestinationStream, type Logger, type LoggerOptions } from 'pino';

export type { Logger } from 'pino';

/** Per-request or per-job context, injected into every line by the mixin. */
export interface LogContext {
  trace_id: string;
  request_id?: string;
  tenant_id?: string;
  user_id?: string;
  job?: { name: string; id: string; attempt: number };
  /** Set by setRequestOutcome; only the request's completion line reads it. */
  outcome?: { event: string; fields?: Record<string, unknown> };
  /** When the request entered the context (ms epoch), for a completion line pino-http never wrote; not logged. */
  started_at?: number;
}

const storage = new AsyncLocalStorage<LogContext>();

export function runWithLogContext<T>(ctx: LogContext, fn: () => T): T {
  return storage.run({ ...ctx }, fn);
}

export function getLogContext(): LogContext | undefined {
  return storage.getStore();
}

/** Call once auth resolves the caller; later lines in this request or job carry the ids. */
export function setLogContext(fields: Pick<LogContext, 'tenant_id' | 'user_id'>): void {
  const store = storage.getStore();
  if (store) Object.assign(store, fields);
}

/** 32 lowercase hex, the W3C trace-id shape, so it can later become a real OTel trace id. */
export function newTraceId(): string {
  return randomBytes(16).toString('hex');
}

export const DEFAULT_REDACT_PATHS = [
  'password', '*.password', 'token', '*.token',
  'access_token', '*.access_token', 'refresh_token', '*.refresh_token',
  'accessToken', '*.accessToken', 'refreshToken', '*.refreshToken',
  'api_key', '*.api_key', 'apiKey', '*.apiKey',
  'secret', '*.secret', 'client_secret', '*.client_secret',
  'authorization', '*.authorization', 'cookie', '*.cookie',
  'req.headers.authorization', 'req.headers.cookie', 'req.headers["x-api-key"]', 'res.headers["set-cookie"]',
  'email', '*.email', 'phone', '*.phone',
  'card', '*.card', 'card_number', '*.card_number', 'cardNumber', '*.cardNumber',
  'card_token', '*.card_token', 'cardToken', '*.cardToken', 'cvc', '*.cvc', 'cvv', '*.cvv',
];

export interface SerializedError {
  type: string;
  message: string;
  stack?: string;
  cause?: SerializedError;
}

/** Only these four keys: other properties can hold a request (body-parser keeps the raw body on `err.body`). */
export function serializeError(err: unknown, depth = 0): SerializedError {
  if (!(err instanceof Error)) return { type: 'NonError', message: String(err) };
  const out: SerializedError = { type: err.constructor.name || err.name, message: err.message, stack: err.stack };
  if (err.cause !== undefined && depth < 5) out.cause = serializeError(err.cause, depth + 1);
  return out;
}

/** Better Stack recommends records under 100 KiB; bigger lines are replaced by a summary, never dropped silently. */
export const MAX_LINE_BYTES = 100 * 1024;
const SUMMARY_KEYS = ['level', 'time', 'timestamp', 'message', 'service', 'env', 'version', 'trace_id', 'request_id', 'tenant_id', 'user_id', 'event'];

export function capLine(line: string): string {
  if (line.length * 3 < MAX_LINE_BYTES || Buffer.byteLength(line) <= MAX_LINE_BYTES) return line;
  const original = JSON.parse(line) as Record<string, unknown>;
  const summary: Record<string, unknown> = {};
  for (const key of SUMMARY_KEYS) if (key in original) summary[key] = original[key];
  if (typeof summary.message === 'string') summary.message = summary.message.slice(0, 1000);
  const error = original.error as { type?: unknown; message?: unknown } | undefined;
  if (error) summary.error = { type: error.type, message: String(error.message).slice(0, 1000) };
  summary.truncated = true;
  summary.original_bytes = Buffer.byteLength(line);
  return `${JSON.stringify(summary)}\n`;
}

function shippingTransport(level: string): LoggerOptions['transport'] {
  const sourceToken = process.env.BETTER_STACK_SOURCE_TOKEN;
  const host = process.env.BETTER_STACK_INGESTING_HOST;
  if (!sourceToken && !host) return undefined; // stdout only: a collector or Vector ships, or nothing does
  if (!sourceToken || !host) throw new Error('Set both BETTER_STACK_SOURCE_TOKEN and BETTER_STACK_INGESTING_HOST, or neither');
  const endpoint = /^https?:\/\//.test(host) ? host : `https://${host}`;
  return {
    targets: [
      { target: 'pino/file', options: { destination: 1 }, level },
      { target: '@logtail/pino', options: { sourceToken, options: { endpoint } }, level },
    ],
  };
}

export interface CreateLoggerOptions {
  /** The service name from logging-standard section 1, e.g. "api" or "worker". */
  service: string;
  level?: string;
  /** Project-specific paths, added to the defaults, never replacing them. */
  redact?: string[];
  /** Tests pass a stream to capture lines; production leaves it unset. */
  destination?: DestinationStream;
}

export function createLogger(opts: CreateLoggerOptions): Logger {
  const level = opts.level ?? process.env.LOG_LEVEL ?? 'info';
  const options: LoggerOptions = {
    level,
    messageKey: 'message',
    // `err`, not `error`: pino takes a missing message from obj[errorKey], and Nest (through nestjs-pino)
    // logs errors as `{ err }` with no message; the formatter below stores it under `error`.
    errorKey: 'err',
    base: { service: opts.service, env: process.env.APP_ENV ?? 'local', version: process.env.GIT_SHA ?? 'unknown' },
    // `timestamp` is the contract field; `time` (same value) is what @logtail/pino turns into Better Stack's `dt`.
    timestamp: () => {
      const iso = new Date().toISOString();
      return `,"timestamp":"${iso}","time":"${iso}"`;
    },
    serializers: { error: serializeError },
    redact: { paths: [...DEFAULT_REDACT_PATHS, ...(opts.redact ?? [])], censor: '[REDACTED]' },
    formatters: {
      // `log.error({ err }, ...)`, `log.error(new Error())` and Nest's `{ err }` all end up under `error`.
      log(object) {
        if (object.err !== undefined && object.error === undefined) {
          const { err, ...rest } = object;
          return { ...rest, error: err };
        }
        return object;
      },
    },
    mixin: () => {
      const store = storage.getStore();
      if (!store) return {};
      const { outcome, started_at, ...ctx } = store;
      return ctx;
    },
    hooks: { streamWrite: capLine },
  };
  if (opts.destination) return pino(options, opts.destination);
  const transport = shippingTransport(level);
  return transport ? pino({ ...options, transport }) : pino(options);
}

/** Keep `rate` of a high-volume success event; never use it for warn, error or audit events. */
export function sampled(rate: number): { sample_rate: number } | undefined {
  return Math.random() < rate ? { sample_rate: rate } : undefined;
}
```

What it guarantees:

- `level` stays numeric in the process (`logging-standard` section 1 says why).
- Shipping is decided by the environment: both `BETTER_STACK_*` variables set means stdout plus Better Stack, neither means stdout only (for Vector or a collector), one alone fails at startup.
  Which variables each environment gets is set up in `betterstack-logs` section 3.
- Context fields come only from the mixin; never bind `trace_id`, `request_id`, `tenant_id` or `user_id` with `logger.child()`, because pino then writes the key twice in one line.
- An error is serialized to `type`, `message`, `stack` and `cause` only; pino's own `errWithCause` copies every other property too, so do not switch back to it.
- stdout is written asynchronously (and by a worker thread when shipping), so lines from pino and `console.log` can interleave out of order; read order from `timestamp`, and capture lines in tests through `destination`, which is synchronous, never by parsing stdout.
- For local reading, pipe stdout through `npx pino-pretty`; do not add a pretty transport to the code.

### http.ts

```ts
// src/logging/http.ts - correlation middleware and the pino-http options shared by Express and nestjs-pino.
import { randomUUID } from 'node:crypto';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Options as PinoHttpOptions } from 'pino-http';
import { EVENT } from './events.js';
import { getLogContext, newTraceId, runWithLogContext, type Logger } from './logger.js';

const TRACEPARENT = /^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$/;
const SAFE_ID = /^[A-Za-z0-9._:-]{1,128}$/;
export const HEALTH_PATHS = new Set(['/health', '/healthz', '/readyz', '/livez']);

/** Any id read from a header, path or query before it goes on a line: the expected shape or nothing. */
export function safeId(value: unknown): string | undefined {
  return typeof value === 'string' && SAFE_ID.test(value) ? value : undefined;
}

function header(req: IncomingMessage, name: string): string | undefined {
  const value = req.headers[name];
  return Array.isArray(value) ? value[0] : value;
}

/** Inbound ids are attacker-controlled: accept only the expected shape, otherwise start fresh. */
export function traceIdFrom(req: IncomingMessage): string {
  const match = TRACEPARENT.exec(header(req, 'traceparent') ?? '');
  if (match && !/^0+$/.test(match[1])) return match[1];
  return safeId(header(req, 'x-correlation-id')) ?? newTraceId();
}

export function requestIdFrom(req: IncomingMessage): string {
  return safeId(header(req, 'x-request-id')) ?? randomUUID();
}

/** Register before any other middleware so every later line, including pino-http's, carries the ids. */
export function correlationMiddleware(req: IncomingMessage & { id?: unknown }, res: ServerResponse, next: () => void): void {
  const request_id = requestIdFrom(req);
  req.id = request_id;
  res.setHeader('x-request-id', request_id);
  runWithLogContext({ trace_id: traceIdFrom(req), request_id, started_at: Date.now() }, next);
}

/** Headers to send on calls to our own services, so their lines join the same trace. */
export function correlationHeaders(): Record<string, string> {
  const ctx = getLogContext();
  return ctx ? { 'x-correlation-id': ctx.trace_id } : {};
}

/** Name an expected outcome (validation failed, access denied) on the completion line instead of logging a second line. */
export function setRequestOutcome(event: string, fields?: Record<string, unknown>): void {
  const store = getLogContext();
  if (store) store.outcome = { event, fields };
}

type Req = IncomingMessage & { id?: unknown; originalUrl?: string; baseUrl?: string; route?: { path?: unknown } };

function route(req: Req): string {
  // The route template (/invoices/:id), never the raw URL: low cardinality and no ids or tokens from the query string.
  // Nest mounts middleware as wildcard routes, so a request that reached no controller (404, rejected body) still
  // carries one; a wildcard counts as unmatched, like no route at all.
  const path = req.route?.path;
  return typeof path === 'string' && !path.includes('*') ? `${req.baseUrl ?? ''}${path}` || '/' : 'unmatched';
}

function http(req: Req, res: ServerResponse, durationMs: number) {
  return { method: req.method, route: route(req), status_code: res.statusCode, duration_ms: durationMs };
}

export function httpLoggerOptions(logger: Logger): PinoHttpOptions {
  return {
    logger,
    genReqId: (req) => (req as Req).id as string ?? randomUUID(),
    customLogLevel: (_req, res, err) => (err || res.statusCode >= 500 ? 'error' : res.statusCode >= 400 ? 'warn' : 'info'),
    autoLogging: { ignore: (req) => HEALTH_PATHS.has(((req as Req).originalUrl ?? req.url ?? '').split('?')[0]) },
    // No req/res dumps (headers, cookies, query strings) on any line; the completion line carries `http` instead.
    quietResLogger: true,
    serializers: { req: () => undefined, res: () => undefined },
    customSuccessMessage: () => 'request completed',
    customErrorMessage: () => 'request failed',
    customSuccessObject: (req, res, val) => {
      const outcome = getLogContext()?.outcome;
      return { ...outcome?.fields, event: outcome?.event ?? EVENT.HTTP_REQUEST_COMPLETED, request_id: (req as Req).id, http: http(req as Req, res, val.responseTime) };
    },
    customErrorObject: (req, res, error, val) =>
      ({ event: EVENT.HTTP_REQUEST_FAILED, request_id: (req as Req).id, http: http(req as Req, res, val.responseTime), error }),
  };
}

/** The 4xx status an error asks for (body-parser, http-errors), or undefined for a server error. */
export function clientErrorStatus(err: unknown): number | undefined {
  const e = err as { status?: unknown; statusCode?: unknown } | null;
  const status = Number(e?.status ?? e?.statusCode);
  return status >= 400 && status < 500 ? status : undefined;
}

/**
 * An expected client error: a 4xx that http-errors marks `expose: true` (`createError(404)`, body-parser's 400/413,
 * whose message and `body` can quote the raw request). Its warn completion line is the whole story.
 * An SDK error that carries a 4xx status without `expose` (a rotated Stripe key, a rate limit) is not one: it keeps
 * its error and stack, so a broken integration does not look like client noise.
 */
export function isExpectedClientError(err: unknown): boolean {
  return clientErrorStatus(err) !== undefined && (err as { expose?: unknown } | null)?.expose === true;
}

/**
 * Express error handler, registered last.
 * The completion line logs every error once; an expected client error is logged at warn without the error object.
 */
export function errorHandler(err: Error, _req: unknown, res: ServerResponse & { err?: Error; headersSent: boolean }, next: (e: Error) => void): void {
  if (res.headersSent) return next(err);
  const status = clientErrorStatus(err);
  if (!isExpectedClientError(err)) res.err = err;
  res.statusCode = status ?? 500;
  res.setHeader('content-type', 'application/json');
  res.end(JSON.stringify({ error: status === undefined ? 'internal_error' : 'invalid_request' }));
}

/**
 * Write the completion line for a request pino-http never saw, and return whether it did.
 * Frameworks that parse the body before pino-http is attached (Nest with its own parser) would otherwise leave a
 * rejected body with no line at all; an exception filter calls this.
 */
export function logCompletionIfMissing(logger: Logger, req: IncomingMessage, res: ServerResponse & { log?: unknown }, error?: unknown): boolean {
  if (res.log !== undefined) return false;
  const startedAt = getLogContext()?.started_at;
  const fields = { request_id: (req as Req).id, http: http(req as Req, res, startedAt === undefined ? 0 : Date.now() - startedAt) };
  if (res.statusCode >= 500) logger.error({ ...fields, event: EVENT.HTTP_REQUEST_FAILED, err: error }, 'request failed');
  else logger.warn({ ...fields, event: EVENT.HTTP_REQUEST_COMPLETED }, 'request completed');
  return true;
}
```

- The completion line is the request's only automatic line: no `req`/`res` dump, so headers, cookies and query strings never reach the sink.
- The route is the template (`/invoices/:id`), read after routing; a request that matched no route, or only a middleware wildcard, logs `unmatched`.
- `setRequestOutcome` replaces the completion line's `event` and adds its fields, so an expected 4xx is one `warn` line; select all completion lines by the `http` field, not by event.
- Health paths are silent; add the project's own probe paths to `HEALTH_PATHS`.

### worker.ts

```ts
// src/logging/worker.ts - carry the request's ids into jobs and log each job attempt once.
import { EVENT } from './events.js';
import { getLogContext, newTraceId, runWithLogContext, type Logger } from './logger.js';

/** Put this in the job payload when enqueuing, next to the business data. */
export interface JobLogMeta {
  trace_id?: string;
  request_id?: string;
  tenant_id?: string;
  user_id?: string;
}

export function jobLogMeta(): JobLogMeta {
  const { trace_id, request_id, tenant_id, user_id } = getLogContext() ?? {};
  return { trace_id, request_id, tenant_id, user_id };
}

export interface JobRun {
  name: string;
  id: string;
  attempt: number;
  maxAttempts: number;
  meta?: JobLogMeta;
}

/**
 * Run one attempt inside the enqueuing request's context.
 * This wrapper is the boundary that logs a failure; it rethrows only so the queue can schedule a retry,
 * and the queue must not log the same error again.
 */
export async function runJob<T>(logger: Logger, job: JobRun, fn: () => Promise<T>): Promise<T> {
  const ctx = { ...job.meta, trace_id: job.meta?.trace_id ?? newTraceId(), job: { name: job.name, id: job.id, attempt: job.attempt } };
  return runWithLogContext(ctx, async () => {
    const started = Date.now();
    try {
      const result = await fn();
      logger.info({ event: EVENT.JOB_COMPLETED, duration_ms: Date.now() - started }, 'job completed');
      return result;
    } catch (error) {
      const final = job.attempt >= job.maxAttempts;
      logger[final ? 'error' : 'warn'](
        { event: final ? EVENT.JOB_FAILED : EVENT.JOB_ATTEMPT_FAILED, duration_ms: Date.now() - started, error },
        final ? 'job failed' : 'job attempt failed, will retry',
      );
      throw error;
    }
  });
}
```

## Express wiring

```ts
// src/main.ts - Express wiring order: correlation, then pino-http, body parsers and routes, error handler last.
import express from 'express';
import { pinoHttp } from 'pino-http';
import { EVENT } from './logging/events.js';
import { correlationMiddleware, errorHandler, httpLoggerOptions, setRequestOutcome } from './logging/http.js';
import { createLogger, setLogContext } from './logging/logger.js';

const logger = createLogger({ service: 'api' });
const app = express();
app.use(correlationMiddleware);
app.use(pinoHttp(httpLoggerOptions(logger)));
app.use(express.json()); // after pino-http, so a malformed body still gets its completion line

app.get('/health', (_req, res) => { res.send('ok'); });
app.get('/invoices/:id', (req, res) => {
  setLogContext({ tenant_id: 'org_42', user_id: 'usr_7' }); // normally done by the auth guard
  if (req.params.id.startsWith('other_')) {
    setRequestOutcome(EVENT.INVOICE_ACCESS_DENIED, { invoice_id: req.params.id });
    res.status(403).json({ error: 'forbidden' });
    return;
  }
  logger.info({ event: EVENT.INVOICE_VIEWED, invoice_id: req.params.id }, 'invoice viewed');
  res.json({ id: req.params.id });
});
app.use(errorHandler);

const server = app.listen(Number(process.env.PORT ?? 3000), () => logger.info({ event: EVENT.APP_STARTED }, 'listening'));

// Stop accepting work, then exit through process.exit so pino's exit hook flushes the transport worker.
function shutdown(signal: string): void {
  logger.info({ event: EVENT.APP_STOPPING, signal }, 'shutting down');
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10_000).unref();
}
process.once('SIGTERM', () => shutdown('SIGTERM'));
process.once('SIGINT', () => shutdown('SIGINT'));
// Nothing else catches these: log fatal once, then exit so the orchestrator restarts a clean process.
process.on('uncaughtException', (error) => { logger.fatal({ event: EVENT.APP_CRASHED, error }, 'uncaught exception'); process.exit(1); });
process.on('unhandledRejection', (error) => { logger.fatal({ event: EVENT.APP_CRASHED, error }, 'unhandled rejection'); process.exit(1); });
```

Order matters: `correlationMiddleware` first, `pinoHttp` second, body parsers and routes next, `errorHandler` last.
Log in handlers with the shared `logger`, not `req.log`; the context fields arrive through the mixin either way.

## NestJS wiring (nestjs-pino)

```ts
// src/app.module.ts
import { Controller, Get, HttpException, HttpStatus, Logger, type MiddlewareConsumer, Module, type NestModule, type OnApplicationShutdown, Param, Post } from '@nestjs/common';
import express from 'express';
import { LoggerModule } from 'nestjs-pino';
import { EVENT } from './logging/events.js';
import { httpLoggerOptions } from './logging/http.js';
import { createLogger, setLogContext } from './logging/logger.js';

@Controller()
class InvoicesController {
  private readonly log = new Logger(InvoicesController.name);

  @Get('health')
  health() { return 'ok'; }

  @Get('invoices/:id')
  get(@Param('id') id: string) {
    setLogContext({ tenant_id: 'org_42', user_id: 'usr_7' }); // normally done by the auth guard
    this.log.log({ event: EVENT.INVOICE_VIEWED, invoice_id: id }, 'invoice viewed');
    return { id };
  }

  @Get('forbidden')
  forbidden() { throw new HttpException('not yours', HttpStatus.FORBIDDEN); }

  @Post('fail')
  fail() { throw new Error('charge failed', { cause: new Error('card_declined') }); }
}

@Module({
  // forRoot in the root module only; a second registration logs every request twice.
  imports: [LoggerModule.forRoot({ pinoHttp: httpLoggerOptions(createLogger({ service: 'api' })) })],
  controllers: [InvoicesController],
})
export class AppModule implements NestModule, OnApplicationShutdown {
  // The body parser runs after nestjs-pino's middleware, so a malformed or oversized body still gets its completion line.
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(express.json()).forRoutes('*path');
  }

  onApplicationShutdown(signal?: string) {
    new Logger('App').log({ event: EVENT.APP_STOPPING, signal }, 'shutting down');
  }
}
```

```ts
// src/log-once.filter.ts - answer exactly like Nest's default filter, but never log: pino-http's completion line logs each request once.
import type { IncomingMessage, ServerResponse } from 'node:http';
import { type ArgumentsHost, Catch, HttpException, HttpStatus } from '@nestjs/common';
import { BaseExceptionFilter } from '@nestjs/core';
import { PinoLogger } from 'nestjs-pino';
import { isExpectedClientError, logCompletionIfMissing } from './logging/http.js';

@Catch()
export class LogOnceExceptionFilter extends BaseExceptionFilter {
  override catch(exception: unknown, host: ArgumentsHost): void {
    const http = host.switchToHttp();
    const req = http.getRequest<IncomingMessage>();
    const res = http.getResponse<ServerResponse & { err?: Error; log?: unknown }>();
    if (exception instanceof HttpException) {
      super.catch(exception, host); // Nest's own response; Nest does not log HttpExceptions
      logCompletionIfMissing(PinoLogger.root, req, res); // a body Nest's parser rejected, before pino-http was attached
      return;
    }
    const adapter = this.applicationRef ?? this.httpAdapterHost?.httpAdapter;
    if (!adapter) throw exception;
    // Same status and body as BaseExceptionFilter.handleUnknownError, without its logger.error call.
    const body = this.isHttpError(exception)
      ? { statusCode: exception.statusCode, message: exception.message }
      : { statusCode: HttpStatus.INTERNAL_SERVER_ERROR, message: 'Internal server error' };
    const keepError = !isExpectedClientError(exception); // an exposed 4xx (body-parser, http-errors) is the client's
    if (keepError) res.err = exception instanceof Error ? exception : new Error(String(exception));
    if (adapter.isHeadersSent(res)) adapter.end(res);
    else adapter.reply(res, body, body.statusCode);
    logCompletionIfMissing(PinoLogger.root, req, res, keepError ? exception : undefined);
  }
}
```

```ts
// src/main.ts
import 'reflect-metadata';
import { HttpAdapterHost, NestFactory } from '@nestjs/core';
import { Logger } from 'nestjs-pino';
import { AppModule } from './app.module.js';
import { LogOnceExceptionFilter } from './log-once.filter.js';
import { correlationMiddleware } from './logging/http.js';

async function bootstrap() {
  const app = await NestFactory.create(AppModule, { bufferLogs: true, bodyParser: false }); // AppModule mounts the parser
  app.useLogger(app.get(Logger));
  app.use(correlationMiddleware); // before nestjs-pino's middleware, which Nest mounts during init
  app.useGlobalFilters(new LogOnceExceptionFilter(app.get(HttpAdapterHost).httpAdapter));
  // process.exit after the hooks fires pino's exit flush; the default re-raises the signal and loses the last lines.
  app.enableShutdownHooks(undefined, { useProcessExit: true });
  await app.listen(Number(process.env.PORT ?? 3000));
}
void bootstrap();
```

- `app.use(correlationMiddleware)` runs before nestjs-pino's middleware because Nest mounts module middleware during `listen()`.
- Nest's default exception filter logs every exception that is not an `HttpException` (with no message, since it passes only `{ err }`), so with pino-http that is two error lines per 500; `LogOnceExceptionFilter` keeps it to the completion line and answers with exactly Nest's statuses and bodies.
- An app that needs Nest's own body parser (for example `rawBody: true` to verify webhook signatures) keeps it: no `bodyParser: false` and no `consumer.apply(express.json())`; Nest then turns a rejected body into a `BadRequestException` before pino-http is attached, and the filter's `logCompletionIfMissing` call writes that request's one warn line.
  Switching an app between the two parser setups touches webhook signature checks: prove a signed webhook still verifies, and run `flow-trace` if it does not.
- With a global prefix, add the prefixed probe paths (`/api/health`) to `HEALTH_PATHS`.
- A request that reached no controller logs `route: "unmatched"`.
- Auth guards call `setLogContext({ tenant_id, user_id })` once the caller is known; a controller or guard names an expected 4xx with `setRequestOutcome` before throwing its `HttpException`.
- Without `useProcessExit: true` (needs @nestjs/core 11.1.10 or newer), Nest re-raises the signal after its hooks and the last lines are lost from stdout and from Better Stack; this was reproduced, not assumed.
  On an older Nest, upgrade, or handle SIGTERM yourself: `await app.close()`, then `process.exit(0)`.

## Workers and queues

When enqueuing, put `log: jobLogMeta()` in the job payload next to the business data.
In the processor, wrap the handler:

```ts
await runJob(logger, { name: job.name, id: String(job.id), attempt, maxAttempts, meta: job.data.log }, () => handle(job.data));
```

`attempt` is 1-based; read it from the queue library's job object in the installed version (BullMQ's counters differ between versions, so check its `Job` type rather than guessing).
A scheduled job with no enqueuing request gets a fresh `trace_id` per run from `runJob`.
Work with no queue to retry it (fire-and-forget after a response, an in-process timer) runs with `attempt: 1, maxAttempts: 1` and ends in `.catch(() => {})`, because `runJob` already logged the failure as `job.failed`:

```ts
void runJob(logger, { name: 'receipt.email', id: invoiceId, attempt: 1, maxAttempts: 1, meta: jobLogMeta() }, () => sendReceipt(invoiceId)).catch(() => {});
```

## Shutdown and flush

- Handle `SIGTERM` and `SIGINT`, stop accepting work, then leave through `process.exit()`: pino flushes the transport worker on the `exit` event, and a process killed by the default signal action never emits it.
- Check this with plain `node`, not `tsx` or `ts-node-dev`: `tsx` relays signals in a way that hid the loss in testing.
- `uncaughtException` and `unhandledRejection` log `fatal` once and exit with code 1.

## Tests

```ts
// test/logging.test.ts - run with: node --import tsx --test test/logging.test.ts
import assert from 'node:assert/strict';
import type { AddressInfo } from 'node:net';
import { test } from 'node:test';
import express from 'express';
import { pinoHttp } from 'pino-http';
import { correlationMiddleware, errorHandler, httpLoggerOptions, setRequestOutcome } from '../src/logging/http.js';
import { createLogger, MAX_LINE_BYTES, setLogContext } from '../src/logging/logger.js';
import { jobLogMeta, runJob } from '../src/logging/worker.js';

function capture() {
  const lines: Record<string, any>[] = [];
  const destination = { write: (s: string) => { lines.push(JSON.parse(s)); } };
  return { lines, logger: createLogger({ service: 'api', destination }) };
}

async function serve(app: express.Express, fn: (base: string) => Promise<void>) {
  const server = app.listen(0);
  try {
    await fn(`http://127.0.0.1:${(server.address() as AddressInfo).port}`);
  } finally {
    server.close();
  }
}

test('every line carries the contract fields and secrets never reach the sink', async () => {
  const { lines, logger } = capture();
  const app = express();
  app.use(correlationMiddleware);
  app.use(pinoHttp(httpLoggerOptions(logger)));
  app.get('/health', (_req, res) => { res.send('ok'); });
  app.post('/login', (req, res) => {
    setLogContext({ tenant_id: 'org_1', user_id: 'usr_1' });
    // The mistake the redaction guards against: logging an object that holds credentials.
    logger.info({ event: 'auth.login.attempted', body: { password: 'hunter2-secret' }, headers: { authorization: 'Bearer leaked-token' } }, 'login attempted');
    res.status(401).end();
  });

  await serve(app, async (base) => {
    await fetch(`${base}/health`);
    const res = await fetch(`${base}/login`, { method: 'POST', headers: { 'x-request-id': 'req-abc', authorization: 'Bearer leaked-token' } });
    assert.equal(res.headers.get('x-request-id'), 'req-abc');
  });
  await new Promise((r) => setTimeout(r, 50));

  const raw = JSON.stringify(lines);
  assert.ok(!raw.includes('hunter2-secret'), 'password leaked');
  assert.ok(!raw.includes('leaked-token'), 'token leaked');
  assert.ok(raw.includes('[REDACTED]'), 'redaction marker missing');
  assert.ok(!lines.some((l) => l.http?.route === '/health'), 'health check logged');

  const completed = lines.find((l) => l.event === 'http.request.completed');
  assert.ok(completed, 'no completion line');
  for (const field of ['timestamp', 'time', 'message', 'service', 'env', 'version', 'trace_id', 'request_id']) {
    assert.equal(typeof completed[field], 'string', `missing ${field}`);
  }
  assert.equal(completed.level, 40); // 401 -> warn
  assert.equal(completed.request_id, 'req-abc');
  assert.equal(completed.tenant_id, 'org_1');
  assert.deepEqual(Object.keys(completed.http).sort(), ['duration_ms', 'method', 'route', 'status_code']);
  assert.equal(completed.req, undefined, 'request dump on the line');
});

test('an unhandled error is logged once, with its cause chain and nothing else', async () => {
  const { lines, logger } = capture();
  const app = express();
  app.use(correlationMiddleware);
  app.use(pinoHttp(httpLoggerOptions(logger)));
  app.get('/fail', () => {
    throw Object.assign(new Error('charge failed', { cause: new Error('card_declined') }), { config: { headers: { 'x-api-key': 'sk_live_leak' } } });
  });
  app.use(errorHandler);
  await serve(app, async (base) => { await fetch(`${base}/fail`); });
  await new Promise((r) => setTimeout(r, 50));

  const errors = lines.filter((l) => l.level >= 50);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].error.message, 'charge failed');
  assert.equal(errors[0].error.cause.message, 'card_declined');
  assert.match(errors[0].error.stack, /charge failed/);
  assert.deepEqual(Object.keys(errors[0].error).sort(), ['cause', 'message', 'stack', 'type']);
});

test('a malformed body is a 400 at warn, and neither the body nor the parser error reaches the sink', async () => {
  const { lines, logger } = capture();
  const app = express();
  app.use(correlationMiddleware);
  app.use(pinoHttp(httpLoggerOptions(logger)));
  app.use(express.json());
  app.post('/pay', (_req, res) => { res.end(); });
  app.use(errorHandler);
  let status = 0;
  await serve(app, async (base) => {
    const body = '{"cardToken":"tok_live_4242","email":"jane@example.com",'; // invalid JSON; body-parser keeps it on err.body
    status = (await fetch(`${base}/pay`, { method: 'POST', headers: { 'content-type': 'application/json' }, body })).status;
  });
  await new Promise((r) => setTimeout(r, 50));

  assert.equal(status, 400);
  const raw = JSON.stringify(lines);
  assert.ok(!raw.includes('tok_live_4242') && !raw.includes('jane@example.com'), 'request body leaked');
  assert.equal(lines.length, 1);
  assert.equal(lines[0].level, 40);
  assert.equal(lines[0].http.status_code, 400);
});

test('an expected 4xx is one warn line named by the handler', async () => {
  const { lines, logger } = capture();
  const app = express();
  app.use(correlationMiddleware);
  app.use(pinoHttp(httpLoggerOptions(logger)));
  app.post('/invoices/:id/pay', (req, res) => {
    setRequestOutcome('invoice.payment.rejected', { invoice_id: req.params.id, reason: 'card_declined' });
    res.status(402).json({ error: 'card_declined' });
  });
  await serve(app, async (base) => { await fetch(`${base}/invoices/inv_1/pay`, { method: 'POST' }); });
  await new Promise((r) => setTimeout(r, 50));

  assert.equal(lines.length, 1);
  assert.equal(lines[0].level, 40);
  assert.equal(lines[0].event, 'invoice.payment.rejected');
  assert.equal(lines[0].reason, 'card_declined');
  assert.equal(lines[0].http.route, '/invoices/:id/pay');
  assert.equal(lines[0].outcome, undefined, 'outcome leaked into the context fields');
});

test('jobs inherit the enqueuing request ids', async () => {
  const { lines, logger } = capture();
  const app = express();
  app.use(correlationMiddleware);
  let meta = {};
  app.get('/enqueue', (_req, res) => { setLogContext({ tenant_id: 'org_9' }); meta = jobLogMeta(); res.end(); });
  await serve(app, async (base) => { await fetch(`${base}/enqueue`, { headers: { 'x-request-id': 'req-job' } }); });

  await runJob(logger, { name: 'invoice.send', id: 'job_1', attempt: 1, maxAttempts: 3, meta }, async () => {
    logger.info({ event: 'invoice.sent' }, 'invoice sent');
  });
  await assert.rejects(runJob(logger, { name: 'invoice.send', id: 'job_2', attempt: 3, maxAttempts: 3, meta }, async () => {
    throw new Error('smtp timeout');
  }));

  const sent = lines.find((l) => l.event === 'invoice.sent');
  assert.equal(sent?.request_id, 'req-job');
  assert.equal(sent?.tenant_id, 'org_9');
  assert.deepEqual(sent?.job, { name: 'invoice.send', id: 'job_1', attempt: 1 });
  assert.equal(lines.find((l) => l.event === 'job.failed')?.level, 50);
});

test('an oversized line is replaced by a summary, not shipped whole', () => {
  const { lines, logger } = capture();
  logger.info({ event: 'report.built', blob: 'x'.repeat(MAX_LINE_BYTES * 2) }, 'report built');
  assert.equal(lines[0].truncated, true);
  assert.equal(lines[0].event, 'report.built');
  assert.equal(lines[0].blob, undefined);
});

test('an SDK 4xx keeps its error, an expected 4xx stays warn without it, an unknown path is unmatched', async () => {
  const { lines, logger } = capture();
  const app = express();
  app.use(correlationMiddleware);
  app.use(pinoHttp(httpLoggerOptions(logger)));
  app.get('/sync', () => {
    throw Object.assign(new Error('Invalid API Key provided'), { statusCode: 401, type: 'StripeAuthenticationError' });
  });
  app.get('/missing', () => {
    throw Object.assign(new Error('Not Found'), { status: 404, statusCode: 404, expose: true }); // what http-errors' createError(404) builds
  });
  app.use(errorHandler);
  await serve(app, async (base) => {
    await fetch(`${base}/sync`);
    await fetch(`${base}/missing`);
    await fetch(`${base}/no-such-route`);
  });
  await new Promise((r) => setTimeout(r, 50));

  const sync = lines.find((l) => l.http?.route === '/sync');
  assert.equal(sync?.http.status_code, 401);
  assert.equal(sync?.error?.message, 'Invalid API Key provided');
  assert.match(sync?.error?.stack ?? '', /Invalid API Key/);
  const missing = lines.find((l) => l.http?.route === '/missing');
  assert.equal(missing?.level, 40, 'an expected 4xx is warn');
  assert.equal(missing?.error, undefined, 'an expected 4xx carries no error');
  const unknown = lines.find((l) => l.http?.status_code === 404 && l.http.route === 'unmatched');
  assert.ok(unknown, 'unknown path not logged as unmatched');
});
```

```ts
// test/nest-logging.test.ts - run with: node --import tsx --test test/nest-logging.test.ts
// The tsconfig that covers test/ needs experimentalDecorators, or tsx rejects the parameter decorators.
// Through the real Nest + nestjs-pino stack with Nest's own body parser (the rawBody case), not a stand-in.
import 'reflect-metadata';
import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { Body, Controller, ForbiddenException, Get, Logger as NestLogger, Module, Post } from '@nestjs/common';
import { HttpAdapterHost, NestFactory } from '@nestjs/core';
import { Logger, LoggerModule } from 'nestjs-pino';
import { LogOnceExceptionFilter } from '../src/log-once.filter.js';
import { correlationMiddleware, httpLoggerOptions } from '../src/logging/http.js';
import { createLogger } from '../src/logging/logger.js';

const lines: Record<string, any>[] = [];
const logger = createLogger({ service: 'api', destination: { write: (s: string) => { lines.push(JSON.parse(s)); } } });

@Controller()
class ProbeController {
  @Get('boom') boom() { throw Object.assign(new Error('charge failed', { cause: new Error('card_declined') }), { config: { headers: { 'x-api-key': 'sk_live_leak' } } }); }
  @Get('forbidden') forbidden() { throw new ForbiddenException('Wrong workspace'); }
  @Get('sync') sync() { throw Object.assign(new Error('Invalid API Key provided'), { statusCode: 401 }); }
  @Post('pay') pay(@Body() _body: unknown) { return { ok: true }; }
}

@Module({ imports: [LoggerModule.forRoot({ pinoHttp: httpLoggerOptions(logger) })], controllers: [ProbeController] })
class ProbeModule {}

let base = '';
let close = async () => {};
before(async () => {
  const app = await NestFactory.create(ProbeModule, { bufferLogs: true, rawBody: true }); // Nest's own parser stays
  app.useLogger(app.get(Logger));
  app.use(correlationMiddleware);
  app.useGlobalFilters(new LogOnceExceptionFilter(app.get(HttpAdapterHost).httpAdapter));
  await app.listen(0, '127.0.0.1');
  base = await app.getUrl();
  close = () => app.close();
});
after(() => close());

async function call(path: string, init?: RequestInit) {
  const from = lines.length;
  const res = await fetch(base + path, init);
  const body = await res.json().catch(() => undefined);
  await new Promise((r) => setTimeout(r, 50));
  return { status: res.status, body, out: lines.slice(from) };
}

test('a 500 is one error line with a message and the real error, answered like Nest', async () => {
  const { status, body, out } = await call('/boom');
  assert.equal(status, 500);
  assert.deepEqual(body, { statusCode: 500, message: 'Internal server error' });
  const errors = out.filter((l) => l.level >= 50);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].message, 'request failed');
  assert.equal(errors[0].error.cause.message, 'card_declined');
  assert.deepEqual(Object.keys(errors[0].error).sort(), ['cause', 'message', 'stack', 'type']);
  assert.ok(!JSON.stringify(out).includes('sk_live_leak'), 'extra error property leaked');
});

test('an HttpException is one warn line with Nest\'s response', async () => {
  const { status, body, out } = await call('/forbidden');
  assert.equal(status, 403);
  assert.equal((body as { message: string }).message, 'Wrong workspace');
  assert.equal(out.length, 1);
  assert.equal(out[0].level, 40);
});

test('an SDK 4xx keeps its error', async () => {
  const { status, out } = await call('/sync');
  assert.equal(status, 401);
  assert.equal(out.length, 1);
  assert.equal(out[0].error?.message, 'Invalid API Key provided');
  assert.match(out[0].error?.stack ?? '', /Invalid API Key/);
});

test('a body Nest\'s parser rejects still gets one warn line, without the body', async () => {
  const body = '{"cardToken":"tok_live_4242","email":"jane@example.com",';
  const { status, out } = await call('/pay', { method: 'POST', headers: { 'content-type': 'application/json' }, body });
  assert.equal(status, 400);
  assert.equal(out.length, 1);
  assert.equal(out[0].level, 40);
  assert.equal(out[0].http.route, 'unmatched');
  const raw = JSON.stringify(out);
  assert.ok(!raw.includes('tok_live_4242') && !raw.includes('jane@example.com'), 'request body leaked');
});

test('a request that reached no controller logs as unmatched, not the middleware wildcard', async () => {
  const { status, out } = await call('/no-such-route');
  assert.equal(status, 404);
  assert.equal(out.length, 1);
  assert.equal(out[0].http.route, 'unmatched');
});

test('an error logged through the Nest Logger gets a message', async () => {
  const from = lines.length;
  new NestLogger('Sync').error(new Error('sync failed'));
  await new Promise((r) => setTimeout(r, 20));
  const line = lines.slice(from).find((l) => l.level >= 50);
  assert.equal(line?.message, 'sync failed');
});
```

```ts
// test/logging-wiring.test.ts - the tests above build their own app; this pins that the real one registers the same pieces.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

test('main.ts and the root module mount the logging pieces', () => {
  const main = readFileSync(new URL('../src/main.ts', import.meta.url), 'utf8');
  assert.match(main, /app\.use\(correlationMiddleware\)/);
  assert.match(main, /app\.useGlobalFilters\(new LogOnceExceptionFilter\(/);
  assert.match(main, /app\.useLogger\(app\.get\(Logger\)\)/);
  const root = readFileSync(new URL('../src/app.module.ts', import.meta.url), 'utf8');
  assert.match(root, /LoggerModule\.forRoot\(\{ pinoHttp: httpLoggerOptions\(/);
});
```

Break it once before trusting it (`logging-standard` section 7 test 5), each break failing the test named, then restore:

1. Empty `DEFAULT_REDACT_PATHS`: the contract and redaction test fails.
2. Make `errorHandler` answer every error as a 500 with `res.err = err`: the malformed-body test fails.
3. Make `isExpectedClientError` always return false: the expected-4xx assertion fails.
4. Delete `app.useGlobalFilters(...)` from the Nest test's `before()`: the 500-once test fails; delete it from `main.ts`: the wiring test fails.
5. Delete the `logCompletionIfMissing` call in the filter's `HttpException` branch: the rejected-body Nest test fails.

## Moving an existing pino logger onto the contract

Change in place when the project already has one shared logger factory with AsyncLocalStorage correlation and redaction (Westmont: `message`, `error`, ISO `timestamp` plus `time`, numeric `level`, a redaction test); otherwise adopt the four files above.
In place means:

1. Add `service`, `env`, `version` through `base`.
2. Accept `traceparent` and `x-request-id`, validate every inbound id, and return `x-request-id`.
3. Wrap job processors so worker lines carry the request's ids.
4. Drop `req`/`res` dumps from request lines, extend the redaction defaults, and serialize errors to the four keys only.
5. Keep an existing tenant field name only as a declared alias (`logging-standard` section 1).
6. Set `errorKey: 'err'` and rename to `error` in the log formatter, so Nest's `{ err }` calls get a message.
   If the logger and pino-http options are spread into one object (nestjs-pino's `pinoHttp: { ...loggerOptions, ...httpOptions }`), the later `serializers` replaces the earlier one, so the http options carry all three: `serializers: { req: () => undefined, res: () => undefined, error: (v) => v }`.
7. Install `LogOnceExceptionFilter` (NestJS wiring above) and pin its registration with a structural test when the full app needs a database to boot.
8. Before the PR, grep the repo for readers of the old fields (`req.url`, `responseTime`, `msg`, `name`, `svc`, `req.headers` in docs, project skills, scripts, saved queries) and update them; list Better Stack saved searches, dashboards, and alerts that use them in the PR body, since lines from before the deploy keep the old shape.
9. Set `APP_ENV` per environment and pass `GIT_SHA` from the deploy's image tag (for example `GIT_SHA: ${IMAGE_TAG:-unknown}` in the compose file); a server `.env` change is the user's step (`environments`), named in the PR body.
10. A shared logger package is shared infrastructure: follow the project's own rule for announcing such changes.

Changing `level` to labels in such a project breaks scripts that grep numeric levels (Westmont's deploy check greps `"level":(50|60)`); keep it numeric.
