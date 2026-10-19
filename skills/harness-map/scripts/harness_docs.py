#!/usr/bin/env python3
"""Write the harness docs page: the harness wheel, where each skill and hook sits in the Claude Code lifecycle, and the task path.

Skill placement comes from assets/lifecycle.json; hooks are read live from settings and enabled plugins.
Read-only, like harness_map.py. Usage: python3 harness_docs.py [--out FILE] [--open]
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import socket
import sys
from pathlib import Path

from page import CLAUDE, PILLARS, REPO, SKILL, esc, icon, load_json, pillar_cards, render_page, repo_skills, run, short, wheel_svg

LIFE = load_json(SKILL / "assets" / "lifecycle.json")


# ---------------------------------------------------------------- live hooks

def hook_source(cmd):
    """Name who owns a hook command: one of this repo's scripts, a plugin, or a custom command."""
    m = re.search(r"agent-skills-hooks/([\w-]+)\.py", cmd)
    if m:
        return "gate", m.group(1)
    m = re.search(r"plugins/cache/[^/]+/([^/]+)/", cmd)
    if m:
        return "plugin", m.group(1)
    return "custom", (cmd.split()[0] if cmd.split() else "command")[-28:]


def live_hooks():
    """[(event, matcher, kind, name, where)] from settings files and enabled plugins' hooks.json."""
    rows = []
    for fname in ("settings.json", "settings.local.json"):
        for event, entries in ((load_json(CLAUDE / fname) or {}).get("hooks") or {}).items():
            for e in entries:
                for h in e.get("hooks", []):
                    kind, name = hook_source(h.get("command", ""))
                    rows.append((event, e.get("matcher") or "*", kind, name, fname))
    settings = load_json(CLAUDE / "settings.json") or {}
    installed = (load_json(CLAUDE / "plugins" / "installed_plugins.json") or {}).get("plugins", {})
    for pid, on in (settings.get("enabledPlugins") or {}).items():
        if not on:
            continue
        path = Path((installed.get(pid) or [{}])[-1].get("installPath", ""))
        data = load_json(path / "hooks" / "hooks.json") or {}
        for event, entries in (data.get("hooks", data) or {}).items():
            if isinstance(entries, list):
                for e in entries:
                    rows.append((event, e.get("matcher") or "*", "plugin", pid.split("@")[0], "plugin " + pid.split("@")[0]))
    # Settings entries that only launch a plugin's own runner duplicate the plugin row; keep one per (event, name).
    seen, out = set(), []
    for r in rows:
        key = (r[0], r[3])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------- lifecycle svg

ROWS = ["session_start", "prompt", "pre_tool", "permission", "tool", "post_tool", "post_batch", "subagent",
        "task_created", "task_completed", "stop", "teammate_idle", "pre_compact", "post_compact", "session_end"]
Y = {"session_start": 30, "prompt": 110}
for i, r in enumerate(ROWS[2:10]):
    Y[r] = 200 + i * 70
Y.update({"stop": 790, "teammate_idle": 880, "pre_compact": 950, "post_compact": 1020, "session_end": 1090})
NODE_H = 40
MX, MW = 200, 220           # main column
CX, CR = 490, 1048          # chip column start and right edge
SX, SW = 14, 150            # side events
FILL = {"session_start": ("var(--ok-soft)", "var(--ok)", "var(--ok-text)"),
        "tool": ("var(--accent)", "var(--accent)", "#fff"),
        "stop": ("var(--bad-soft)", "var(--bad)", "var(--bad-text)")}
LOOP_FILL = ("var(--warn-soft)", "var(--warn)", "var(--text)")
PLAIN_FILL = ("var(--surface-3)", "var(--border-2)", "var(--text)")
CHIP = {"skill": ("var(--accent-soft)", "var(--accent-text)"), "gate": ("var(--bad-soft)", "var(--bad-text)"),
        "plugin": ("var(--surface-3)", "var(--muted)"), "custom": ("var(--surface-3)", "var(--muted)")}


def text(x, y, s, cls="", anchor="start", extra=""):
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" class="{cls}" {extra}>{esc(s)}</text>'


def chips_for(row, hooks):
    events = LIFE["events"][row]["hooks"]
    items = [("skill", n) for n, s in LIFE["skills"].items() if row in s["events"]]
    names = []
    for ev, _, kind, name, _ in hooks:
        if ev in events and (kind, name) not in names:
            names.append((kind, name))
    items += [(k, ("hook " if k == "gate" else "") + n) for k, n in names]
    return items


