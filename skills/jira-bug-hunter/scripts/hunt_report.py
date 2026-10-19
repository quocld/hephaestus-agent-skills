#!/usr/bin/env python3
"""Maintain the one bug-hunt demo report shared by every project: a single index.html grouped by day, then by project.

Usage:
  python3 hunt_report.py check <entry.json>   validate an entry, write nothing
  python3 hunt_report.py add <entry.json>     validate, copy its media, upsert it by (date, project, ticket), re-render
  python3 hunt_report.py render               re-render the page from the data it already embeds
  python3 hunt_report.py path                 print the report file path

The report lives in $BUG_HUNT_REPORT_DIR (default ~/bug-hunt-report): index.html plus media/<date>/<project>/.
The entries are embedded in index.html itself (<script type="application/json" id="hunt-data">), so that file is the only source of truth.
Concurrent `add` calls are serialized with a lock file; the page is replaced atomically.

Entry JSON (one ticket, one day):
{
  "date": "2026-10-19",                       day the result was verified, YYYY-MM-DD
  "project": "VOCO",                          display name; groups entries within a day
  "ticket": "VOCOTMA-13",
  "ticketUrl": "https://<site>.atlassian.net/browse/VOCOTMA-13",
  "title": "Completeness score breakdown",
  "where": "Dashboard /en/dashboard",         screen or route the bug lives on
  "verdict": "verified | not-fixed | cannot-reproduce | needs-decision | correct-per-decision | blocked | awaiting-merge | pending-deploy",
  "environment": {"name": "dev", "url": "https://dev.example.com"},
  "persona": "member@example.test - Camille, Pro plan",   never a password
  "viewports": ["1440x900", "390x844"],
  "before": "What the reporter saw, with the date they reported it.",
  "asked": "What the ticket asked for, in the reader's words.",
  "now": "What the product does now on <environment>, or why the ticket ended in another verdict.",
  "media": [{"src": "/abs/path/after-desktop.webm", "kind": "before | after", "caption": "Desktop, 1440x900"}],
  "steps": ["Reproduce-it-yourself step 1", "..."],
  "checks": [{"ok": true, "text": "Observed fact with the measured value"}],
  "pr": "https://github.com/org/repo/pull/12",
  "commit": "<SHA running on the environment when verified>",
  "evidence": "<report dir>/evidence/VOCOTMA-13-2026-10-19T08:00:00Z.json",
  "dataChanges": ["Test data this run created or changed on the environment"]
}
`verified` needs at least one `after` media item, a non-empty `steps`, every check ok, and `commit`.
Media files are copied into the report folder; videos use preload="none", so nothing downloads before Play.
"""
import contextlib
import datetime as dt
import fcntl
import html
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

