# NestJS

NestJS has no official agent skill, and its majors move fast (v12 ships ESM packages and Standard Schema validation), so patterns from training data are often a version behind.
The official docs are published as Markdown for agents; read them for the version you run before copying a pattern.

## Before writing code

1. Version: the lockfile entry for `@nestjs/core`, or `pnpm list @nestjs/core` (the repo's package manager) after install; if it is newer than the patterns you know, read `https://docs.nestjs.com/migration-guide.md` first.
2. Docs: every chapter as Markdown at its URL plus `.md` (`https://docs.nestjs.com/controllers.md`); index at `https://docs.nestjs.com/llms.txt`.
   Never fetch `llms-full.txt` whole; it is every chapter in one file.
3. Read `main.ts` for the HTTP adapter (Express or Fastify), global pipes, guards, filters, interceptors, and prefixes, since they decide what each new route gets for free.
4. Find how the project validates input (`ValidationPipe` with class-validator DTOs, or schemas with `StandardSchemaValidationPipe`), how it reaches the database, and how it builds the API contract (`@nestjs/swagger`); copy those, never add a second way.

## Traps

- A provider is usable outside its module only when that module exports it and the consumer imports the module; fix "Nest can't resolve dependencies" with imports and exports, not with `@Global()`.
  A circular import solved with `forwardRef` is a sign to extract the shared part into its own module.
- Every body, query, and param goes through validation; the project's global `ValidationPipe` should set `whitelist` and `forbidNonWhitelisted` so unknown fields are rejected, and `transform` so `@Param` ids arrive as numbers, not strings; with Standard Schema validation, make the object schema strict instead.
- Order of a request: middleware, guards, interceptors, pipes, handler, interceptors, exception filters.
  Authorization belongs in a guard; a check in middleware or after validation runs in the wrong place.
- The auth guard should be global (`APP_GUARD`) with an explicit public-route opt-out, so a new controller is protected by default instead of only when someone remembers the decorator.
  A project missing this or the global validation above: protect and validate the new route explicitly, and raise the global change per `ask-or-decide` instead of refactoring it inside the story.
- The tenant and the user come from the authenticated principal, never from a body field or a header the client sets.
- Providers are singletons shared by all requests: never keep request data in a service field.
  `Scope.REQUEST` makes every consumer up the chain request-scoped too; pass request context with AsyncLocalStorage (`https://docs.nestjs.com/recipes/async-local-storage.md`) instead.
- `@Res()` turns off Nest's response handling (interceptors, serialization, `@HttpCode()`); use `@Res({ passthrough: true })` when you only need to set a cookie or header.
- Throw Nest's HTTP exceptions (`NotFoundException`, `ForbiddenException`) for expected failures; anything else becomes a 500, and no stack trace or SQL text may reach the response.
- Never return an ORM entity directly: map to a response DTO or use the serialization interceptor, so password hashes and internal columns never leak.
- Read configuration through `ConfigModule` with a validation schema, so a missing env var fails at startup instead of at the first request.
- Call `app.enableShutdownHooks()` for anything that runs in a container, so `SIGTERM` closes database and queue connections.
- ORM `synchronize` stays off outside local throwaway databases; schema changes are migrations.

## Verify

- Unit tests build the module with `Test.createTestingModule` and replace only external edges with `overrideProvider`.
- E2E tests boot the real app module and call `app.getHttpServer()` with `supertest`, against this worktree's own database, covering at least one rejected request (validation or authorization) per new route.
- When the project generates OpenAPI, check the generated contract shows the new route and fields as the story needs them.
