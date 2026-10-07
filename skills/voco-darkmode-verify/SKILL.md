---
name: voco-darkmode-verify
description: Use when verifying or fixing dark-mode for a VOCO page — runs browser via Playwright MCP, identifies low-contrast bugs by reading computed styles, fixes CSS to use semantic tokens. Triggers on "check dark mode for /xxx", "verify dark mode for page X", "fix dark mode", "tiếp tục verify trang", "kiểm tra dark mode trang".
---

# VOCO Dark Mode — Page Verify & Fix

You're verifying dark mode for a specific page in the VOCO codebase (`apps/web` submodule). This skill captures the actual failure modes hit during the initial dark-mode rollout — read it before touching CSS.

## Hard rules — don't repeat these mistakes

### 1. Static audit is NOT enough. Always MCP-browser verify.

The initial agent audit said "all TSX clean ✅" but Playwright screenshots revealed ~80 hidden CSS hex literals breaking dark mode. Pages can look "clean" at the TSX layer and still be totally broken at render. Do not mark a page Done until you've seen its dark-mode screenshot.

### 2. VOCO has DUAL :root blocks. Check BOTH.

- `apps/web/src/app/globals.css` — defines `--color-*` tokens in `:root` + `[data-theme="dark"]`
- `apps/web/src/styles/legacy.css` — **also** defines `:root` + `[data-theme="dark"]`, loads AFTER globals.css

Because legacy.css loads later, **any variable it redefines in `:root` overrides globals.css — including the dark override**. If legacy.css `[data-theme="dark"]` block is MISSING a variable that legacy.css `:root` declares, the variable stays at light value in dark mode regardless of what globals.css says.

This is THE biggest gotcha. The "Gratuit/Elite/Compare/Final CTA bug" was caused entirely by `--color-surface-subtle` being declared in legacy.css `:root` but missing from legacy.css dark block.

**Always grep both files for any token you're debugging:**
```bash
grep -nE '\-\-color-surface-subtle' apps/web/src/app/globals.css apps/web/src/styles/legacy.css
grep -nE '\-\-color-surface-subtle' apps/web/src/styles/legacy.css  # check legacy.css separately
```

If legacy.css declares it in `:root` but not in its `[data-theme="dark"]` block (legacy.css lines ~118-160), add it.

### 3. `--navy-50..--navy-950` palette in legacy.css is light-only.

Any CSS rule using `var(--navy-700)` etc. directly as TEXT or BORDER color will stay navy in dark mode → invisible on dark surface. Do NOT globally flip the navy palette in dark — it breaks navy-slab elements (sidebar, navy CTAs, gradient cards). Fix per-rule:
- Text: `var(--navy-700)` → `var(--color-fg)`
- Border: `var(--navy-200)` → `var(--color-border)`
- BG (navy slab): leave as-is

Same for `--gold-*`, `--espresso-*`, `--forest-*` — these are brand palette, not theme-aware.

### 4. HMR delay — re-screenshot after edits.

Right after editing legacy.css, the page in browser may still show OLD CSS for 1-3 seconds. Don't trust the first screenshot after an edit. Either:
- Re-navigate (`browser_navigate` to same URL forces fresh CSS)
- Or run `browser_evaluate` to read `getComputedStyle()` first — if the computed value reflects your edit, the CSS is loaded.

### 5. Hex literals in tailwind utility form `bg-[#...]` text-[#...]` count too.

Don't only grep raw `#hex`. Also grep `bg-\[#` `text-\[#` patterns in TSX.

### 6. Use `getComputedStyle()` over screenshot for diagnosis.

Screenshots show the symptom (text invisible). `getComputedStyle` tells you WHY (color resolves to navy on dark surface). Always read the resolved color of suspect elements before guessing what's wrong:

```js
() => {
  const els = [...document.querySelectorAll('*')]
    .filter(el => el.children.length === 0 &&
                  (el.textContent||'').trim().includes('NEEDLE TEXT'));
  return els.slice(0,3).map(el => ({
    cls: el.className,
    color: getComputedStyle(el).color,
    bg: getComputedStyle(el.parentElement || el).backgroundColor,
    text: el.textContent.trim().slice(0,60)
  }));
}
```

### 7. Don't fix problems agents claimed to fix — verify their output.

Subagents reported "all hex tokenized ✅" but several hexes survived (mostly text-on-card-bg pairs where the agent missed the corresponding bg fix). Always re-grep after agent runs:
```bash
grep -nE '#[0-9a-fA-F]{3,8}\b' apps/web/src/styles/legacy.css \
  | grep -vE '/\*|\*\/' \
  | grep -vE 'var\(--[a-z-]+,\s*#' \
  | head -30
```

## Workflow per page

### Step 1: Read the spec

`apps/web/DARKMODE_PROGRESS.md` tracks status. Find the page you're verifying; read its sections + known issues. Update the row after verifying.

