# Next.js and serverless

The implementation of the `logging-standard` contract where the process can be frozen or killed right after a response.
Tested with Next.js 16.4.2 (`next build` and `next start`), React 19, @logtail/node 0.5.12, @logtail/pino 0.5.12, against a local stand-in for the ingest endpoint.

## Rules for serverless

- Never use a pino worker transport (`transport:` or `pino.transport()`) in a serverless function: the worker thread is frozen with the function and its last batch is lost.
- Every invocation flushes before it ends: `after(flushLogs)` in route handlers (inside `route()`) and server actions, `event.waitUntil(flushLogs())` in `proxy.ts`/`middleware.ts`, `await logtail.flush()` in a plain function handler.
- Log from the Node.js runtime only.
  Next 16 deprecates the edge runtime and runs `proxy.ts` on Node.js; Next 15.5 can run middleware on Node.js too, so read that version's middleware docs for the setting.
  `@logtail/edge` failed in Next's edge runtime in testing (it needs `CompressionStream`, which the runtime rejects), so the lines were lost.
- Browser code never holds the source token: no `NEXT_PUBLIC_BETTER_STACK_SOURCE_TOKEN`; the browser posts to the app's own route, which logs on the server.
- App logs go through this SDK; a Vercel log drain, if any, carries only platform request and build logs into its own source, never the app's (`betterstack-logs` section 2).

## Why @logtail/node and not @logtail/next

`@logtail/next` puts every field you pass under `fields` (`fields.event`, `fields.trace_id`) and adds its own `request`/`vercel` objects, so its lines do not match the contract the queries in `betterstack-logs` rely on.
`@logtail/node` sends `{dt, level, ...fields, message}` with the fields at the top level, as the pino path does.
A project that already uses `@logtail/next` for web vitals may keep it for that alone.

```bash
npm install @logtail/node server-only
```

## lib/log.ts

```ts
// lib/log.ts - server-side logger for Next.js (Node.js runtime only); every call site must flush before the invocation ends.
import 'server-only';
import { Logtail } from '@logtail/node';

type Level = 'debug' | 'info' | 'warn' | 'error';
type Fields = Record<string, unknown>;
const ORDER: Record<Level, number> = { debug: 10, info: 20, warn: 30, error: 40 };

const token = process.env.BETTER_STACK_SOURCE_TOKEN;
const host = process.env.BETTER_STACK_INGESTING_HOST;
const client = token && host
  ? new Logtail(token, {
      endpoint: /^https?:\/\//.test(host) ? host : `https://${host}`,
      captureStackContext: false, // per-line file/line context costs bytes and points into bundled chunks
    })
  : undefined;

const base = { service: 'web', env: process.env.APP_ENV ?? 'local', version: process.env.GIT_SHA ?? 'unknown' };
const minLevel = ORDER[(process.env.LOG_LEVEL as Level) ?? 'info'] ?? ORDER.info;

const SECRET_KEY = /pass(word)?|token|secret|authorization|cookie|api_?key|email|phone|card|cvc|cvv/i;

function redact(value: unknown, depth = 0): unknown {
  if (depth > 8 || value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) return value.map((v) => redact(v, depth + 1));
  return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, SECRET_KEY.test(k) ? '[REDACTED]' : redact(v, depth + 1)]));
}

export function errorField(err: unknown): Fields {
  if (!(err instanceof Error)) return { type: 'NonError', message: String(err) };
  return { type: err.name, message: err.message, stack: err.stack, ...(err.cause !== undefined ? { cause: errorField(err.cause) } : {}) };
}

function write(level: Level, message: string, fields: Fields): void {
  if (ORDER[level] < minLevel) return;
  const { error, ...rest } = fields;
  const line = { ...base, ...(redact(rest) as Fields), ...(error !== undefined ? { error: errorField(error) } : {}), message };
  if (client) void client.log(message, level, line);
  else console[level === 'debug' ? 'log' : level](JSON.stringify({ level, timestamp: new Date().toISOString(), ...line }));
}

export interface Log {
  debug(message: string, fields?: Fields): void;
  info(message: string, fields?: Fields): void;
  warn(message: string, fields?: Fields): void;
  error(message: string, fields?: Fields): void;
  with(fields: Fields): Log;
}

function make(bound: Fields): Log {
  return {
    debug: (m, f = {}) => write('debug', m, { ...bound, ...f }),
    info: (m, f = {}) => write('info', m, { ...bound, ...f }),
    warn: (m, f = {}) => write('warn', m, { ...bound, ...f }),
    error: (m, f = {}) => write('error', m, { ...bound, ...f }),
    with: (f) => make({ ...bound, ...f }),
  };
}

