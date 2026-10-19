# Vercel

Code that runs fine in `next dev` can still fail on Vercel: functions are stateless, time-limited, and get their environment per deployment.
Deploy commands, environments, and promotion belong to `environments`; this file covers writing code that runs well there.

## Before writing code

1. Read `vercel.json` or `vercel.ts` (crons, function settings, rewrites, regions) and the project's framework preset; with neither file, the project runs on defaults.
2. Find the plan (Hobby, Pro, Enterprise) from the registry or the user when the change depends on a limit (cron frequency, duration); ask once rather than guess.
3. Docs: every page has a `.md` URL (`https://vercel.com/docs/functions/limitations.md`); index at `https://vercel.com/docs/llms.txt`.
   Limits and plan features change; read the limitations page before relying on a number.

## Traps

- No persistent filesystem or memory between requests: only `/tmp`, per instance and temporary; files, uploads, and caches go to storage (Blob, Supabase Storage, a database).
- Max duration defaults to 300s and the ceiling depends on the plan; long jobs go to a queue or workflow, not one long request.
- Request bodies have a size limit (see the limitations page); large uploads go straight from the browser to storage with a signed URL.
- Work after the response uses `waitUntil` from `@vercel/functions` (`after()` in Next.js); a floating promise is cut off when the response ends.
- Environment variable changes apply only to new deployments: redeploy after changing one, and set it for each environment (Production, Preview, Development) that needs it.
- `NEXT_PUBLIC_` and other public-prefixed variables are baked into the build and visible to everyone.
- Preview deployments get their own URLs: auth callbacks, CORS lists, and webhook targets must allow them or be set per environment, never hard-coded to production.
- Crons are declared under `crons` in `vercel.json`/`vercel.ts` (`https://vercel.com/docs/cron-jobs.md`) and call the production deployment with a GET request; the handler checks `Authorization: Bearer ${process.env.CRON_SECRET}` and must be idempotent, since a run can repeat.
- Cron schedules are in UTC, so "yesterday" or "9am" for a tenant needs its timezone; Hobby allows at most one run per day, with the hour's timing loose.
- Put the function region next to the database; a cross-region round trip per query adds up fast.
- Use the Node.js runtime for new functions; Vercel recommends migrating away from Edge.
- Database connections from functions go through a pooler, since every instance opens its own connections (see `supabase.md` for the Supabase pooler).

## Verify

- `vercel build` locally, or the preview deployment of the PR, before calling it done when the change touches `vercel.json`/`vercel.ts`, env vars, crons, or function settings.
- Preview logs come through the registry's `logs` command, following `environments`.