def chip_rows(items, x0, x1, char_w=6.3):
    """Greedy line wrap of chips into [(kind, label, x, width)] per line."""
    lines, cur, x = [], [], x0
    for kind, label in items:
        w = round(len(label) * char_w + 16)
        if cur and x + w > x1:
            lines.append(cur)
            cur, x = [], x0
        cur.append((kind, label, x, w))
        x += w + 6
    if cur:
        lines.append(cur)
    return lines


def lifecycle_svg(hooks):
    W, H = 1060, 1160
    p = [f'<svg viewBox="0 0 {W} {H}" class="life" role="img" aria-label="Claude Code lifecycle with skills and hooks">',
         '<defs>'
         '<marker id="a-g" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="var(--muted)"/></marker>'
         '<marker id="a-o" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="#d08a5c"/></marker>'
         '<marker id="a-b" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8z" fill="#3b82c4"/></marker>'
         '</defs>']
    cy = lambda r: Y[r] + NODE_H / 2

    # Column headings.
    for x, label in ((SX, "Side events"), (MX, "Lifecycle"), (CX, "Skills and hooks that act here")):
        p.append(text(x, 14, label, "lbl"))

    # Each-turn (blue) and agentic-loop (orange) frames.
    p.append(f'<rect x="176" y="96" width="282" height="752" rx="12" fill="none" stroke="#3b82c4" stroke-width="1.6" stroke-dasharray="6 5"/>')
    p.append(text(186, 838, "EACH TURN", "frame", extra='fill="#3b82c4"'))
    p.append(f'<rect x="188" y="164" width="258" height="586" rx="10" fill="none" stroke="#d08a5c" stroke-width="1.6" stroke-dasharray="6 5"/>')
    p.append(text(198, 186, "AGENTIC LOOP", "frame", extra='fill="#d08a5c"'))

    # Main spine arrows.
    for a, b in zip(ROWS, ROWS[1:]):
        p.append(f'<path d="M{MX + MW / 2} {Y[a] + NODE_H} V{Y[b] - 2}" stroke="var(--muted)" stroke-width="1.6" marker-end="url(#a-g)"/>')
    # Agentic loop back edge and each-turn back edge.
    p.append(f'<path d="M{MX + MW} {cy("task_completed")} H436 V{cy("pre_tool")} H{MX + MW + 2}" fill="none" stroke="#d08a5c" stroke-width="1.6" marker-end="url(#a-o)"/>')
    p.append(f'<path d="M{MX + MW} {cy("stop")} H452 V{cy("prompt")} H{MX + MW + 2}" fill="none" stroke="#3b82c4" stroke-width="1.6" marker-end="url(#a-b)"/>')
    # Resumed sessions.
    p.append(f'<path d="M{MX} {cy("session_end")} H168 V{cy("session_start")} H{MX - 2}" fill="none" stroke="var(--text-2)" stroke-width="1.6" stroke-dasharray="6 5" marker-end="url(#a-g)"/>')
    p.append(f'<text x="160" y="{(cy("session_start") + cy("session_end")) / 2}" class="lbl" transform="rotate(-90 160 {(cy("session_start") + cy("session_end")) / 2})" text-anchor="middle">resumed sessions</text>')

    # Side events.
    for s in LIFE["side"]:
        y = Y[s["row"]]
        stroke = "var(--accent)" if s["skills"] else "var(--border-2)"
        p.append(f'<rect x="{SX}" y="{y - 4}" width="{SW - 10}" height="{NODE_H + 8}" rx="7" fill="var(--surface)" stroke="{stroke}" stroke-dasharray="4 3"/>')
        p.append(text(SX + (SW - 10) / 2, y + 13, s["label"], "side", "middle"))
        sub = ", ".join(s["skills"]) if s["skills"] else s["sub"]
        p.append(text(SX + (SW - 10) / 2, y + 29, sub, "skillsub" if s["skills"] else "sub", "middle"))
        if s["arrow"]:
            p.append(f'<path d="M{SX + SW - 8} {y + NODE_H / 2} H{176 if s["row"] != "session_start" else MX - 4}" stroke="var(--muted)" stroke-width="1.2" stroke-dasharray="4 3" marker-end="url(#a-g)"/>')

    # Main nodes and the chips that act at each.
    for r in ROWS:
        y, label = Y[r], LIFE["events"][r]["label"]
        in_loop = ROWS.index("pre_tool") <= ROWS.index(r) <= ROWS.index("task_completed")
        fill, stroke, ink = FILL.get(r, LOOP_FILL if in_loop else PLAIN_FILL)
        p.append(f'<rect x="{MX}" y="{y}" width="{MW}" height="{NODE_H}" rx="8" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        p.append(text(MX + MW / 2, y + 25, label, "node", "middle", f'style="fill:{ink}"'))

        chips = chips_for(r, HOOKS)
        if chips:
            lines = chip_rows(chips, CX, CR)
            top = y + NODE_H / 2 - (len(lines) * 22 - 4) / 2
            p.append(f'<path d="M{MX + MW} {y + NODE_H / 2} H{CX - 6}" stroke="var(--border-2)" stroke-width="1.2" stroke-dasharray="3 3"/>')
            for li, line in enumerate(lines):
                for kind, lab, x, w in line:
                    bg, fg = CHIP[kind]
                    yy = top + li * 22
                    p.append(f'<rect x="{x}" y="{yy}" width="{w}" height="18" rx="5" fill="{bg}"/>')
                    p.append(f'<text x="{x + w / 2}" y="{yy + 12.5}" text-anchor="middle" class="chip-t" style="fill:{fg}">{esc(lab)}</text>')
    p.append('</svg>')
    return "".join(p)


# ---------------------------------------------------------------- task path svg

def task_path_svg():
    """Prompt -> agentic loop (gather, act, verify, retry) -> response -> back to the next prompt,
    with each skill placed on the step where it comes into play (assets/lifecycle.json `path`)."""
    W, H, NY, NH = 1280, 500, 262, 62
    CW, CH, GAP = 7.4, 21, 27   # chip char width, chip height, chip row pitch (larger text than the lifecycle map)
    nodes = {"setup": (16, 150), "prompt": (196, 180), "gather": (432, 180), "act": (646, 180),
             "verify": (860, 180), "response": (1080, 184)}
    look = {"setup": ("var(--surface)", "var(--border-2)", "5 4"), "prompt": ("var(--surface-3)", "none", ""),
            "response": ("var(--surface-3)", "none", ""), "gather": ("var(--ok-soft)", "none", ""),
            "act": ("var(--ok-soft)", "none", ""), "verify": ("var(--accent-soft)", "none", "")}
    path = LIFE["path"]
    skills_at = lambda step: [("skill", n) for n, sk in LIFE["skills"].items() if step in sk["path"]] + \
                             [("plugin", f) for f in path[step]["files"]]
    cx = lambda k: nodes[k][0] + nodes[k][1] / 2
    mid = NY + NH / 2
    p = [f'<svg viewBox="0 0 {W} {H}" class="life tp" role="img" aria-label="Task path through the agentic loop">',
         '<defs><marker id="t-a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0L8 4L0 8z" fill="var(--muted)"/></marker></defs>']

    def chips_line(items, center, y):
        """One centered row of chips; returns its svg and width."""
        widths = [round(len(lab) * CW + 16) for _, lab in items]
        total = sum(widths) + 6 * (len(items) - 1)
        x, out = center - total / 2, []
        for (kind, lab), w in zip(items, widths):
            bg, fg = CHIP[kind]
            out.append(f'<rect x="{x:.1f}" y="{y}" width="{w}" height="{CH}" rx="5" fill="{bg}"/>'
                       f'<text x="{x + w / 2:.1f}" y="{y + 14.5}" text-anchor="middle" class="chip-t" style="fill:{fg}">{esc(lab)}</text>')
            x += w + 6
        return "".join(out), total

    def chips_above(step):
        x, w = nodes[step]
        lines = chip_rows(skills_at(step), 0, w + 30, CW)
        for k, line in enumerate(lines):
            y = NY - 14 - (len(lines) - k) * GAP
            p.append(chips_line([(kind, lab) for kind, lab, _, _ in line], x + w / 2, y)[0])

    def label_on_line(text_, step, cxv, y):
        """Text ends where the chips start, so the gap is exact whatever the font measures."""
        items = skills_at(step)
        tw = len(text_) * 7.2  # generous estimate, only used for the mask behind the label
        _, cw = chips_line(items, 0, 0)
        join = cxv - cw / 2 + tw / 2
        p.append(f'<rect x="{join - tw - 18:.1f}" y="{y - 14}" width="{tw + cw + 36:.1f}" height="28" fill="var(--surface)"/>')
        p.append(f'<text x="{join - 8:.1f}" y="{y + 4.5}" text-anchor="end" class="tl">{esc(text_)}</text>')
        p.append(chips_line(items, join + cw / 2, y - CH / 2)[0])

    # Agentic loop frame with its label sitting in a gap of the dashed line.
    bx, by, bw, bh = 404, 40, 646, 376
    p.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6" fill="none" stroke="var(--border-3, var(--muted))" stroke-width="1.5" stroke-dasharray="5 5"/>')
    p.append(f'<rect x="{bx + bw - 160}" y="{by - 13}" width="140" height="26" fill="var(--surface)"/>')
    p.append(f'<text x="{bx + bw - 90}" y="{by + 6}" text-anchor="middle" class="tframe">Agentic loop</text>')

    # Forward arrows.
    order = ["setup", "prompt", "gather", "act", "verify", "response"]
    for a, b in zip(order, order[1:]):
        x1 = nodes[a][0] + nodes[a][1] + 6
        x2 = nodes[b][0] - 6
        dash = ' stroke-dasharray="5 4"' if a == "setup" else ""
        p.append(f'<path d="M{x1} {mid} H{x2}" stroke="var(--muted)" stroke-width="1.6"{dash} marker-end="url(#t-a)"/>')
    # Verify fails: back to gather. Response: back to the next prompt.
    p.append(f'<path d="M{cx("verify")} {NY + NH + 4} V364 Q{cx("verify")} 372 {cx("verify") - 8} 372 H{cx("gather") + 8} '
             f'Q{cx("gather")} 372 {cx("gather")} 364 V{NY + NH + 8}" fill="none" stroke="var(--muted)" stroke-width="1.6" marker-end="url(#t-a)"/>')
    p.append(f'<path d="M{cx("response")} {NY + NH + 4} V462 Q{cx("response")} 470 {cx("response") - 8} 470 H{cx("prompt") + 8} '
             f'Q{cx("prompt")} 470 {cx("prompt")} 462 V{NY + NH + 8}" fill="none" stroke="var(--muted)" stroke-width="1.6" marker-end="url(#t-a)"/>')
    label_on_line(path["retry"]["label"], "retry", (cx("gather") + cx("verify")) / 2, 372)
    label_on_line(path["remember"]["label"], "remember", (cx("prompt") + cx("response")) / 2, 470)

    # Nodes and the skills that act at each.
    for k in order:
        x, w = nodes[k]
        fill, stroke, dash = look[k]
        p.append(f'<rect x="{x}" y="{NY}" width="{w}" height="{NH}" rx="7" fill="{fill}" stroke="{stroke}"'
                 f'{f" stroke-dasharray=\"{dash}\"" if dash else ""}/>')
        p.append(text(x + w / 2, NY + 28, path[k]["label"], "tn", "middle"))
        p.append(text(x + w / 2, NY + 47, path[k]["sub"], "tsub", "middle"))
        chips_above(k)
    p.append('</svg>')
    return "".join(p)


# ---------------------------------------------------------------- page

DOC_CSS = """<style>
.life{display:block;width:100%;height:auto}
.life text{font-family:Inter,ui-sans-serif,system-ui,sans-serif;fill:var(--text)}
.life .lbl{font-size:10.5px;fill:var(--muted);letter-spacing:.06em;text-transform:uppercase;font-weight:600}
.life .frame{font-size:12px;font-weight:700;letter-spacing:.12em}
.life .node{font-size:12.5px;font-weight:600}
.life .side{font-size:11px;font-weight:600;fill:var(--text-2)}
.life .sub{font-size:10px;fill:var(--muted)}
.life .skillsub{font-size:10px;fill:var(--accent-text);font-weight:600}
.life .chip-t{font-family:"Azeret Mono",ui-monospace,monospace;font-size:10.5px}
.scroll{overflow-x:auto;padding:18px}
.scroll .life{min-width:760px}
.legend{display:flex;flex-wrap:wrap;gap:14px;padding:0 18px 16px;color:var(--muted);font-size:12px}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:14px;height:10px;border-radius:3px;display:inline-block}
.life .tn{font-family:"Host Grotesk",Inter,sans-serif;font-size:18px;font-weight:500}
.life .tsub{font-size:12px;fill:var(--muted)}
.life .tl{font-size:12.5px;fill:var(--muted);font-weight:500}
.life .tframe{font-family:"Host Grotesk",Inter,sans-serif;font-size:17px;fill:var(--muted)}
.tp .chip-t{font-size:12px}
.prose{padding:16px 18px;color:var(--text-2);max-width:820px}
.prose p{margin:0 0 10px}.prose ul{margin:0 0 10px;padding-left:18px}.prose li{margin:3px 0}
table.t{width:100%;border-collapse:collapse;font-size:13px}
table.t th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;padding:10px 18px;border-bottom:1px solid var(--border);background:var(--surface-2)}
table.t td{padding:10px 18px;border-top:1px solid var(--border);vertical-align:top;color:var(--text-2)}
table.t td:first-child{color:var(--text);font-weight:500;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:28px}
@media (max-width:900px){.kpis{grid-template-columns:1fr 1fr}
table.t td:first-child{white-space:normal}}
</style>"""


def card(id_, ic, title, desc, inner):
    return (f'<section class="card" id="{id_}"><div class="hd">{icon(ic)}<h2>{esc(title)}</h2>'
            f'<span class="desc">{esc(desc)}</span></div>{inner}</section>')


def render(hooks, version, now):
    skills = repo_skills()
    meta = {d.name: fm for d, fm in skills}
    unmapped = [n for n in meta if n not in LIFE["skills"]]
    stale = [n for n in LIFE["skills"] if n not in meta]
    _, sha, _ = run(["git", "-C", str(REPO), "log", "-1", "--format=%h"])
    ours = sorted({n for _, _, k, n, _ in hooks if k == "gate"})
    plugins = sorted({n for _, _, k, n, _ in hooks if k == "plugin"})

    h = [DOC_CSS]
    h.append(f'<div class="hero"><div><div class="eyebrow">Harness docs {esc(version)}</div><h1>How this harness is built</h1>'
             '<p class="sub">The eight components of an agent harness and what this repo puts in each, the Claude Code lifecycle '
             'redrawn with every skill and hook, and the path a normal task takes through them.</p>'
             f'<div class="meta"><span>Generated <b>{now}</b></span><span>Repo <b class="mono">{esc(short(REPO))}</b></span>'
             f'<span>Commit <b class="mono">{esc(sha.strip())}</b></span></div></div></div>')
    h.append('<div class="kpis">' + "".join(
        f'<div class="stat"><div class="n">{n}</div><div class="l"><span class="dot {c}"></span>{esc(l)}</div></div>'
        for n, c, l in [(len(skills), "info", "skills in this repo"), (len(ours), "fail", "gate hooks (this repo)"),
                        (len(plugins), "skip", "plugins with hooks"), (len({e for e, *_ in hooks}), "ok", "lifecycle events hooked")]) + '</div>')

    nav = [("wheel", "Harness wheel"), ("lifecycle", "Lifecycle map"), ("path", "Task path"),
           ("skills", "Skill reference"), ("hooks", "Hooks wired")]
    h.append('<div class="grid"><nav class="side"><div class="h">Docs</div>' +
             "".join(f'<a href="#{i}">{esc(t)}</a>' for i, t in nav) + '</nav><div>')

    wl = "".join(f'<a data-pillar="{pl["id"]}" tabindex="0" role="button"><span class="n">{pl["no"]}</span><span>{esc(pl["name"])}</span>'
                 f'<span class="mono" style="font-size:11px;color:var(--muted)">{len(pl["covered_by"].get("skills", []))} skills</span></a>'
                 for pl in PILLARS)
    h.append(card("wheel", "Skills", "Harness wheel", "The eight components of an agent harness; hover or tap a slice for what it covers",
                  f'<div class="wheelwrap">{wheel_svg()}<div class="wlist">{wl}</div></div>{pillar_cards()}'))

    legend = ('<div class="legend">'
              '<span><i class="sw" style="background:var(--accent-soft);outline:1px solid var(--accent-text)"></i>skill</span>'
              '<span><i class="sw" style="background:var(--bad-soft);outline:1px solid var(--bad-text)"></i>gate hook from this repo</span>'
              '<span><i class="sw" style="background:var(--surface-3);outline:1px solid var(--border-2)"></i>plugin hook</span>'
              '<span><i class="sw" style="border:1.5px dashed #d08a5c"></i>agentic loop</span>'
              '<span><i class="sw" style="border:1.5px dashed #3b82c4"></i>each turn</span></div>')
    h.append(card("lifecycle", "Flow", "Lifecycle map", "Claude Code hook events, top to bottom; chips are what acts at each one",
                  f'<div class="scroll">{lifecycle_svg(hooks)}</div>{legend}'))

    h.append(card("path", "Skills", "Task path", "Where each skill comes into play on a normal task",
                  f'<div class="scroll">{task_path_svg()}</div>'))


    rows = []
    for n, s in sorted(LIFE["skills"].items(), key=lambda kv: kv[1]["tier"] != "core"):
        if n not in meta:
            continue
        inv = meta[n].get("user-invocable", "").lower() == "true"
        how = f'<span class="chip acc">/{esc(n)}</span>' if inv else '<span class="chip agent">by description</span>'
        tier = f'<span class="tier {s["tier"]}">{"Core" if s["tier"] == "core" else "Optional"}</span>'
        where = " ".join(f'<span class="chip">{esc(LIFE["events"][e]["label"])}</span>' for e in s["events"])
        rows.append(f'<tr><td class="mono">{esc(n)}</td><td>{tier}</td><td>{how}</td><td><div class="chips">{where}</div></td><td>{esc(s["when"])}</td></tr>')
    for n in unmapped:
        rows.append(f'<tr><td class="mono">{esc(n)}</td><td colspan="4"><span class="chip warn">not placed in assets/lifecycle.json yet</span></td></tr>')
    h.append(card("skills", "Skills", "Skill reference", f"{len(meta)} skills, how they load and where they act",
                  '<div style="overflow-x:auto"><table class="t"><tr><th>Skill</th><th>Tier</th><th>Loads</th><th>Lifecycle</th><th>When</th></tr>'
                  + "".join(rows) + '</table></div>'))

    hrows = "".join(
        f'<tr><td>{esc(ev)}</td><td class="mono">{esc(m)}</td><td><span class="chip {"bad" if k == "gate" else ""}">{esc(n)}</span></td><td>{esc(src)}</td></tr>'
        for ev, m, k, n, src in sorted(hooks, key=lambda r: (r[0], r[2] != "gate", r[3])))
    h.append(card("hooks", "Hooks", "Hooks wired", "Read live from ~/.claude settings and enabled plugins",
                  '<div style="overflow-x:auto"><table class="t"><tr><th>Event</th><th>Matcher</th><th>Hook</th><th>From</th></tr>'
                  + (hrows or '<tr><td colspan="4">No hooks registered.</td></tr>') + '</table></div>'))
    h.append('</div></div>')
    footer = (f'Harness docs {esc(version)}, generated by <span class="mono">skills/harness-map/scripts/harness_docs.py</span> '
              'from <span class="mono">assets/lifecycle.json</span> and live settings. Re-run to refresh.')
    return render_page(f"Harness Docs {version}", "Harness Docs", f"/ {version}", "".join(h), footer), unmapped, stale


HOOKS = []


def main():
    global HOOKS
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(CLAUDE / "harness-docs.html"))
    ap.add_argument("--open", action="store_true", help="open the page in the default browser")
    a = ap.parse_args()

    HOOKS = live_hooks()
    page, unmapped, stale = render(HOOKS, LIFE["version"], dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)
    print(f"Harness docs {LIFE['version']}: {out}")
    print(f"{len(LIFE['skills']) - len(stale)} skills placed, {len(HOOKS)} hooks wired on {socket.gethostname().split('.')[0]}")
    if unmapped:
        print("Not placed in assets/lifecycle.json: " + ", ".join(unmapped))
    if stale:
        print("In assets/lifecycle.json but no such skill: " + ", ".join(stale))
    if a.open:
        run(["open" if sys.platform == "darwin" else "xdg-open", str(out)])
    sys.exit(1 if unmapped or stale else 0)


if __name__ == "__main__":
    main()