export const log = make({});

const TRACEPARENT = /^00-([0-9a-f]{32})-[0-9a-f]{16}-[0-9a-f]{2}$/;
const SAFE_ID = /^[A-Za-z0-9._:-]{1,128}$/;

/** Logger bound to the request's ids; proxy.ts sets x-request-id on every request, so handlers and actions agree. */
export function requestLog(headers: Headers): Log {
  const safe = (v: string | null) => (v && SAFE_ID.test(v) ? v : undefined);
  const tp = TRACEPARENT.exec(headers.get('traceparent') ?? '');
  const trace_id = (tp && !/^0+$/.test(tp[1]) ? tp[1] : undefined) ?? safe(headers.get('x-correlation-id'));
  return log.with({ request_id: safe(headers.get('x-request-id')), ...(trace_id ? { trace_id } : {}) });
}

/** Await this before the invocation ends: pass it to after() or event.waitUntil(). */
export function flushLogs(): Promise<void> {
  return client ? client.flush().then(() => undefined) : Promise.resolve();
}
```

- `service` is the service name from `logging-standard` section 1; `GIT_SHA` comes from `next.config` `env` as in the `environments` skill's `references/version-endpoint.md`.
- Key-based redaction also hides harmless keys that contain a listed word (`token_count`); rename those fields rather than weakening the pattern.
- Without the two `BETTER_STACK_*` variables, lines go to the console as JSON, which is what local dev and `next build` need.

## proxy.ts: ids for every request

```ts
// proxy.ts (Next 16; middleware.ts before 16) - give every request ids, log it, flush with waitUntil.
import { type NextFetchEvent, type NextRequest, NextResponse } from 'next/server';
import { flushLogs, requestLog } from './lib/log';

const SAFE_ID = /^[A-Za-z0-9._:-]{1,128}$/;

export function proxy(request: NextRequest, event: NextFetchEvent) {
  const headers = new Headers(request.headers);
  const inbound = headers.get('x-request-id');
  const requestId = inbound && SAFE_ID.test(inbound) ? inbound : crypto.randomUUID();
  headers.set('x-request-id', requestId);
  if (!headers.get('traceparent') && !SAFE_ID.test(headers.get('x-correlation-id') ?? '')) {
    headers.set('x-correlation-id', crypto.randomUUID().replaceAll('-', ''));
  }
  // Route handlers, server actions and pages read the same ids from these request headers.
  const response = NextResponse.next({ request: { headers } });
  response.headers.set('x-request-id', requestId);
  requestLog(headers).debug('request received', { event: 'http.request.received', http: { method: request.method, route: request.nextUrl.pathname } });
  event.waitUntil(flushLogs());
  return response;
}

export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico|api/health).*)'] };
```

On Next 15 or older the file is `middleware.ts` and the export is `middleware`.
Downstream code reads the ids from the request headers, so a route handler, a server action and the page of one request share them.

## Route handlers

Wrap every route handler in `route()`: it writes the one completion line, logs an uncaught error once, and flushes after the response.
The browser log route below is the one exception, because its lines are the browser's events.

```ts
// lib/route.ts - one completion line per route handler call, errors logged once, flushed after the response.
import 'server-only';
import { after } from 'next/server';
import { unstable_rethrow } from 'next/navigation';
import { flushLogs, requestLog, type Log } from './log';

type Fields = Record<string, unknown>;

export interface RequestScope {
  /** Bound to the request ids and to whatever set() added. */
  readonly log: Log;
  /** Add tenant_id and user_id once auth resolves; later lines and the completion line carry them. */
  set(fields: Fields): void;
  /** Name an expected 4xx on the completion line instead of logging a second line. */
  outcome(event: string, fields?: Fields): void;
}

export function route<C>(template: string, handler: (request: Request, context: C, scope: RequestScope) => Promise<Response> | Response) {
  return async (request: Request, context: C): Promise<Response> => {
    const started = Date.now();
    after(flushLogs); // runs after the response is sent; on Vercel it is kept alive with waitUntil
    let log = requestLog(request.headers);
    let completion: Fields = { event: 'http.request.completed' };
    const scope: RequestScope = {
      get log() { return log; },
      set: (fields) => { log = log.with(fields); },
      outcome: (event, fields = {}) => { completion = { ...fields, event }; },
    };
    const http = (status_code: number) => ({ method: request.method, route: template, status_code, duration_ms: Date.now() - started });
    try {
      const response = await handler(request, context, scope);
      const level = response.status >= 500 ? 'error' : response.status >= 400 ? 'warn' : 'info';
      log[level]('request completed', { ...completion, http: http(response.status) });
      return response;
    } catch (error) {
      unstable_rethrow(error); // redirect() and notFound() are control flow, not failures
      // The wrapper is the boundary: log once here and answer; do not rethrow.
      log.error('request failed', { event: 'http.request.failed', error, http: http(500) });
      return Response.json({ error: 'internal_error' }, { status: 500 });
    }
  };
}
```

```ts
// app/api/invoices/[id]/route.ts - Node runtime route handler.
import { route } from '@/lib/route';

