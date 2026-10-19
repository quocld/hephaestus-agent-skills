"""Shared paths, helpers and the page template for harness-map's generators (harness_map.py, harness_docs.py)."""
from __future__ import annotations

import html
import json
import math
import os
import re
import subprocess
from pathlib import Path

HOME = Path.home()
CLAUDE = Path(os.environ.get("CLAUDE_DIR", HOME / ".claude"))
SKILL = Path(__file__).resolve().parents[1]
REPO = SKILL.parents[1]
SKILLS_DIR = REPO / "skills"
TEMPLATE = SKILL / "assets" / "template.html"

# Ranked by how much each status blocks work; drives sorting and scores.
RANK = {"fail": 0, "missing": 1, "warn": 2, "ok": 3, "info": 4, "skip": 5}
LABEL = {"fail": "Failing", "missing": "Missing", "warn": "Attention", "ok": "OK", "info": "Info", "skip": "Skipped"}

ICONS = {
    "Global instructions": '<path d="M4 4h12v12H4z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 8h6M7 11h4" stroke="currentColor" stroke-width="1.6"/>',
    "Skills": '<path d="M10 3l6 3.5v7L10 17l-6-3.5v-7z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Hooks": '<path d="M7 4v6a3 3 0 006 0V8" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="13" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Tools": '<path d="M4 6l4 4-4 4M10 14h6" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Plugins & MCP": '<path d="M8 3v4M12 3v4M6 7h8v3a4 4 0 01-8 0zM10 14v3" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Settings hygiene": '<path d="M10 3l6 2.5V10c0 3.5-2.6 6-6 7-3.4-1-6-3.5-6-7V5.5z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Project": '<path d="M3 6h5l2 2h7v8H3z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Flow": '<path d="M3 10h4l2-5 2 10 2-5h4" fill="none" stroke="currentColor" stroke-width="1.6"/>',
}


def run(cmd, cwd=None, timeout=20):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


def _main_checkout():
    """The repo's main worktree, so fix commands never point at a throwaway task worktree."""
    code, so, _ = run(["git", "-C", str(REPO), "worktree", "list", "--porcelain"], timeout=10)
    first = so.split("\n", 1)[0]
    return Path(first[len("worktree "):]) if code == 0 and first.startswith("worktree ") else REPO


MAIN = _main_checkout()


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def frontmatter(path):
    """Parse the small YAML subset skills use: scalars and folded `>` blocks."""
    try:
        text = path.read_text()
    except OSError:
        return None
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return None
    out, key = {}, None
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip()
            out[key] = "" if val in (">", "|", ">-", "|-") else val.strip("\"'")
        elif key and line.startswith(" "):
            out[key] = (out[key] + " " + line.strip()).strip()
    return out


def repo_skills():
    """Every skill folder in this repo with its parsed frontmatter ({} when unreadable)."""
    return [(d, frontmatter(d / "SKILL.md") or {}) for d in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())]


def short(p):
    s = str(p)
    return "~" + s[len(str(HOME)):] if s.startswith(str(HOME)) else s


def esc(s):
    return html.escape(str(s), quote=True)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def icon(name):
    return f'<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true">{ICONS.get(name, "")}</svg>'


def pill(s):
    return f'<span class="pill {s}"><span class="dot {s}"></span>{LABEL[s]}</span>'


def render_page(title, brand, crumb, body, footer, header_tools=""):
    """Fill assets/template.html; every page shares its header, theme switch, tokens and scripts."""
    out = TEMPLATE.read_text()
    for key, val in (("title", esc(title)), ("brand", esc(brand)), ("crumb", esc(crumb)),
                     ("header_tools", header_tools), ("footer", footer), ("body", body)):
        out = out.replace("{{" + key + "}}", val)
    return out


# ---------------------------------------------------------------- harness wheel (assets/pillars.json)


PILLARS = (load_json(SKILL / "assets" / "pillars.json") or {}).get("pillars", [])
WHEEL_FILL = {"ok": ("var(--ok-soft)", "var(--ok)"), "warn": ("var(--warn-soft)", "var(--warn)"),
              "fail": ("var(--bad-soft)", "var(--bad)"), None: ("var(--accent-soft)", "var(--accent)")}
WHEEL_WORD = {"ok": "Covered", "warn": "Partial", "fail": "Gaps"}  # designed coverage; setup problems are a separate alert


