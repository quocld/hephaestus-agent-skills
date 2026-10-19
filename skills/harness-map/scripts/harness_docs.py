#!/usr/bin/env python3
"""The Docs tab of the harness map page: where each skill and hook sits in the Claude Code lifecycle, the task path,
and reference tables. Skill placement comes from assets/lifecycle.json; hooks are read live from settings and enabled
plugins. harness_map.py renders it next to the dashboard in one HTML file.
"""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from page import release_version, PILLARS, REPO, pillar_cards, wheel_svg, SKILL_NAMES, ULTIMATE, ult, CLAUDE, SKILL, _dict, _dicts, _str, esc, icon, load_json, load_obj, plugin_entry, repo_skills

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
    # Name a custom hook by its program, skipping leading NAME=value assignments, which can hold secrets.
    try:
        words = shlex.split(cmd)
    except ValueError:
        return "custom", "command"   # unbalanced quotes: any guess could be part of a value
    words = [w for w in words if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)]
    return "custom", (Path(words[0].strip("\"'")).name if words else "command")[:28]


def repo_hooks():
    """[(event, matcher, kind, name, where)] that this repo's plugin registers (hooks/hooks.json): the same table as
    live_hooks, but from the repo alone, for a page that must not describe any one machine."""
    data = load_obj(REPO / "hooks" / "hooks.json")
    rows = []
    for event, entries in _dict(data.get("hooks", data)).items():
        for e in _dicts(entries):
            for h in _dicts(e.get("hooks")):
                m = re.search(r"hooks/([\w-]+)\.py", _str(h.get("command")))
                rows.append((event, _str(e.get("matcher")) or "*", "gate", m.group(1) if m else "agent-skills", "plugin hooks.json"))
    return rows


def live_hooks():
    """[(event, matcher, kind, name, where)] from settings files and enabled plugins' hooks.json."""
    rows = []
    for fname in ("settings.json", "settings.local.json"):
        for event, entries in _dict(load_obj(CLAUDE / fname).get("hooks")).items():
            for e in _dicts(entries):
                for h in _dicts(e.get("hooks")):
                    kind, name = hook_source(_str(h.get("command")))
                    rows.append((event, _str(e.get("matcher")) or "*", kind, name, fname))
    settings = load_obj(CLAUDE / "settings.json")
    installed = _dict(load_obj(CLAUDE / "plugins" / "installed_plugins.json").get("plugins"))
    for pid, on in _dict(settings.get("enabledPlugins")).items():
        if not on:
            continue
        path = Path(_str(plugin_entry(installed, pid).get("installPath")))
        data = load_obj(path / "hooks" / "hooks.json")
        ours = pid.split("@")[0] == "agent-skills"
        for event, entries in _dict(data.get("hooks", data)).items():
            for e in _dicts(entries):
                if ours:
                    # This repo's own gates, shipped in the plugin, keep their names and the gate colour.
                    for h in _dicts(e.get("hooks")):
                        m = re.search(r"hooks/([\w-]+)\.py", _str(h.get("command")))
                        rows.append((event, _str(e.get("matcher")) or "*", "gate", m.group(1) if m else "agent-skills", "plugin agent-skills"))
                else:
                    rows.append((event, _str(e.get("matcher")) or "*", "plugin", pid.split("@")[0], "plugin " + pid.split("@")[0]))
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

        chips = chips_for(r, hooks)
        if chips:
            lines = chip_rows(chips, CX, CR)
            top = y + NODE_H / 2 - (len(lines) * 22 - 4) / 2
            p.append(f'<path d="M{MX + MW} {y + NODE_H / 2} H{CX - 6}" stroke="var(--border-2)" stroke-width="1.2" stroke-dasharray="3 3"/>')
            for li, line in enumerate(lines):
                for kind, lab, x, w in line:
                    bg, fg = CHIP[kind]
                    yy = top + li * 22
                    p.append(svg_chip(kind, lab, x, yy, w, 18, 12.5))
    p.append('</svg>')
    return "".join(p)


# ---------------------------------------------------------------- task path svg

CW, CH, GAP = 7.4, 21, 27   # chip char width, chip height, chip row pitch in the larger diagrams