### Step 2: Start dev server (if not running)

```bash
pnpm dev  # check port — may be 3000 or 3001 if 3000 taken
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/fr
```

### Step 3: Make sure Playwright MCP screenshot dir exists at allowed root

Playwright MCP only writes to `/Users/quocle/Desktop/workspace/VOCO/` or `.playwright-mcp/`. Use a path relative to that root:
```
darkmode-verify/<page-slug>-dark.png
```

### Step 4: Navigate + set dark mode + verify

```js
// in browser_evaluate
() => {
  localStorage.setItem('voco-theme','dark');
  document.documentElement.setAttribute('data-theme','dark');
  return getComputedStyle(document.documentElement).getPropertyValue('--color-surface');
}
```

If returned value isn't a dark color (should start with `#0` or `#1`), the dark mode token isn't applying — go fix legacy.css dark block FIRST (rule 2 above).

### Step 5: Take screenshot

`mcp__playwright__browser_take_screenshot` with `type: 'jpeg'`. Use `fullPage: true` only when needed (large files).

### Step 6: Read screenshot + identify problems

Look for:
- Light-colored text blocks (white/ivory) that appear faded → text-on-light-bg in dark mode → card bg didn't flip
- Dark-colored text (navy/black) on dark page → text didn't flip; likely uses `var(--navy-700)` direct
- Icon/SVG with hardcoded fill/stroke
- Borders missing in dark (white-ish on dark bg)

### Step 7: Diagnose via eval

Use the snippet in rule 6 above. Pass actual visible text from the screenshot as needle.

### Step 8: Find offending CSS rule

```bash
grep -nE '\.<classname>\{' apps/web/src/styles/legacy.css apps/web/src/app/globals.css
```

### Step 9: Fix to semantic tokens

Available token mapping (memorize):

| Use case | Token |
|---|---|
| Page bg | `var(--color-bg)` |
| Card / surface | `var(--color-surface)` |
| Subtle card / muted surface | `var(--color-surface-subtle)` |
| Hover state | `var(--color-surface-hover)` |
| Body text | `var(--color-fg)` |
| Secondary text | `var(--color-fg-secondary)` |
| Muted text / hints | `var(--color-fg-muted)` |
| Border | `var(--color-border)` |
| Stronger border | `var(--color-border-strong)` |
| Primary CTA (navy) | `var(--color-primary)` + `var(--color-primary-fg)` text |
| Accent (gold) | `var(--color-accent)` + `var(--color-accent-fg)` text |
| Accent text-only | `var(--color-accent-text)` |
| Accent soft bg | `var(--color-accent-soft)` |
| Success | `var(--color-success)` / `var(--color-success-soft)` |
| Danger / error | `var(--color-danger)` / `var(--color-danger-soft)` |
| Info / link blue | `var(--color-info)` / `var(--color-info-soft)` |

### Step 10: Re-verify

Re-navigate, re-screenshot, re-eval. Don't trust HMR.

### Step 11: Update spec

Edit `apps/web/DARKMODE_PROGRESS.md` row for that page: Impl → ✅ (or note partial), MCP → ✅, Done → ✅.

### Step 12: Typecheck + lint

```bash
cd /Users/quocle/Desktop/workspace/VOCO && pnpm typecheck && pnpm lint
```

## Page-specific notes

These pages have known follow-ups beyond the bulk fix:

- **`/dashboard/*` + `/onboarding/*`** — Heavy use of `.pp-*` / `.ob-*` / `.prof-*` classes referencing `var(--navy-700)` directly. Each rule needs per-context replacement (see rule 3). Don't batch-sed; use Edit with the right semantic token per use case (text/border/bg).
- **`/admin/*`** — TSX uses tailwind semantic utilities (`bg-surface`, `text-fg`); usually OK. Verify shared `.admin-*` table classes in legacy.css.
- **`(app)` sidebar `.app-side-*`** — INTENTIONAL navy slab in both themes per design. Skip unless PM approves a light-sidebar redesign.
- **`/dashboard/analytics`** — Chart uses `--espresso-300` (legacy palette, no dark override). Already fixed to `var(--color-border)`. If you see similar, prefer semantic.

## Pages remaining to verify

Check `apps/web/DARKMODE_PROGRESS.md` "MCP" column = ⏳ rows. Public pages done; auth/onboarding/dashboard/settings/admin still pending MCP verify.

## Don't do

- ❌ Don't add a global `[data-theme="dark"]` rule that flips `--navy-700` palette — breaks navy slab elements
- ❌ Don't trust agent reports without re-grepping
- ❌ Don't screenshot immediately after edit without re-navigate
- ❌ Don't tokenize SVG paths whose colors are brand-fixed (Google G logo, FR/EN flags)
- ❌ Don't tokenize gradient stops on intentionally-fixed brand surfaces (Pro card navy gradient)
- ❌ Don't commit unless user explicitly asks
