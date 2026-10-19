# Next.js

Training data lags the installed Next.js: APIs, caching defaults, and file conventions change between minor versions.
Vercel's own evals found agents pass far more often with version-matched docs than with any knowledge skill, so the docs come first and this file only adds the traps.

## Before writing code

1. Version, from the package that depends on `next` (in a monorepo, not always the root): its lockfile entry, or `pnpm list next` (the repo's package manager) after install.
2. Read the guide for the API you are about to use, from the first source that exists:
   - 16.2 or later: `node_modules/next/dist/docs/` (`01-app/` for the App Router, `02-pages/` for the Pages Router).
   - 16.1 or earlier: `.next-docs/`; when it is missing, run `npx @next/codemod@canary agents-md --output AGENTS.md` in that package (without `--output` it waits on a prompt), which downloads version-matched docs into the gitignored `.next-docs/` and indexes them in `AGENTS.md`; check with `git diff AGENTS.md` that every other block (such as `project-init`) is intact, then commit `AGENTS.md` and `.gitignore` with the change.
   - Only when that fails, the page's `.md` URL (`https://nextjs.org/docs/app/getting-started/caching.md`), which describes the latest version, so check its version notes against yours.
   - Error codes: `https://nextjs.org/docs/messages/<code>.md` (not bundled).
3. Router: `app/` or `pages/`; never copy a pattern from the other router.
4. Read `next.config.*` for flags that change the rules below: `cacheComponents`, `reactCompiler`, `output`, anything under `experimental`.
5. A `<!-- BEGIN:nextjs-agent-rules -->` block in `AGENTS.md` is written by `next dev` (16.3+); keep it and commit it with your work.

## Traps

- Components are Server Components by default; put `'use client'` on the smallest leaf that needs state, effects, or browser APIs, since everything it imports ships to the browser.
- Props passed from a Server Component to a Client Component are serialized into the page: pass only the fields the client renders, never whole rows, secrets, or tokens.
- Server actions and route handlers are public HTTP endpoints: authenticate, authorize, and validate input inside each one; `middleware`/`proxy` or a layout check is not an auth gate (`security-pass` owns the checklist).
- `redirect()` and `notFound()` work by throwing: call them after the `try`/`catch`, never inside it, or the catch swallows them.
- `cookies()`, `headers()`, `params`, and `searchParams` are async since Next 15; await them.
- Caching depends on the version and on `cacheComponents`; read the installed caching guide instead of assuming `fetch` or route defaults.
  After a mutation, revalidate exactly the paths or tags it changed, with the API that guide names.
- Independent awaits start together (`Promise.all`); slow parts sit behind `<Suspense>` so the rest streams.
- Work after the response (logging, emails, webhooks to others) goes through `after()`, never a floating promise that dies with the function.
- `NEXT_PUBLIC_` variables are inlined at build time: they are public, and changing one needs a rebuild.
- New route handlers use the Node.js runtime; check the installed docs before writing `runtime = 'edge'`, which Vercel recommends migrating away from.
- `next/link`, `next/image`, and `next/font` instead of raw `<a>`, `<img>`, and font links; `next/dynamic` for heavy client-only widgets.
- Import icons and large libraries by path, not through a barrel file, unless `optimizePackageImports` covers that package.

## Verify

- Run `next build` (or the project's build script) once before calling it done; typecheck alone misses server and client boundary errors.
  On 16.3+ with `next dev` running, the MCP endpoint `/_next/mcp` (`get_compilation_issues`) gives the same answer faster while iterating.
- Then the runtime check of `e2e-verify`.

## Deeper, only when the task is in that area

- Performance (waterfalls, bundle, re-renders): Vercel's rule files, one per rule, at `https://raw.githubusercontent.com/vercel-labs/agent-skills/main/skills/react-best-practices/rules/<rule>.md`; the index is the skill's `SKILL.md`, one folder up from `rules/`.
- Adopting or tuning Cache Components: the official workflow skills `next-cache-components-adoption` and `-optimizer`, installed into the project only when the user asks (`npx skills add vercel/next.js --skill <name>`).