def svg_chip(kind, lab, x, y, w, h, base):
    """One chip; an ultimate skill gets the gradient outline and gradient bold text, and every repo skill opens
    in the skill reader when clicked."""
    bg, fg = CHIP[kind]
    if kind == "skill" and lab in ULTIMATE:
        chip = (f'<rect x="{x:.1f}" y="{y}" width="{w}" height="{h}" rx="5" fill="{bg}" stroke="url(#ult-grad)" stroke-width="1.4"/>'
                f'<text x="{x + w / 2:.1f}" y="{y + base}" text-anchor="middle" class="chip-t ult-t" style="fill:url(#ult-grad)">{esc(lab)}</text>')
    else:
        chip = (f'<rect x="{x:.1f}" y="{y}" width="{w}" height="{h}" rx="5" fill="{bg}"/>'
                f'<text x="{x + w / 2:.1f}" y="{y + base}" text-anchor="middle" class="chip-t" style="fill:{fg}">{esc(lab)}</text>')
    if kind == "skill" and lab in SKILL_NAMES:
        return f'<g class="skl" data-skill="{esc(lab)}" role="button" tabindex="0"><title>Read {esc(lab)}</title>{chip}</g>'
    return chip


def chip_line_svg(items, center, y):
    """One centered row of chips [(kind, label)]; returns (svg, width)."""
    widths = [round(len(lab) * CW + 16) for _, lab in items]
    total = sum(widths) + 6 * (len(items) - 1)
    x, out = center - total / 2, []
    for (kind, lab), w in zip(items, widths):
        out.append(svg_chip(kind, lab, x, y, w, CH, 14.5))
        x += w + 6
    return "".join(out), total


def chips_stacked(items, center, width, bottom):
    """Wrap chips into rows that fit `width`, stacked upward so the last row ends at `bottom`."""
    lines = chip_rows(items, 0, width, CW)
    return "".join(chip_line_svg([(k, lab) for k, lab, _, _ in line], center, bottom - (len(lines) - i) * GAP)[0]
                   for i, line in enumerate(lines))

def task_path_svg():
    """Prompt -> agentic loop (gather, act, verify, retry) -> response -> back to the next prompt,
    with each skill placed on the step where it comes into play (assets/lifecycle.json `path`)."""
    W, H, NY, NH = 1280, 500, 262, 62
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

    def chips_above(step):
        x, w = nodes[step]
        p.append(chips_stacked(skills_at(step), x + w / 2, w + 30, NY - 14))

    def label_on_line(text_, step, cxv, y):
        """Text ends where the chips start, so the gap is exact whatever the font measures."""
        items = skills_at(step)
        tw = len(text_) * 7.2  # generous estimate, only used for the mask behind the label
        _, cw = chip_line_svg(items, 0, 0)
        join = cxv - cw / 2 + tw / 2
        p.append(f'<rect x="{join - tw - 18:.1f}" y="{y - 14}" width="{tw + cw + 36:.1f}" height="28" fill="var(--surface)"/>')
        p.append(f'<text x="{join - 8:.1f}" y="{y + 4.5}" text-anchor="end" class="tl">{esc(text_)}</text>')
        p.append(chip_line_svg(items, join + cw / 2, y - CH / 2)[0])

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
                 + (f' stroke-dasharray="{dash}"' if dash else "") + '/>')
        p.append(text(x + w / 2, NY + 28, path[k]["label"], "tn", "middle"))
        p.append(text(x + w / 2, NY + 47, path[k]["sub"], "tsub", "middle"))
        chips_above(k)
    p.append('</svg>')
    return "".join(p)


# ---------------------------------------------------------------- verification loop svg