export const GET = route('/api/invoices/[id]', async (_request, { params }: { params: Promise<{ id: string }> }, scope) => {
  scope.set({ tenant_id: 'org_42', user_id: 'usr_7' }); // ids from your auth session
  const { id } = await params;
  if (id === 'boom') throw new Error('invoice lookup failed', { cause: new Error('db timeout') });
  if (id.startsWith('other_')) {
    scope.outcome('invoice.access.denied', { invoice_id: id });
    return Response.json({ error: 'forbidden' }, { status: 403 });
  }
  scope.log.info('invoice viewed', { event: 'invoice.viewed', invoice_id: id });
  return Response.json({ id });
});
```

```ts
// app/api/version/route.ts - the version endpoint from the environments skill, wrapped like every route.
import { route } from '@/lib/route';

export const dynamic = 'force-dynamic';

export const GET = route('/api/version', () => Response.json(
  { service: 'web', sha: process.env.GIT_SHA ?? 'unknown', builtAt: process.env.BUILT_AT ?? 'unknown', env: process.env.APP_ENV ?? 'unknown' },
  { headers: { 'Cache-Control': 'no-store' } },
));
```

- The route is the template (`/api/invoices/[id]`), never the URL.
- The version route's `info` completion line is the line the `betterstack-logs` shipping check looks for in production, where the proxy's `debug` line is off.

## Server actions

```ts
'use server';
// app/actions/pay.ts - server action.
import { after } from 'next/server';
import { headers } from 'next/headers';
import { flushLogs, requestLog } from '@/lib/log';

export async function payInvoice(formData: FormData): Promise<{ ok: boolean }> {
  const log = requestLog(await headers());
  after(flushLogs);
  const invoiceId = String(formData.get('invoiceId'));
  log.info('invoice paid', { event: 'invoice.paid', invoice_id: invoiceId, card: { token: 'tok_should_not_appear' } });
  return { ok: true };
}
```

Server components log the same way with `requestLog(await headers())` and `after(flushLogs)`; `after()` works in server components, route handlers, server actions and proxy.

## Unexpected server errors

```ts
// instrumentation.ts - the boundary for server errors no code caught.
import type { Instrumentation } from 'next';

export const onRequestError: Instrumentation.onRequestError = async (error, request, context) => {
  if (process.env.NEXT_RUNTIME !== 'nodejs') return;
  const { flushLogs, requestLog } = await import('./lib/log');
  const headers = new Headers(Object.entries(request.headers).map(([k, v]) => [k, Array.isArray(v) ? v.join(',') : v ?? '']));
  const digest = typeof error === 'object' && error !== null && 'digest' in error ? String(error.digest) : undefined;
  requestLog(headers).error('request failed', {
    event: 'http.request.failed',
    error,
    digest,
    http: { method: request.method, route: context.routePath, status_code: 500 },
    next: { route_type: context.routeType },
  });
  await flushLogs();
};
```

Next calls `onRequestError` for errors no code caught, in route handlers, server actions, rendering and proxy, so it is their one log; code that catches an error logs it itself and does not rethrow.
The error may be one React rebuilt during rendering; the `digest` ties it to the original.

## Browser logs through a proxy route

```ts
// app/api/client-log/route.ts - browser logs reach Better Stack through our server: no token in the bundle, same contract, bounded input.
import { after } from 'next/server';
import { flushLogs, requestLog } from '@/lib/log';

const MAX_BODY_BYTES = 16 * 1024;
const MAX_EVENTS = 20;
const LEVELS = new Set(['info', 'warn', 'error']);
const EVENT = /^[a-z0-9_]+(\.[a-z0-9_]+)+$/;

type ClientEvent = { level?: string; event?: string; message?: string; error?: { type?: string; message?: string; stack?: string }; route?: string };

