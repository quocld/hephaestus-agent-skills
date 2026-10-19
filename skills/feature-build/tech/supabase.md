# Supabase and Postgres

Supabase changes often (CLI commands, keys, auth helpers), and most of its data bugs are silent: an RLS gap returns rows it should not, a missing policy returns none, and neither raises an error.
Tenant isolation, auth, keys, and storage policies belong to `security-pass`; staging and prod migrations to `environments`; this file covers building the change.

## Before writing code

1. Breaking changes: `curl -s https://supabase.com/changelog.md | grep -i -B1 -A2 'breaking change'` (never read the whole file, it is large), and follow any entry that touches the task.
2. Docs: any page as Markdown by adding `.md` to its URL; index at `https://supabase.com/llms.txt`; the Supabase MCP `search_docs` tool when it is connected.
3. Versions: `@supabase/supabase-js` and `@supabase/ssr` in the lockfile, since auth and cookie helpers change between majors; CLI `supabase --version`, then `supabase <group> --help` for the exact command; never write a command or flag from memory.
4. Schema workflow: `supabase/schemas/` exists or `config.toml` sets `schema_paths` means declarative (edit the schema files, generate the migration); otherwise imperative migrations in `supabase/migrations/`.
5. Work only against your own local database (`worktree-flow` section 2).

## Making a schema change

- Declarative: edit `supabase/schemas/`, then generate the migration with the command `https://supabase.com/docs/guides/local-development/declarative-database-schemas.md` gives for the project's diff engine (`[experimental.pgdelta]` in `config.toml`); on pg-delta that is not `supabase db diff`, which ignores the schema files there.
- Imperative: iterate with `supabase db query` or `psql` on the local database, not with MCP `apply_migration`, which writes a history entry on every call and breaks later diffs.
  Then create the migration with the CLI (`supabase migration new <name>`, or `supabase db pull <name> --local --yes` after iterating); never invent a migration filename.
- Before committing: `supabase db advisors` (CLI 2.81.3+) or MCP `get_advisors`, and fix what it reports; with neither available, say so in the report.
- Regenerate types after the change (`supabase gen types`, with the flags the project's script already uses) and commit them with the migration.

## Traps

- A new table in an exposed schema (`public` by default) gets RLS enabled in the same migration, and may need explicit `grant`s to `anon`/`authenticated` before the Data API can see it at all.
- An `update` needs a `select` policy too; without one, updates silently match 0 rows.
- Write policies with `to authenticated` (or `anon`) plus a row predicate; `auth.role()` is deprecated and passes anonymous sign-ins.
- Wrap auth calls in policies as `(select auth.uid())` so Postgres evaluates them once per query instead of once per row, and index every column a policy filters on.
- Postgres does not index foreign keys: add an index for every foreign key column you create.
- Constraints live in the database (`not null`, `unique`, `check`, foreign keys), not only in app validation.
- Primary keys: `bigint generated always as identity`, or the uuid default the schema already uses; `timestamptz` for times; lowercase snake_case names.
- Lists that grow use keyset (cursor) pagination, not deep `offset`.
- No query per row in a loop: one query with a join or `in (...)`, and multi-row inserts.
- Keep transactions short; never hold one open across a network call.
- Serverless or many-instance servers connect through the Supavisor pooler in transaction mode (port 6543), which does not support named prepared statements: turn them off in the driver or ORM.
- Storage upsert needs `insert`, `select`, and `update` policies on `storage.objects`.

## Verify

- Run the query or request the feature makes, as each role involved, against the local database, and read the rows it returns; "no error" proves nothing under RLS.
  Either sign in one client per test user, or in SQL `begin; set local role authenticated; select set_config('request.jwt.claims', '{"sub":"<user uuid>","role":"authenticated"}', true);` before the query, then `rollback`, adding any other claim the policies read (such as `app_metadata`).
- On an unexpected error, empty result, or RLS surprise, read `https://supabase.com/docs/guides/monitoring-and-debugging.md` before guessing.

## Deeper, only when the task is in that area

- Postgres performance and schema rules, one file per rule: `https://raw.githubusercontent.com/supabase/agent-skills/main/skills/supabase-postgres-best-practices/references/<rule>.md` (`query-`, `conn-`, `schema-`, `lock-`, `data-`; index in `_sections.md`).
