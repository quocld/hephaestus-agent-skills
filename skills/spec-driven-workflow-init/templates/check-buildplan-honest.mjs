#!/usr/bin/env node
// check-buildplan-honest.mjs · ships with spec-driven-workflow-init
//
// Reads docs/build-plan.md. For every row marked [x] in the Done column,
// verifies the linked change folder:
//   1. Exists (active or archive)
//   2. Has no unchecked [ ] in Phase B (Deliverables)
//   3. Has no Defer/Deferred lines without an owner arrow
//
// Fails if any [x] row is dishonest (a "Defer:" comment in the notes column
// of a [x] row is the canonical lie this script catches).

import {readdirSync, readFileSync, existsSync, statSync} from "node:fs";
import {join} from "node:path";

const ROOT = process.cwd();
const BUILD_PLAN = join(ROOT, "docs/build-plan.md");
const CHANGES_DIR = join(ROOT, "openspec/changes");

if (!existsSync(BUILD_PLAN)) {
  console.log("[buildplan-honest] no docs/build-plan.md — skip");
  process.exit(0);
}
if (!existsSync(CHANGES_DIR)) {
  console.log("[buildplan-honest] no openspec/changes — skip");
  process.exit(0);
}

function findChange(id) {
  const direct = join(CHANGES_DIR, id);
  if (existsSync(direct)) return direct;
  const archive = join(CHANGES_DIR, "archive");
  if (existsSync(archive)) {
    for (const ym of readdirSync(archive)) {
      const candidate = join(archive, ym, id);
      if (existsSync(candidate)) return candidate;
    }
  }
  return null;
}

const text = readFileSync(BUILD_PLAN, "utf8");
const lines = text.split("\n");
const rows = lines
  .map((l, i) => ({line: i + 1, raw: l}))
  .filter((r) => /^\|/.test(r.raw) && !/^\|\s*-{3,}/.test(r.raw));

const violations = [];

for (const {line, raw} of rows) {
  // Look for a [x] Done indicator AND a change id reference
  if (!/\[x\]/.test(raw)) continue;
  const idMatch = raw.match(/`(m[\w-]+)`/) || raw.match(/\b(m[\w-]+-[a-z][\w-]+)\b/);
  if (!idMatch) continue;
  const id = idMatch[1];
  const folder = findChange(id);
  if (!folder) {
    violations.push({line, id, reason: `change folder not found`});
    continue;
  }
  const tasks = join(folder, "tasks.md");
  if (!existsSync(tasks)) continue;
  const body = readFileSync(tasks, "utf8");

  // Phase B has unchecked items?
  const phaseB = body.match(/##\s*2\.[^\n]*Phase B[\s\S]*?(?=^##\s|\Z)/m);
  if (phaseB && /^\s*-\s*\[\s*\]/m.test(phaseB[0])) {
    violations.push({line, id, reason: `Phase B has unchecked items but build-plan shows [x]`});
  }

  // Defer without owner?
  const deferSection = body.match(/##\s*(?:\d+\.\s*)?Defer(?:red)?[\s\S]*?(?=^##\s|\Z)/im);
  if (deferSection) {
    const ownerRe = /→\s*(m[\w-]+|build-plan|[A-Z][A-Z0-9-]+-\d+|#\d+)/;
    const deferLines = deferSection[0]
      .split("\n")
      .filter((l) => /^[-*|]\s/.test(l.trim()) && !/^- \[x\]/.test(l.trim()));
    const orphan = deferLines.find((l) => !ownerRe.test(l));
    if (orphan) {
      violations.push({line, id, reason: `Defer without owner: ${orphan.trim()}`});
    }
  }
}

if (violations.length) {
  console.error("\n❌ Build-plan honesty check failed\n");
  for (const v of violations) {
    console.error(`  build-plan.md:${v.line}  [x] ${v.id}`);
    console.error(`    ${v.reason}`);
  }
  console.error(`
A [x] Done row means: zero unchecked Phase B items AND zero defer-without-owner.
If any defer remains with a named owner, the row stays [~].
If Phase B is incomplete, the row stays [ ] or [~].

Fix the tasks.md or downgrade the tick.
`);
  process.exit(1);
}

console.log(`[buildplan-honest] all [x] rows verified`);