export async function POST(request: Request) {
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return new Response(null, { status: 413 });
  let events: ClientEvent[];
  try {
    const parsed = JSON.parse(text);
    events = (Array.isArray(parsed) ? parsed : [parsed]).slice(0, MAX_EVENTS);
  } catch {
    return new Response(null, { status: 400 });
  }
  const log = requestLog(request.headers).with({ origin: 'browser' });
  after(flushLogs);
  for (const e of events) {
    const level = LEVELS.has(e.level ?? '') ? (e.level as 'info' | 'warn' | 'error') : 'info';
    const event = typeof e.event === 'string' && EVENT.test(e.event) ? e.event : 'client.unknown';
    const error = e.error ? { type: String(e.error.type ?? 'Error').slice(0, 100), message: String(e.error.message ?? '').slice(0, 1000), stack: String(e.error.stack ?? '').slice(0, 4000) } : undefined;
    log[level](String(e.message ?? event).slice(0, 500), { event, route: String(e.route ?? '').slice(0, 200), ...(error ? { client_error: error } : {}) });
  }
  return new Response(null, { status: 204 });
}
```

```ts
// lib/client-log.ts - browser side: send to our own route, never to Better Stack directly.
export function reportClientError(error: Error, event = 'client.error.unhandled'): void {
  const body = JSON.stringify({ level: 'error', event, message: 'client error', route: location.pathname, error: { type: error.name, message: error.message, stack: error.stack } });
  if (!navigator.sendBeacon?.('/api/client-log', new Blob([body], { type: 'application/json' }))) {
    void fetch('/api/client-log', { method: 'POST', body, keepalive: true, headers: { 'content-type': 'application/json' } });
  }
}
```

```tsx
'use client';
// app/error.tsx - route error boundary reports once per error.
import { useEffect } from 'react';
import { reportClientError } from '@/lib/client-log';

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => { reportClientError(error); }, [error]);
  return <button onClick={reset}>Try again</button>;
}
```

- Exclude `/api/client-log` from auth middleware only if anonymous pages must report errors, and rate-limit it per IP at the edge or in the route.
- The route caps size, count, level and event names because anyone can post to it; it never forwards browser-supplied fields as they are.
- Report errors from error boundaries and caught failures, never `console.log` mirroring or every click.

## Plain serverless functions with pino

When a function already uses pino, keep it but write in the same thread and flush:

```ts
// handler.ts - pino in a serverless function: in-thread stream, flushed before returning.
import { Logtail } from '@logtail/node';
import { LogtailStream } from '@logtail/pino';
import { createLogger } from './src/logger.js';

const logtail = new Logtail(process.env.BETTER_STACK_SOURCE_TOKEN!, { endpoint: `https://${process.env.BETTER_STACK_INGESTING_HOST}` });
const logger = createLogger({ service: 'billing-fn', destination: new LogtailStream(logtail) });

export async function handler(event: { invoiceId: string }) {
  try {
    logger.info({ event: 'invoice.paid', invoice_id: event.invoiceId }, 'invoice paid');
    return { ok: true };
  } finally {
    await logtail.flush(); // the platform may freeze the process right after return
  }
}
```

`LogtailStream` needs @logtail/pino 0.5.12 or newer; pass `captureStackContext: false` to the `Logtail` options if the per-line `context.runtime` object is not wanted.

## Tests

```ts
// test/log.test.ts - run with: node --conditions=react-server --import tsx --test test/log.test.ts
import assert from 'node:assert/strict';
import { test } from 'node:test';

test('lines follow the contract and secrets never reach the output', async () => {
  delete process.env.BETTER_STACK_SOURCE_TOKEN; // no client: lines go to the console as JSON
  const lines: Record<string, any>[] = [];
  const original = console.info;
  console.info = (s: string) => { lines.push(JSON.parse(s)); };
  try {
    const { requestLog } = await import('../lib/log');
    const headers = new Headers({ 'x-request-id': 'req-1', 'x-correlation-id': 'not valid!' });
    requestLog(headers).info('invoice paid', { event: 'invoice.paid', card: { token: 'tok_live_secret' }, headers: { authorization: 'Bearer abc' } });
  } finally {
    console.info = original;
  }
  const raw = JSON.stringify(lines);
  assert.ok(!raw.includes('tok_live_secret') && !raw.includes('Bearer abc'), 'secret leaked');
  assert.ok(raw.includes('[REDACTED]'));
  for (const f of ['timestamp', 'level', 'message', 'service', 'env', 'version', 'request_id', 'event']) assert.ok(lines[0][f], `missing ${f}`);
  assert.equal(lines[0].trace_id, undefined, 'invalid inbound id was accepted');
});
```

Break it once by disabling the redaction in `lib/log.ts`; the test must fail with `secret leaked`.
