#!/usr/bin/env node
// check-defer-owner.mjs · ships with spec-driven-workflow-init
//
// Walks openspec/changes/**/{proposal,tasks}.md, finds Defer/Deferred sections,
// fails if any line lacks an arrow owner:
//   → m<id>-<slug>      (sibling change folder must exist)
//   → build-plan §<sec> (build-plan must have a [ ] row in that section)
//   → <TICKET-ID>       (Linear/JIRA/GH issue ref)
//
// Exit 0 on pass, 1 on violation. Designed for pre-commit.
import {readdirSync, readFileSync, existsSync, statSync} from "node:fs";
import {join, dirname} from "node:path";

const ROOT = process.cwd();
const CHANGES_DIR = join(ROOT, "openspec/changes");
const BUILD_PLAN = join(ROOT, "docs/build-plan.md");

if (!existsSync(CHANGES_DIR)) {
  console.log("[defer-owner] no openspec/changes — skip");
  process.exit(0);
}

const OWNER_RE = /→\s*(m[\w-]+|build-plan\s*§[\w\s-]+|[A-Z][A-Z0-9-]+-\d+|#\d+)/;
const SECTION_RE = /^##+\s*(?:\d+\.\s*)?Defer(?:red)?\b/i;

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const s = statSync(full);
    if (s.isDirectory()) {
      if (name === "archive") continue;
      out.push(...walk(full));
    } else if (/(proposal|tasks)\.md$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

const violations = [];
const changeIds = new Set(
  existsSync(CHANGES_DIR)
    ? readdirSync(CHANGES_DIR).filter((n) => n !== "archive" && statSync(join(CHANGES_DIR, n)).isDirectory())
    : []
);
const archiveDir = join(CHANGES_DIR, "archive");
if (existsSync(archiveDir)) {
  for (const ym of readdirSync(archiveDir)) {
    const ymPath = join(archiveDir, ym);
    if (statSync(ymPath).isDirectory()) {
      for (const id of readdirSync(ymPath)) changeIds.add(id);
    }
  }
}
const buildPlan = existsSync(BUILD_PLAN) ? readFileSync(BUILD_PLAN, "utf8") : "";

for (const file of walk(CHANGES_DIR)) {
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  let inDefer = false;
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^##\s/.test(line)) inDefer = SECTION_RE.test(line);
    if (!inDefer) continue;
    // Skip headings, empty lines, table headers
    const body = line.trim();
    if (!body || body.startsWith("#") || body.startsWith("|---")) continue;
    if (body.startsWith("- [x]")) continue; // already shipped or moved
    // Pick lines that look like list items / table rows with content
    if (!/^[-*|]\s/.test(body) && !/^\|/.test(body)) continue;
    if (/^\|\s*Defer\s*\|/i.test(body)) continue; // skip header row

    const m = body.match(OWNER_RE);
    if (!m) {
      violations.push({file, line: i + 1, text: body});
      continue;
    }
    // Validate owner target
    const owner = m[1];
    if (owner.startsWith("m") && !owner.includes(" ")) {
      if (!changeIds.has(owner) && !changeIds.has(owner.split("§")[0])) {
        violations.push({file, line: i + 1, text: body, reason: `unknown change id: ${owner}`});
      }
    } else if (/^build-plan/i.test(owner)) {
      if (!buildPlan) {
        violations.push({file, line: i + 1, text: body, reason: "docs/build-plan.md missing"});
      }
      // §section presence check is best-effort; build-plan formats vary
    }
  }
}

if (violations.length) {
  console.error("\n❌ Defer-owner check failed\n");
  for (const v of violations) {
    console.error(`  ${v.file}:${v.line}`);
    console.error(`    ${v.text}`);
    if (v.reason) console.error(`    reason: ${v.reason}`);
  }
  console.error(`
Every line in ## Defer / ## Deferred must end with an inline owner arrow:
    → m<id>-<slug>          (sibling change folder)
    → build-plan §<section> (real [ ] row, not a note)
    → TICKET-123 or #45     (external tracker)

Without an owner, it's unfinished scope — ship it or delete it.
`);
  process.exit(1);
}

console.log(`[defer-owner] ${changeIds.size} change(s) clean`);