def _polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def wheel_svg(status=None, center=("Agent Harness", "8 components"), alerts=None):
    """Donut of the eight pillars, pillar 1 at the top, clockwise; hovering a slice shows its card in the popover.
    status maps pillar id to ok/warn (designed coverage); None draws every slice in the accent tint.
    alerts marks pillars whose pieces are not set up on this machine with a red badge."""
    status, alerts = status or {}, alerts or {}
    S, cx, cy, R, r = 560, 280, 280, 250, 118
    n = len(PILLARS) or 1
    step = 360 / n
    p = [f'<svg viewBox="0 0 {S} {S}" class="wheel" role="img" aria-label="Agent harness: {n} components">']
    for i, pl in enumerate(PILLARS):
        a0, a1 = -90 - step / 2 + i * step + 1.2, -90 + step / 2 + i * step - 1.2
        x0, y0 = _polar(cx, cy, R, a0)
        x1, y1 = _polar(cx, cy, R, a1)
        x2, y2 = _polar(cx, cy, r, a1)
        x3, y3 = _polar(cx, cy, r, a0)
        st = status.get(pl["id"])
        fill, stroke = WHEEL_FILL[st]
        mid = (a0 + a1) / 2
        tx, ty = _polar(cx, cy, (R + r) / 2, mid)
        words = pl["short"].replace(" & ", " &\n").split("\n")
        lines = "".join(f'<tspan x="{tx:.1f}" dy="{0 if k == 0 else 15}">{esc(w)}</tspan>' for k, w in enumerate(words))
        word = WHEEL_WORD[st] + (" · setup" if alerts.get(pl["id"]) else "") if st else ""
        sub = (f'<text x="{tx:.1f}" y="{ty + 16 + 15 * (len(words) - 1):.1f}" class="wsub" text-anchor="middle"'
               f'{" style=\"fill:var(--bad-text)\"" if alerts.get(pl["id"]) else ""}>{esc(word)}</text>') if st else ""
        p.append(f'<g class="slice" data-pillar="{pl["id"]}" tabindex="0" role="button" aria-label="{pl["no"]}. {esc(pl["name"])}">'
                 f'<path d="M{x0:.1f} {y0:.1f} A{R} {R} 0 0 1 {x1:.1f} {y1:.1f} L{x2:.1f} {y2:.1f} A{r} {r} 0 0 0 {x3:.1f} {y3:.1f}Z" '
                 f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>'
                 f'<circle cx="{tx:.1f}" cy="{ty - 26:.1f}" r="11" fill="{"var(--bad)" if alerts.get(pl["id"]) else stroke}"/>'
                 f'<text x="{tx:.1f}" y="{ty - 22:.1f}" class="wno" text-anchor="middle">{pl["no"]}</text>'
                 f'<text x="{tx:.1f}" y="{ty + 1:.1f}" class="wname" text-anchor="middle">{lines}</text>{sub}</g>')
    p.append(f'<circle cx="{cx}" cy="{cy}" r="{r - 14}" fill="var(--surface)" stroke="var(--border-2)"/>'
             f'<text x="{cx}" y="{cy - 4}" class="wc1" text-anchor="middle">{esc(center[0])}</text>'
             f'<text x="{cx}" y="{cy + 20}" class="wc2" text-anchor="middle">{esc(center[1])}</text></svg>')
    return "".join(p)


def pillar_cards(status=None, related=None, installed=None, alerts=None):
    """One hidden card per pillar (definition, what this harness has, what is missing), shown in the
    wheel popover on hover. related maps pillar id to failing check titles; installed maps skill name to True/False."""
    status, related, installed, alerts = status or {}, related or {}, installed, alerts or {}
    out = ['<div class="pillar-src" hidden>']
    for pl in PILLARS:
        st = status.get(pl["id"])
        cov = pl["covered_by"]
        badge = f'<span class="pill {st}">{WHEEL_WORD[st]}</span>' if st else ""
        if alerts.get(pl["id"]):
            badge += '<span class="pill fail">Setup needed</span>'
        if pl.get("badge"):
            badge = f'<span class="tier core">{esc(pl["badge"])}</span>' + badge
        skill_chips = "".join(
            f'<span class="chip {"acc" if installed is None or installed.get(s) else "bad"}">{esc(s)}</span>' for s in cov.get("skills", []))
        file_chips = "".join(f'<span class="chip">{esc(f)}</span>' for f in cov.get("files", []))
        missing = list(related.get(pl["id"], [])) + pl.get("gaps", [])
        miss = ("<ul class='miss'>" + "".join(f"<li>{esc(m)}</li>" for m in missing) + "</ul>") if missing else '<p class="none">Nothing known missing.</p>'
        points = "".join(f"<li>{esc(x)}</li>" for x in pl["points"])
        principle = f'<p class="principle">{esc(pl["principle"])}</p>' if pl.get("principle") else ""
        out.append(f'<article class="pillar" id="pillar-src-{pl["id"]}" data-s="{st or ""}"><div class="ph"><span class="pno">{pl["no"]}</span>'
                   f'<h3>{esc(pl["name"])}</h3><span class="sp"></span>{badge}</div><p class="lead">{esc(pl["lead"])}</p>'
                   f'<div class="lbl2">In this harness</div><div class="chips">{skill_chips}{file_chips}</div>'
                   f'<div class="lbl2">Missing</div>{miss}'
                   f'<div class="lbl2">What it covers</div><ul>{points}</ul>{principle}</article>')
    out.append('</div>')
    return "".join(out)
