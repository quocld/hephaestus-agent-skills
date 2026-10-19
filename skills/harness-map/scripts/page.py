"""Shared paths, helpers and the page template for the harness map page (harness_map.py, with its Docs tab from harness_docs.py)."""
from __future__ import annotations

import base64
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


def run(cmd, cwd=None, timeout=20, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=env)
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


def load_obj(path):
    """A JSON file that must hold an object; anything else (missing, broken, a list) reads as {}."""
    data = load_json(path)
    return data if isinstance(data, dict) else {}


def _dict(x):
    return x if isinstance(x, dict) else {}


def _dicts(x):
    return [i for i in x if isinstance(i, dict)] if isinstance(x, list) else []


def _str(x, default=""):
    return x if isinstance(x, str) else (str(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else default)


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


TOKEN_LIKE = re.compile(r"^(gh[opsu]_|github_pat_|glpat-|gldt-|xox[abp]-|x-access-token)|^[A-Za-z0-9_\-]{32,}$")


def strip_userinfo(url):
    """A URL without its userinfo; (clean url, True when that userinfo can be a credential).
    Fails closed: the userinfo runs to the last @ before any ? or #, so a password holding / or @ is removed whole;
    a user part with a password, or a bare one that looks like a token, counts as a credential, while a plain
    login name (Bitbucket's https://jdoe@...) does not."""
    url = _str(url).strip()
    m = re.match(r"([a-z][a-z0-9+.-]*://)(.*)", url, re.I | re.S)
    if not m:
        return url, False
    scheme, rest = m.groups()
    cut = min([i for i in (rest.find("?"), rest.find("#")) if i != -1] or [len(rest)])
    at = rest.rfind("@", 0, cut)
    if at == -1:
        return url, False
    info = rest[:at]
    if "/" in info and ":" not in info.split("/", 1)[0]:
        return url, False   # the @ sits in the path (/@scope/pkg), not in userinfo
    secret = ":" in info or bool(TOKEN_LIKE.match(info))
    return scheme + rest[at + 1:], secret


def is_agent_skills_dir(d):
    """An agent-skills checkout or plugin folder: its manifest says so, or it has the repo's shape.
    Identifies a legacy link's target by what it holds, so it works from a plugin folder that has no git."""
    try:
        if json.loads((d / ".claude-plugin" / "plugin.json").read_text()).get("name") == "agent-skills":
            return True
    except (OSError, ValueError, AttributeError):
        pass
    return (d / "AGENTS.md").is_file() and (d / "skills" / "worktree-flow" / "SKILL.md").is_file()


def links_into_agent_skills(link, rel):
    """True when link is a symlink to <an agent-skills checkout>/<rel>, comparing path parts."""
    if not link.is_symlink():
        return False
    target = Path(os.path.realpath(link))
    parts = Path(rel).parts
    return target.exists() and target.parts[-len(parts):] == parts and is_agent_skills_dir(target.parents[len(parts) - 1])


def plugin_entry(installed, pid):
    """The newest install record for a plugin id, whether the index stores a list of records or one record."""
    v = _dict(installed).get(pid)
    if isinstance(v, list):
        return v[-1] if v and isinstance(v[-1], dict) else {}
    return v if isinstance(v, dict) else {}


VERSION_OVERRIDE = None   # set by harness_map.py --version


def release_version():
    """The plugin's release version: --version, else HARNESS_VERSION, else the newest tag reachable from HEAD
    (v1.2.0), else "dev" (a plugin install or a clone without tags)."""
    if VERSION_OVERRIDE:
        return VERSION_OVERRIDE
    if os.environ.get("HARNESS_VERSION"):
        return os.environ["HARNESS_VERSION"]
    code, out, _ = run(["git", "-C", str(REPO), "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"], timeout=10)
    return out.strip() if code == 0 and out.strip() else "dev"


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


FALLBACK_MARK = ('<span class="mark"><svg width="16" height="16" viewBox="0 0 20 20"><path d="M10 2l7 4v8l-7 4-7-4V6z" fill="none" '
                 'stroke="#fff" stroke-width="1.8"/><circle cx="10" cy="10" r="2.4" fill="#fff"/></svg></span>')


def logo_svg(prefix="hx-"):
    """The repo logo (assets/icon.svg, the one the README shows), inline so the page stays one file.
    Its ids get a prefix so they cannot clash with the page's own ids; None when the repo has no logo."""
    try:
        svg = (REPO / "assets" / "icon.svg").read_text()
    except OSError:
        return None
    svg = re.sub(r"<\?xml[^>]*>\s*", "", svg)
    for name in set(re.findall(r'\bid="([^"]+)"', svg)):
        svg = svg.replace(f'id="{name}"', f'id="{prefix}{name}"').replace(f"url(#{name})", f"url(#{prefix}{name})") \
                 .replace(f'aria-labelledby="{name}"', f'aria-labelledby="{prefix}{name}"')
    return re.sub(r'\s(width|height)="512"', "", svg, count=2)


def render_page(title, brand, crumb, body, footer, header_tools="", head=""):
    """Fill assets/template.html; every page shares its header, theme switch, tokens and scripts."""
    out = TEMPLATE.read_text()
    logo = logo_svg()
    mark = f'<span class="logo" aria-hidden="true">{logo}</span>' if logo else FALLBACK_MARK
    favicon = ('<link rel="icon" type="image/svg+xml" href="data:image/svg+xml;base64,'
               + base64.b64encode(logo_svg("f-").encode()).decode() + '">') if logo else ""
    for key, val in (("mark", mark), ("favicon", favicon), ("head", head), ("title", esc(title)), ("brand", esc(brand)), ("crumb", esc(crumb)),
                     ("header_tools", header_tools), ("footer", footer), ("body", body)):
        out = out.replace("{{" + key + "}}", val)
    return out


# ---------------------------------------------------------------- harness wheel (assets/pillars.json)


PILLARS = (load_json(SKILL / "assets" / "pillars.json") or {}).get("pillars", [])
# Ultimate skills run a whole workflow end to end and orchestrate other skills; every page draws their name in the
# animated gradient (class "ult" in HTML, fill url(#ult-grad) in SVG, both defined in assets/template.html).
ULTIMATE = {n for n, s_ in ((load_json(SKILL / "assets" / "lifecycle.json") or {}).get("skills") or {}).items() if s_.get("ultimate")}


SKILL_NAMES = {d.name for d in SKILLS_DIR.iterdir() if (d / "SKILL.md").exists()} if SKILLS_DIR.is_dir() else set()


def ult(name, text=None):
    """A skill name (or text) as HTML: the ultimate effect for ultimate skills, and for every skill of this repo a
    button that opens it in the skill reader (data-skill, handled in assets/template.html)."""
    t = esc(name if text is None else text)
    if name in ULTIMATE:
        t = f'<span class="ult">{t}</span>'
    if name in SKILL_NAMES:
        return f'<span class="skl" data-skill="{esc(name)}" role="button" tabindex="0" title="Read {esc(name)}">{t}</span>'
    return t


# ---------------------------------------------------------------- skill reader

def _inline(s):
    """Inline markdown on already-escaped text: code spans first (left as is), then bold, italics and http(s) links."""
    parts = re.split(r"(`[^`]+`)", s)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{part[1:-1]}</code>")
            continue
        part = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", part)
        part = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", part)
        part = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', part)
        out.append(part)
    return "".join(out)


def render_markdown(md):
    """A small, safe markdown renderer for SKILL.md files: every byte is HTML-escaped before any markup is added.
    Handles headings, paragraphs, fenced code, pipe tables, block quotes and nested lists."""
    lines = esc(md).split("\n")
    out, para, i = [], [], 0

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(x.strip() for x in para)) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            flush()
            code, indent = [], len(line) - len(line.lstrip(" "))   # a fence inside a list item: drop the item's indent
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i][indent:] if lines[i][:indent].strip() == "" else lines[i])
                i += 1
            out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            level = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            flush()
            cells = lambda row: [c.strip() for c in row.strip().strip("|").split("|")]
            head = "".join(f"<th>{_inline(c)}</th>" for c in cells(line))
            i += 2
            body = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                body.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells(lines[i])) + "</tr>")
                i += 1
            out.append(f'<div class="rtable"><table><tr>{head}</tr>{"".join(body)}</table></div>')
            continue
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            flush()
            # A list block: indentation decides nesting; continuation lines join the item above.
            items = []
            while i < len(lines) and (re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]) or (lines[i].startswith("  ") and lines[i].strip() and items
                                                                                           and not lines[i].strip().startswith("```"))):
                lm = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", lines[i])
                if lm:
                    items.append([len(lm.group(1)) // 2, lm.group(2)[-1] == ".", lm.group(3)])
                else:
                    items[-1][2] += " " + lines[i].strip()
                i += 1
            html_, stack = [], []
            for depth, ordered, text in items:
                tag = "ol" if ordered else "ul"
                while len(stack) > depth + 1:
                    html_.append(f"</li></{stack.pop()}>")
                if len(stack) == depth + 1 and stack[-1] != tag:   # bullets then numbers at one level: two lists
                    html_.append(f"</li></{stack.pop()}>")
                if len(stack) < depth + 1:
                    while len(stack) < depth + 1:
                        html_.append(f"<{tag}>")
                        stack.append(tag)
                else:
                    html_.append("</li>")
                html_.append(f"<li>{_inline(text)}")
            while stack:
                html_.append(f"</li></{stack.pop()}>")
            out.append("".join(html_))
            continue
        if line.startswith("&gt;"):
            flush()
            quote = []
            while i < len(lines) and lines[i].startswith("&gt;"):
                quote.append(lines[i][4:].strip())
                i += 1
            out.append("<blockquote>" + _inline(" ".join(quote)) + "</blockquote>")
            continue
        if not line.strip():
            flush()
        else:
            para.append(line)
        i += 1
    flush()
    return "".join(out)


def skill_doc(d, fm, title_tag="h2"):
    """(header html, article html) for one skill: tier, ultimate, how it loads, lifecycle, files, then SKILL.md."""
    life = (load_json(SKILL / "assets" / "lifecycle.json") or {}).get("skills") or {}
    events = (load_json(SKILL / "assets" / "lifecycle.json") or {}).get("events") or {}
    try:
        text = (d / "SKILL.md").read_text(errors="replace")
    except OSError:
        return None
    body = re.sub(r"^---\n.*?\n---\n?", "", text, count=1, flags=re.S)
    body = re.sub(rf"^\s*#\s+{re.escape(d.name)}\s*\n", "", body, count=1)   # the header already names the skill
    meta = life.get(d.name) or {}
    tier = meta.get("tier", "optional")
    chips = [f'<span class="tier {esc(tier)}">{"Core" if tier == "core" else "Optional"}</span>']
    if d.name in ULTIMATE:
        chips.append('<span class="chip ultchip"><span class="ult">ultimate</span></span>')
    inv = str(fm.get("user-invocable", "")).lower() == "true"
    chips.append(f'<span class="chip acc">/{esc(d.name)}</span>' if inv else '<span class="chip agent">loads by description</span>')
    chips += [f'<span class="chip">{esc((events.get(e) or {}).get("label", e))}</span>' for e in meta.get("events", [])]
    files = sorted(str(p.relative_to(d)) for p in d.rglob("*") if p.is_file() and p.name != "SKILL.md" and "__pycache__" not in p.parts)
    extra = ('<div class="rfiles"><span>Also in this skill:</span> ' + " ".join(f'<code>{esc(f)}</code>' for f in files) + "</div>") if files else ""
    when = f'<p class="rwhen">{esc(meta["when"])}</p>' if meta.get("when") else ""
    name = f'<span class="ult">{esc(d.name)}</span>' if d.name in ULTIMATE else esc(d.name)
    head = (f'<div class="rmeta"><{title_tag} class="rtitle">{name}</{title_tag}><div class="chips">{"".join(chips)}</div>'
            f'<p class="rdesc">{_inline(esc(fm.get("description", "")))}</p>{when}{extra}</div>')
    return head, f'<article class="md">{render_markdown(body)}</article>'


def skill_sources():
    """One hidden <template> per repo skill, holding its rendered SKILL.md for the skill reader."""
    out = []
    for d, fm in repo_skills():
        doc = skill_doc(d, fm)
        if doc:
            out.append(f'<template id="skill-src-{esc(d.name)}">{doc[0]}{doc[1]}</template>')
    return '<div hidden>' + "".join(out) + '</div>'


WHEEL_FILL = {"ok": ("var(--ok-soft)", "var(--ok)"), "warn": ("var(--warn-soft)", "var(--warn)"),
              "fail": ("var(--bad-soft)", "var(--bad)"), None: ("var(--accent-soft)", "var(--accent)")}
BAD_FILL = ' style="fill:var(--bad-text)"'
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
    GAP = 8   # px between neighbouring slices, the same at every radius
    n = len(PILLARS) or 1
    step = 360 / n
    p = [f'<svg viewBox="0 0 {S} {S}" class="wheel" role="img" aria-label="Agent harness: {n} components">']
    for i, pl in enumerate(PILLARS):
        # Each side is the radial line moved GAP/2 sideways, so the gap between slices keeps one width from
        # the inner ring to the outer one (an angular offset would make it a wedge that widens outwards).
        a0, a1 = -90 - step / 2 + i * step, -90 + step / 2 + i * step
        off_out, off_in = math.degrees(math.asin(GAP / 2 / R)), math.degrees(math.asin(GAP / 2 / r))
        x0, y0 = _polar(cx, cy, R, a0 + off_out)
        x1, y1 = _polar(cx, cy, R, a1 - off_out)
        x2, y2 = _polar(cx, cy, r, a1 - off_in)
        x3, y3 = _polar(cx, cy, r, a0 + off_in)
        st = status.get(pl["id"])
        fill, stroke = WHEEL_FILL[st]
        mid = (a0 + a1) / 2
        tx, ty = _polar(cx, cy, (R + r) / 2, mid)
        words = pl["short"].replace(" & ", " &\n").split("\n")
        lines = "".join(f'<tspan x="{tx:.1f}" dy="{0 if k == 0 else 15}">{esc(w)}</tspan>' for k, w in enumerate(words))
        word = WHEEL_WORD[st] + (" · setup" if alerts.get(pl["id"]) else "") if st else ""
        sub = (f'<text x="{tx:.1f}" y="{ty + 16 + 15 * (len(words) - 1):.1f}" class="wsub" text-anchor="middle"'
               f'{BAD_FILL if alerts.get(pl["id"]) else ""}>{esc(word)}</text>') if st else ""
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
            f'<span class="chip {"acc" if installed is None or installed.get(s) else "bad"}">{ult(s)}</span>' for s in cov.get("skills", []))
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