def verify_loop_svg():
    """verify-loop section 2: seven gates on one head, a red gate loops back to gate 2, the table goes into the PR."""
    vl = LIFE["verify_loop"]
    W, H, NY, NH = 1280, 330, 172, 62
    GW, GG, GX = 124, 14, 160
    gates = [(GX + i * (GW + GG), g) for i, g in enumerate(vl["gates"])]
    fill = {"machine": "var(--ok-soft)", "evidence": "var(--accent-soft)"}
    mid = NY + NH / 2
    p = [f'<svg viewBox="0 0 {W} {H}" class="life tp vlsvg" role="img" aria-label="verify-loop gates in order">',
         '<defs><marker id="v-a" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0L8 4L0 8z" fill="var(--muted)"/></marker>'
         '<marker id="v-r" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
         '<path d="M0 0L8 4L0 8z" fill="var(--bad)"/></marker></defs>']

    # Frame: every gate runs on one head.
    bx, by, bw, bh = 146, 22, 978, 290
    p.append(f'<rect x="{bx}" y="{by}" width="{bw}" height="{bh}" rx="6" fill="none" stroke="var(--border-3, var(--muted))" stroke-width="1.5" stroke-dasharray="5 5"/>')
    p.append(f'<rect x="{bx + bw - 160}" y="{by - 13}" width="140" height="26" fill="var(--surface)"/>')
    p.append(f'<text x="{bx + bw - 90}" y="{by + 6}" text-anchor="middle" class="tframe">One head</text>')

    # Start and end nodes, and the forward arrows.
    ends = [(16, 110, vl["start"]), (1144, 124, vl["end"])]
    for x, w, n in ends:
        p.append(f'<rect x="{x}" y="{NY}" width="{w}" height="{NH}" rx="7" fill="var(--surface-3)"/>')
        p.append(text(x + w / 2, NY + 28, n["label"], "gn", "middle"))
        p.append(text(x + w / 2, NY + 46, n["sub"], "tsub", "middle"))
    xs = [(126, GX)] + [(gates[i][0] + GW, gates[i + 1][0]) for i in range(len(gates) - 1)] + [(gates[-1][0] + GW, 1144)]
    for x1, x2 in xs:
        p.append(f'<path d="M{x1 + 3} {mid} H{x2 - 4}" stroke="var(--muted)" stroke-width="1.6" marker-end="url(#v-a)"/>')

    # Red gate: stubs from gates 3..7 to one line that returns into gate 2.
    RY = 280
    g2 = gates[1][0] + GW / 2
    for x, _ in gates[2:]:
        p.append(f'<path d="M{x + GW / 2} {NY + NH + 2} V{RY}" stroke="var(--bad)" stroke-width="1.2" stroke-dasharray="3 3"/>')
    p.append(f'<path d="M{gates[-1][0] + GW / 2} {RY} H{g2 + 8} Q{g2} {RY} {g2} {RY - 8} V{NY + NH + 8}" fill="none" '
             f'stroke="var(--bad)" stroke-width="1.6" marker-end="url(#v-r)"/>')
    items = [("skill", "root-cause")]
    _, cw = chip_line_svg(items, 0, 0)
    tw = len(vl["retry"]) * 7.2
    cx_ = (gates[2][0] + gates[-1][0] + GW) / 2
    join = cx_ - cw / 2 + tw / 2
    p.append(f'<rect x="{join - tw - 18:.1f}" y="{RY - 14}" width="{tw + cw + 36:.1f}" height="28" fill="var(--surface)"/>')
    p.append(f'<text x="{join - 8:.1f}" y="{RY + 4.5}" text-anchor="end" class="tl" style="fill:var(--bad-text)">{esc(vl["retry"])}</text>')
    p.append(chip_line_svg(items, join + cw / 2, RY - CH / 2)[0])

    # Gates with their number badge and the skills or commands that own them.
    for i, (x, g) in enumerate(gates, 1):
        p.append(f'<rect x="{x}" y="{NY}" width="{GW}" height="{NH}" rx="7" fill="{fill[g["kind"]]}"/>')
        p.append(f'<circle cx="{x + 4}" cy="{NY + 4}" r="10" fill="var(--accent)"/>'
                 f'<text x="{x + 4}" y="{NY + 8}" text-anchor="middle" class="gno">{i}</text>')
        p.append(text(x + GW / 2, NY + 28, g["label"], "gn", "middle"))
        p.append(text(x + GW / 2, NY + 46, g["sub"], "tsub", "middle"))
        chips = [("skill", n) for n in g["skills"]] + [("plugin", n) for n in g["items"]]
        p.append(chips_stacked(chips, x + GW / 2, GW + 12, NY - 12))
    p.append('</svg>')
    return "".join(p)