VERDICTS = {
    "verified": ("Verified on {env}", "ok"),
    "not-fixed": ("Not fixed", "bad"),
    "cannot-reproduce": ("Cannot reproduce", "muted"),
    "needs-decision": ("Needs a decision", "warn"),
    "correct-per-decision": ("Correct per decision", "muted"),
    "blocked": ("Blocked", "bad"),
    "awaiting-merge": ("Awaiting merge", "warn"),
    "pending-deploy": ("Pending deploy", "warn"),
}
VIDEO_EXT = {".webm", ".mp4", ".mov"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
MAX_MEDIA_BYTES = 80 * 1024 * 1024
SECRET = re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\b\s*[:=]\s*\S|\bBearer\s+[A-Za-z0-9._~+/-]{12,}")
DATA_RE = re.compile(r'<script type="application/json" id="hunt-data">(.*?)</script>', re.S)
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def report_dir():
    return Path(os.environ.get("BUG_HUNT_REPORT_DIR") or Path.home() / "bug-hunt-report").expanduser()


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def validate(e):
    """Return a list of problems; empty means the entry is valid."""
    p = []
    if not isinstance(e, dict):
        return ["entry must be a JSON object"]

    def text(key):
        if not isinstance(e.get(key), str) or not e[key].strip():
            p.append(f"{key}: required non-empty string")

    try:
        dt.date.fromisoformat(str(e.get("date")))
    except ValueError:
        p.append("date: must be YYYY-MM-DD")
    for key in ("project", "title", "where", "persona", "before", "asked", "now"):
        text(key)
    if not re.fullmatch(r"[A-Z][A-Z0-9_]+-\d+", str(e.get("ticket", ""))):
        p.append("ticket: must look like ABC-123")
    if not str(e.get("ticketUrl", "")).startswith("https://"):
        p.append("ticketUrl: must be an https URL")
    verdict = e.get("verdict")
    if verdict not in VERDICTS:
        p.append(f"verdict: one of {', '.join(VERDICTS)}")
    env = e.get("environment")
    if not isinstance(env, dict) or not env.get("name") or not str(env.get("url", "")).startswith(("http://", "https://")):
        p.append("environment: {name, url} with an http(s) URL")
    for key in ("viewports", "steps", "dataChanges"):
        if key in e and not (isinstance(e[key], list) and all(isinstance(s, str) and s.strip() for s in e[key])):
            p.append(f"{key}: list of non-empty strings")
    checks = e.get("checks", [])
    if not isinstance(checks, list) or not all(isinstance(c, dict) and isinstance(c.get("ok"), bool) and str(c.get("text", "")).strip() for c in checks):
        p.append("checks: list of {ok: bool, text}")
        checks = []
    media = e.get("media", [])
    if not isinstance(media, list):
        p.append("media: list")
        media = []
    for i, m in enumerate(media):
        if not isinstance(m, dict) or m.get("kind") not in ("before", "after") or not m.get("src"):
            p.append(f"media[{i}]: {{src, kind: before|after, caption}}")
            continue
        ext = Path(m["src"]).suffix.lower()
        if ext not in VIDEO_EXT | IMAGE_EXT:
            p.append(f"media[{i}]: unsupported file type {ext or '(none)'}")
        src = Path(m["src"]).expanduser()
        if not src.is_absolute():
            src = report_dir() / src
        if not src.is_file():
            p.append(f"media[{i}]: file not found: {m['src']}")
        elif src.stat().st_size > MAX_MEDIA_BYTES:
            p.append(f"media[{i}]: larger than {MAX_MEDIA_BYTES // 2**20} MB; record a shorter clip")
    for key in ("pr", "evidence"):
        if key in e and not (isinstance(e[key], str) and e[key].strip()):
            p.append(f"{key}: non-empty string when present")
    if "commit" in e and not re.fullmatch(r"[0-9a-f]{7,40}", str(e["commit"])):
        p.append("commit: hex SHA")
    if verdict == "verified":
        if not any(isinstance(m, dict) and m.get("kind") == "after" for m in media):
            p.append("verified: needs at least one 'after' media item recorded on the environment")
        if not e.get("steps"):
            p.append("verified: needs reproduce-it-yourself steps")
        if not checks or not all(c["ok"] for c in checks):
            p.append("verified: needs checks, all ok; a failed check means verdict not-fixed")
        if not e.get("commit"):
            p.append("verified: needs the commit that was running on the environment")
    leaks = [s[:60] for s in strings(e) if SECRET.search(s)]
    if leaks:
        p.append(f"looks like a credential, remove it: {leaks[0]!r}")
    return p


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def load(path):
    if not path.exists():
        return []
    m = DATA_RE.search(path.read_text(encoding="utf-8"))
    if not m:
        fail(f"{path} has no embedded hunt-data block; refusing to overwrite a file this script did not write")
    return json.loads(m.group(1))


def copy_media(e, root):
    out = []
    for i, m in enumerate(e.get("media", []), 1):
        src = Path(m["src"]).expanduser()
        if not src.is_absolute():
            src = root / src
        rel = Path("media") / e["date"] / slug(e["project"]) / f"{e['ticket']}-{m['kind']}-{i}{src.suffix.lower()}"
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != dst.resolve():
            shutil.copy2(src, dst)
        out.append({**m, "src": rel.as_posix()})
    return {**e, "media": out}


def esc(s):
    return html.escape(str(s), quote=True)


def nice_date(d):
    d = dt.date.fromisoformat(d)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def link(url, label):
    url = str(url)
    if not url.startswith(("https://", "http://")):
        return esc(label)
    return f'<a href="{esc(url)}">{esc(label)}</a>'


def render_entry(e):
    label, tone = VERDICTS[e["verdict"]]
    anchor = f"{e['date']}-{slug(e['project'])}-{e['ticket'].lower()}"
    rows = "".join(
        f'<div class="row"><div class="k {cls}">{name}</div><div class="v {cls}">{esc(e[key])}</div></div>'
        for key, name, cls in (("before", "Before", "before"), ("asked", "What the ticket asked", "asked"), ("now", "Now", "now"))
    )
    media = ""
    for m in e.get("media", []):
        cap = f"<figcaption>{esc(m.get('caption', ''))} <span class='tag'>{esc(m['kind'])}</span></figcaption>"
        if Path(m["src"]).suffix.lower() in VIDEO_EXT:
            body = f'<video controls preload="none" playsinline src="{esc(m["src"])}"></video>'
        else:
            body = f'<a href="{esc(m["src"])}"><img loading="lazy" alt="{esc(m.get("caption", ""))}" src="{esc(m["src"])}"></a>'
        media += f"<figure>{body}{cap}</figure>"
    steps = ""
    if e.get("steps"):
        items = "".join(f"<li>{esc(s)}</li>" for s in e["steps"])
        steps = f"<details><summary>Reproduce it yourself</summary><ol>{items}</ol></details>"
    checks = ""
    if e.get("checks"):
        items = "".join(
            f'<li><span class="mark {"ok" if c["ok"] else "bad"}">{"OK" if c["ok"] else "FAIL"}</span>{esc(c["text"])}</li>'
            for c in e["checks"]
        )
        checks = f'<ul class="checks">{items}</ul>'
    foot = []
    if e.get("pr"):
        foot.append(link(e["pr"], "Pull request"))
    if e.get("commit"):
        foot.append(f"<code>{esc(e['commit'][:10])}</code>")
    if e.get("evidence"):
        foot.append(f"evidence <code>{esc(e['evidence'])}</code>")
    foot_html = f'<p class="foot">{" · ".join(foot)}</p>' if foot else ""
    return (
        f'<article class="card" id="{esc(anchor)}">'
        f'<div class="chips"><span class="chip">{link(e["ticketUrl"], e["ticket"])}</span>'
        f'<span class="badge {tone}">{esc(label.format(env=e["environment"]["name"]))}</span></div>'
        f"<h4>{esc(e['title'])}</h4><p class=\"where\">{esc(e['where'])}</p>"
        f'<div class="grid">{rows}</div>'
        f'{f"<div class=media>{media}</div>" if media else ""}{steps}{checks}{foot_html}</article>'
    )


def render_project(project, entries):
    first = entries[0]
    envs = sorted({(x["environment"]["name"], x["environment"]["url"]) for x in entries})
    personas = sorted({x["persona"] for x in entries})
    viewports = sorted({v for x in entries for v in x.get("viewports", [])})
    meta = "".join(
        f"<dt>{k}</dt><dd>{v}</dd>"
        for k, v in (
            ("Environment", ", ".join(f"{esc(n)} {link(u, u.split('//', 1)[-1].rstrip('/'))}" for n, u in envs)),
            ("Account", "<br>".join(esc(p) for p in personas)),
            ("Viewports", esc(", ".join(viewports))) if viewports else (None, None),
        )
        if k
    )
    index = "".join(
        f'<li><span class="chip">{esc(x["ticket"])}</span>'
        f'<a href="#{esc(x["date"])}-{slug(x["project"])}-{x["ticket"].lower()}">{esc(x["title"])}</a>'
        f'<span class="badge {VERDICTS[x["verdict"]][1]}">{esc(VERDICTS[x["verdict"]][0].format(env=x["environment"]["name"]))}</span></li>'
        for x in entries
    )
    changes = [c for x in entries for c in x.get("dataChanges", [])]
    changes_html = ""
    if changes:
        items = "".join(f"<li>{esc(c)}</li>" for c in dict.fromkeys(changes))
        changes_html = f'<section class="changes"><h5>What this run changed on the environment</h5><ul>{items}</ul></section>'
    cards = "".join(render_entry(x) for x in entries)
    return (
        f'<section class="project" id="{esc(first["date"])}-{slug(project)}"><h3>{esc(project)}</h3>'
        f'<dl class="meta">{meta}</dl><div class="card index"><p class="label">Tickets</p><ul>{index}</ul></div>'
        f"{cards}{changes_html}</section>"
    )


def render(entries):
    days = {}
    for e in sorted(entries, key=lambda x: (x["date"], x["project"].lower(), x["ticket"]), reverse=True):
        days.setdefault(e["date"], {}).setdefault(e["project"], []).append(e)
    nav = "".join(f'<a class="day-chip" href="#d-{d}">{nice_date(d)}</a>' for d in days)
    body = ""
    for d, projects in days.items():
        flat = [x for xs in projects.values() for x in xs]
        checks = [c for x in flat for c in x.get("checks", [])]
        verified = sum(x["verdict"] == "verified" for x in flat)
        summary = f"{len(flat)} ticket{'s' * (len(flat) != 1)} · {verified} verified · {sum(c['ok'] for c in checks)}/{len(checks)} checks passed"
        inner = "".join(render_project(p, sorted(xs, key=lambda x: x["ticket"])) for p, xs in sorted(projects.items(), key=lambda kv: kv[0].lower()))
        body += f'<section class="day" id="d-{d}"><h2>{nice_date(d)}</h2><p class="sub">{esc(summary)}</p>{inner}</section>'
    if not body:
        body = '<p class="sub">No results yet.</p>'
    data = json.dumps(entries, ensure_ascii=False, indent=1).replace("<", "\\u003c")
    return PAGE.replace("{{NAV}}", nav).replace("{{BODY}}", body).replace("{{DATA}}", data)


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Bug Hunt Reports</title>
<style>
:root{--bg:#f8fafc;--card:#fff;--fg:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#b45309;--accent-bg:#fffbeb;--ok:#15803d;--bad:#b91c1c;--warn:#a16207;--chip:#fef3c7}
@media (prefers-color-scheme:dark){:root{--bg:#0b1120;--card:#111827;--fg:#e5e7eb;--muted:#94a3b8;--line:#1f2937;--accent:#f59e0b;--accent-bg:#1c1917;--ok:#4ade80;--bad:#f87171;--warn:#facc15;--chip:#292524}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:inherit;text-decoration:underline dotted;text-underline-offset:3px}code{font-size:12px}
header{position:sticky;top:0;z-index:2;background:var(--bg);border-bottom:1px solid var(--line)}
.wrap{max-width:760px;margin:0 auto;padding:0 16px}
header .wrap{padding-top:14px;padding-bottom:10px}.brand{font-weight:600}.brand span{color:var(--accent)}.brand small{color:var(--muted);font-weight:400;margin-left:8px}
nav{display:flex;gap:6px;overflow-x:auto;margin-top:8px;padding-bottom:2px}
.day-chip{flex:none;font-size:12px;text-decoration:none;border:1px solid var(--accent);color:var(--accent);background:var(--accent-bg);border-radius:6px;padding:1px 8px}
main{padding:24px 0 64px}.day{scroll-margin-top:96px}h2{font-size:26px;letter-spacing:-.02em;margin:24px 0 2px}.sub{color:var(--muted);margin:0 0 16px}
.project{border-top:1px solid var(--line);padding-top:12px;margin-top:20px;scroll-margin-top:96px}h3{font-size:18px;margin:4px 0 8px}
.meta{display:grid;grid-template-columns:120px 1fr;gap:4px 12px;margin:0 0 16px;font-size:14px}.meta dt{color:var(--muted)}.meta dd{margin:0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px 20px;margin:14px 0;scroll-margin-top:96px}
.label{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:0 0 8px}
.index ul{list-style:none;margin:0;padding:0}.index li{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:3px 0}
.chip{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.04em;border:1px solid var(--accent);color:var(--accent);border-radius:5px;padding:1px 7px}.chip a{text-decoration:none}
.badge{font-size:11px;font-weight:600;border-radius:999px;padding:1px 8px;border:1px solid currentColor}.badge.ok{color:var(--ok)}.badge.bad{color:var(--bad)}.badge.warn{color:var(--warn)}.badge.muted{color:var(--muted)}
.chips{display:flex;flex-wrap:wrap;gap:8px;align-items:center}h4{font-size:17px;margin:8px 0 0}.where{color:var(--muted);font-size:13px;margin:2px 0 12px}
.grid{border:1px solid var(--line);border-radius:10px;padding:12px 14px}.row{display:grid;grid-template-columns:170px 1fr;gap:16px;padding:6px 0}
.k{font-size:11px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;padding-top:3px}.k.before{color:var(--muted)}.k.asked{color:var(--accent)}.k.now{color:var(--ok)}.v.before{color:var(--muted)}
.media{display:grid;gap:12px;margin-top:14px}figure{margin:0}video,img{display:block;width:100%;border:1px solid var(--line);border-radius:10px;background:var(--bg)}
figcaption{font-size:13px;color:var(--muted);margin-top:4px}.tag{font-size:11px;border:1px solid var(--line);border-radius:4px;padding:0 5px;margin-left:4px}
details{border-top:1px solid var(--line);margin-top:14px;padding-top:10px}summary{cursor:pointer;font-size:13px;font-weight:500}details ol{margin:8px 0 0;padding-left:20px;font-size:14px}
.checks{list-style:none;padding:0;margin:12px 0 0;font-size:14px}.checks li{display:flex;gap:10px;padding:2px 0}.mark{flex:none;font-size:10px;font-weight:700;width:30px;padding-top:4px}.mark.ok{color:var(--ok)}.mark.bad{color:var(--bad)}
.foot{font-size:12px;color:var(--muted);margin:12px 0 0}.changes h5{font-size:15px;margin:20px 0 6px}.changes ul{margin:0;padding-left:20px;color:var(--muted);font-size:14px}
@media (max-width:600px){.row{grid-template-columns:1fr;gap:2px}.meta{grid-template-columns:1fr}.meta dd{margin-bottom:6px}.card{padding:14px}}
</style></head><body>
<header><div class="wrap"><div class="brand">Bug <span>Hunt</span><small>Fix and verification reports</small></div><nav>{{NAV}}</nav></div></header>
<main><div class="wrap">{{BODY}}</div></main>
<script type="application/json" id="hunt-data">{{DATA}}</script>
</body></html>
"""


@contextlib.contextmanager
def locked(root):
    root.mkdir(parents=True, exist_ok=True)
    with open(root / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def write(path, entries):
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".index-", suffix=".html")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(render(entries))
    os.replace(tmp, path)


def read_entry(arg):
    try:
        return json.loads(Path(arg).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(f"cannot read {arg}: {exc}")


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    root = report_dir()
    page = root / "index.html"
    cmd = argv[1]
    if cmd == "path":
        print(page)
    elif cmd in ("check", "add") and len(argv) == 3:
        entry = read_entry(argv[2])
        problems = validate(entry)
        if problems:
            fail("invalid entry:\n  " + "\n  ".join(problems))
        if cmd == "check":
            print("ok")
            return 0
        with locked(root):
            entries = load(page)
            entry = copy_media(entry, root)
            key = (entry["date"], entry["project"], entry["ticket"])
            entries = [x for x in entries if (x["date"], x["project"], x["ticket"]) != key] + [entry]
            write(page, entries)
        print(f"added {entry['ticket']} ({entry['verdict']}) to {page}")
    elif cmd == "render":
        with locked(root):
            write(page, load(page))
        print(page)
    else:
        fail("usage: hunt_report.py check|add <entry.json> | render | path")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