def verify_loop_html():
    vl = LIFE["verify_loop"]
    rules = "".join(f"<li>{esc(r)}</li>" for r in vl["rules"])
    rows = "".join(f'<tr><td class="mono">{esc(g)}</td><td><span class="pill {"ok" if st == "PASS" else "skip" if st == "SKIP" else "fail"}">{st}</span></td>'
                   f'<td class="mono">{esc(ev)}</td></tr>' for g, st, ev in vl["example"])
    legend = ('<div class="legend"><span><i class="sw" style="background:var(--ok-soft)"></i>machine check</span>'
              '<span><i class="sw" style="background:var(--accent-soft)"></i>evidence gate</span>'
              '<span><i style="display:inline-block;width:18px;border-top:2px solid var(--bad)"></i>red gate loops back to gate 2</span></div>')
    return (f'<div class="scroll">{verify_loop_svg()}</div>{legend}'
            f'<div class="vl"><div><div class="lbl3">Rules</div><ul class="vrules">{rules}</ul></div>'
            f'<div><div class="lbl3">The table that goes into the PR body</div>'
            f'<table class="vt"><tr><th>gate</th><th>status</th><th>evidence</th></tr>{rows}</table>'
            '<p class="vnote">Statuses: PASS, FAIL, SKIP or DEFER, each with its evidence or reason.</p></div></div>')


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
.life .ult-t{font-weight:700}
.life .gn{font-family:"Host Grotesk",Inter,sans-serif;font-size:15px;font-weight:500}
.life .gno{font-size:11px;font-weight:700;fill:#fff}
.vlsvg .gn{font-size:17px}.vlsvg .tsub{font-size:13px}.vlsvg .tl{font-size:13.5px}
.vl{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);gap:24px;padding:4px 18px 20px}
.vrules{margin:8px 0 0;padding-left:18px;font-size:13px;color:var(--text-2)}.vrules li{margin:5px 0}
table.vt{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}
table.vt th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);padding:6px 8px;border-bottom:1px solid var(--border)}
table.vt td{padding:6px 8px;border-top:1px solid var(--border);vertical-align:top;color:var(--text-2)}
table.vt td.mono{font-size:11.5px}
.vnote{margin:8px 0 0;font-size:12px;color:var(--muted)}
.prose{padding:16px 18px;color:var(--text-2);max-width:820px}
.prose p{margin:0 0 10px}.prose ul{margin:0 0 10px;padding-left:18px}.prose li{margin:3px 0}
table.t{width:100%;border-collapse:collapse;font-size:13px}
table.t th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600;padding:10px 18px;border-bottom:1px solid var(--border);background:var(--surface-2)}
table.t td{padding:10px 18px;border-top:1px solid var(--border);vertical-align:top;color:var(--text-2)}
table.t td:first-child{color:var(--text);font-weight:500;white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:28px}
@media (max-width:900px){.vl{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}
table.t td:first-child{white-space:normal}}
</style>"""


def card(id_, ic, title, desc, inner):
    return (f'<section class="card" id="{id_}"><div class="hd">{icon(ic)}<h2>{esc(title)}</h2>'
            f'<span class="desc">{esc(desc)}</span></div>{inner}</section>')


ONBOARD_BUTTON = '<button class="btn primary onboard-btn" type="button" data-open="onboard-src">Onboard your agent</button>'


def onboard_source():
    """The onboarding prompt (assets/onboard-prompt.md) as a template the header button opens in the side panel."""
    prompt = (SKILL / "assets" / "onboard-prompt.md").read_text().strip()
    return ('<template id="onboard-src"><div class="rmeta"><h2 class="rtitle">Onboard your agent</h2>'
            '<p class="rdesc">Paste this one line into any coding agent (Claude Code, Codex, Cursor, Gemini CLI, OpenCode, Copilot). '
            'It reads the install guide, takes stock of the harness you already have, installs Hephaestus Skills without '
            'overwriting anything (a clashing skill or rule is kept and ours is forked as <code>hx-&lt;name&gt;</code>), '
            'shows you every change first, and then walks you through the rest of the setup.</p>'
            '<div class="bar"><button class="btn primary" type="button" data-copy="onboard-text">Copy prompt</button>'
            '<a class="btn ghost" href="/install/">Read the install guide</a></div></div>'
            f'<pre id="onboard-text" class="ptext open">{esc(prompt)}</pre></template>')


def unplaced_skills():
    """Repo skills missing from assets/lifecycle.json, and entries there with no such skill."""
    names = {d.name for d, _ in repo_skills()}
    return sorted(names - set(LIFE["skills"])), sorted(set(LIFE["skills"]) - names)


def docs_body(hooks, standalone=False):
    """Body of the Docs tab: KPIs, lifecycle map, task path, skill reference, hooks table.
    standalone: the public docs site, which has no Dashboard, so it carries the harness wheel itself."""
    skills = repo_skills()
    meta = {d.name: fm for d, fm in skills}
    unmapped, _ = unplaced_skills()
    ours = sorted({n for _, _, k, n, _ in hooks if k == "gate"})
    plugins = sorted({n for _, _, k, n, _ in hooks if k == "plugin"})

    h = [DOC_CSS]
    h.append(f'<div class="hero"><div><div class="eyebrow">Harness docs {esc(release_version())}</div><h1>How this harness is built</h1>'
             '<p class="sub">The Claude Code lifecycle redrawn with every skill and hook, the path a normal task takes through them, '
             + ('and what loads each skill, around the eight components of an agent harness.' if standalone else
                'and what loads each skill. The eight components live on the Dashboard wheel.') + '</p></div></div>')
    h.append('<div class="kpis">' + "".join(
        f'<div class="stat"><div class="n">{n}</div><div class="l"><span class="dot {c}"></span>{esc(l)}</div></div>'
        for n, c, l in ([(len(skills), "info", "skills"),
                         (sum(1 for s_ in LIFE["skills"].values() if s_.get("tier") == "core"), "ok", "core skills"),
                         (len(ULTIMATE), "warn", "ultimate skills"), (len({e for e, *_ in hooks}), "fail", "lifecycle events hooked")]
                        if standalone else
                        [(len(skills), "info", "skills in this repo"), (len(ours), "fail", "gate hooks (this repo)"),
                         (len(plugins), "skip", "plugins with hooks"), (len({e for e, *_ in hooks}), "ok", "lifecycle events hooked")])) + '</div>')

    nav = ([("wheel", "Harness wheel")] if standalone else []) + [("lifecycle", "Lifecycle map"), ("path", "Task path"), ("verification", "Verification loop"), ("skill-reference", "Skill reference"), ("hooks-wired", "Hooks wired")]
    h.append('<div class="grid"><nav class="side"><div class="h">Docs</div>' +
             "".join(f'<a href="#{i}">{esc(t)}</a>' for i, t in nav) + '</nav><div>')
    if standalone:
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
              '<span class="chip ultchip"><span class="ult">ultimate skill</span></span>'
              '<span><i class="sw" style="border:1.5px dashed #3b82c4"></i>each turn</span></div>')
    h.append(card("lifecycle", "Flow", "Lifecycle map", "Claude Code hook events, top to bottom; chips are what acts at each one",
                  f'<div class="scroll">{lifecycle_svg(hooks)}</div>{legend}'))

    h.append(card("path", "Skills", "Task path", "Where each skill comes into play on a normal task",
                  f'<div class="scroll">{task_path_svg()}</div>'))
    h.append(card("verification", "Hooks", "Verification loop",
                  "verify-loop: every gate in order on one head before a change is called done or a PR opens",
                  verify_loop_html()))


    rows = []
    for n, s in sorted(LIFE["skills"].items(), key=lambda kv: kv[1]["tier"] != "core"):
        if n not in meta:
            continue
        inv = meta[n].get("user-invocable", "").lower() == "true"
        how = f'<span class="chip acc">{ult(n, "/" + n)}</span>' if inv else '<span class="chip agent">by description</span>'
        tier = f'<span class="tier {s["tier"]}">{"Core" if s["tier"] == "core" else "Optional"}</span>'
        where = " ".join(f'<span class="chip">{esc(LIFE["events"][e]["label"])}</span>' for e in s["events"])
        # On the docs site a skill name is also a real link to its own page, so search engines can crawl it;
        # the reader still opens it in place on a click.
        name_ = (f'<a class="skl" data-skill="{esc(n)}" href="skills/{esc(n)}/">{ult(n) if n in ULTIMATE else esc(n)}</a>'
                 if standalone else ult(n))
        rows.append(f'<tr><td class="mono">{name_}</td><td>{tier}</td><td>{how}</td><td><div class="chips">{where}</div></td><td>{esc(s["when"])}</td></tr>')
    for n in unmapped:
        rows.append(f'<tr><td class="mono">{esc(n)}</td><td colspan="4"><span class="chip warn">not placed in assets/lifecycle.json yet</span></td></tr>')
    h.append(card("skill-reference", "Skills", "Skill reference", f"{len(meta)} skills, how they load and where they act; click a name to read it",
                  '<div style="overflow-x:auto"><table class="t"><tr><th>Skill</th><th>Tier</th><th>Loads</th><th>Lifecycle</th><th>When</th></tr>'
                  + "".join(rows) + '</table></div>'))

    hrows = "".join(
        f'<tr><td>{esc(ev)}</td><td class="mono">{esc(m)}</td><td><span class="chip {"bad" if k == "gate" else ""}">{esc(n)}</span></td><td>{esc(src)}</td></tr>'
        for ev, m, k, n, src in sorted(hooks, key=lambda r: (r[0], r[2] != "gate", r[3])))
    h.append(card("hooks-wired", "Hooks", "Hooks wired", "Read live from ~/.claude settings and enabled plugins",
                  '<div style="overflow-x:auto"><table class="t"><tr><th>Event</th><th>Matcher</th><th>Hook</th><th>From</th></tr>'
                  + (hrows or '<tr><td colspan="4">No hooks registered.</td></tr>') + '</table></div>'))
    h.append('</div></div>')
    return "".join(h)
