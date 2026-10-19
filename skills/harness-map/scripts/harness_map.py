#!/usr/bin/env python3
"""Inspect the agent harness (this repo's install, hooks, tools, plugins, one project) and write one self-contained HTML report.

Read-only: it never writes outside --out, never prints a secret value, and never runs anything that builds, installs or deploys.
Usage: python3 harness_map.py [--project DIR] [--out FILE] [--no-probe] [--open]
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE = Path(os.environ.get("CLAUDE_DIR", HOME / ".claude"))
REPO = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO / "skills"


def _main_checkout():
    """The repo's main worktree, so fix commands never point at a throwaway task worktree."""
    try:
        so = subprocess.run(["git", "-C", str(REPO), "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=10).stdout
        first = so.split("\n", 1)[0]
        return Path(first[len("worktree "):]) if first.startswith("worktree ") else REPO
    except (OSError, subprocess.TimeoutExpired):
        return REPO


MAIN = _main_checkout()

# Ranked by how much each status blocks work; drives sorting and the readiness score.
RANK = {"fail": 0, "missing": 1, "warn": 2, "ok": 3, "info": 4, "skip": 5}
LABEL = {"fail": "Failing", "missing": "Missing", "warn": "Attention", "ok": "OK", "info": "Info", "skip": "Skipped"}

# CLI tools the skills call. kind: required = most sessions need it; skill = only the named skills need it.
TOOLS = [
    ("git", "required", ["worktree-flow"], "brew install git"),
    ("python3", "required", ["hooks"], "brew install python"),
    ("gh", "required", ["worktree-flow", "fresh-review"], "brew install gh && gh auth login"),
    ("jq", "required", ["project-init", "environments"], "brew install jq"),
    ("node", "required", ["vision", "chrome-devtools-axi", "environments"], "brew install node"),
    ("npx", "required", ["vision", "chrome-devtools-axi", "environments"], "brew install node"),
    ("pnpm", "skill", ["project-init"], "corepack enable pnpm"),
    ("glab", "skill", ["worktree-flow (GitLab repos)"], "brew install glab && glab auth login"),
    ("docker", "skill", ["server-touch"], "brew install --cask docker"),
    ("no-mistakes", "skill", ["no-mistakes"], "see github.com/kunchenguid/no-mistakes"),
    ("gnhf", "skill", ["gnhf"], "see github.com/kunchenguid/gnhf"),
    ("op", "skill", ["environments (op:// secrets)"], "brew install 1password-cli"),
    ("vercel", "skill", ["environments (Vercel targets)"], "npm i -g vercel"),
    ("supabase", "skill", ["environments (Supabase targets)"], "brew install supabase/tap/supabase"),
]

SECRET_KEY = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|PRIVATE_KEY|ACCESS_KEY|CREDENTIAL)", re.I)


def check(section, title, status, detail="", fix="", group=""):
    return {"section": section, "title": title, "status": status, "detail": detail, "fix": fix, "group": group}


def run(cmd, cwd=None, timeout=20):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", str(e)


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


def link_check(section, title, dst, src, fix):
    dst, src = Path(dst), Path(src)
    if dst.is_symlink():
        target = Path(os.path.realpath(dst))
        if target == src.resolve():
            return check(section, title, "ok", f"{short(dst)} -> {short(src)}")
        if target.exists() and target.name == src.name and same_repo(target, src):
            return check(section, title, "ok", f"{short(dst)} -> {short(target)} (another checkout of this repo)")
        return check(section, title, "warn", f"{short(dst)} points to {short(target)}, not this repo", fix)
    if dst.exists():
        return check(section, title, "warn", f"{short(dst)} is a real file, not a link to this repo; edits here do not apply", fix)
    return check(section, title, "missing", f"{short(dst)} does not exist", fix)


def same_repo(a, b):
    """True when both paths sit in checkouts (main or linked worktrees) of one git repo."""
    dirs = []
    for p in (a, b):
        code, so, _ = run(["git", "-C", str(p if p.is_dir() else p.parent), "rev-parse", "--path-format=absolute", "--git-common-dir"])
        dirs.append(so.strip() if code == 0 else None)
    return dirs[0] is not None and dirs[0] == dirs[1]


def short(p):
    s = str(p)
    return "~" + s[len(str(HOME)):] if s.startswith(str(HOME)) else s


# ---------------------------------------------------------------- collectors

def collect_global():
    install = f"{short(MAIN)}/install.sh"
    return [
        link_check("Global instructions", "~/.claude/CLAUDE.md -> AGENTS.md", CLAUDE / "CLAUDE.md", REPO / "AGENTS.md", install),
        link_check("Global instructions", "~/OPINIONS.md -> OPINIONS.md", HOME / "OPINIONS.md", REPO / "OPINIONS.md", install),
        link_check("Global instructions", "~/.claude/agent-skills-hooks -> hooks/", CLAUDE / "agent-skills-hooks", REPO / "hooks", install),
    ]


def collect_skills():
    checks, cards = [], []
    readme = (REPO / "README.md").read_text() if (REPO / "README.md").exists() else ""
    install = f"{short(MAIN)}/install.sh"
    for d in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        name = d.name
        fm = frontmatter(d / "SKILL.md")
        issues = []
        if fm is None:
            issues.append("SKILL.md missing or has no frontmatter")
            fm = {}
        if fm and fm.get("name") != name:
            issues.append(f"frontmatter name '{fm.get('name')}' differs from folder")
        desc = fm.get("description", "")
        if fm and not desc:
            issues.append("no description")
        elif desc and not re.match(r"^Use (when|before|after|at|on)\b", desc):
            issues.append("description does not start with 'Use when/before' (knowledge-placement)")
        if len(desc) > 600:
            issues.append(f"description is {len(desc)} chars (aim under ~500)")
        if f"`{name}`" not in readme:
            issues.append("not listed in README skills table")

        dst = CLAUDE / "skills" / name
        lc = link_check("Skills", name, dst, d, install)
        status = lc["status"]
        detail = lc["detail"]
        if issues and status == "ok":
            status, detail = "warn", "; ".join(issues)
        elif issues:
            detail += "; " + "; ".join(issues)
        checks.append(check("Skills", name, status, detail, lc["fix"] if lc["status"] != "ok" else "", group="skill"))
        cards.append({
            "name": name,
            "status": status,
            "installed": lc["status"] == "ok",
            "invocable": fm.get("user-invocable", "").lower() == "true",
            "desc": desc,
            "issues": issues,
            "extras": sorted(p.name for p in d.iterdir() if p.is_dir()),
        })

    # Skills in ~/.claude/skills that do not come from this repo.
    foreign = []
    if (CLAUDE / "skills").is_dir():
        for p in sorted((CLAUDE / "skills").iterdir()):
            if p.name.startswith(".") or (SKILLS_DIR / p.name).exists():
                continue
            if p.is_symlink() and not p.exists():
                checks.append(check("Skills", f"{p.name} (dangling link)", "warn",
                                    f"{short(p)} points to {os.readlink(p)}, which no longer exists", f"rm {short(p)}"))
            elif (p / "SKILL.md").exists():
                foreign.append(p.name)
    if foreign:
        checks.append(check("Skills", "Other user skills", "info",
                            f"{len(foreign)} skills in ~/.claude/skills not from this repo: " + ", ".join(foreign)))
    return checks, cards


def collect_hooks(probe):
    out = []
    settings = load_json(CLAUDE / "settings.json")
    if settings is None:
        return [check("Hooks", "settings.json", "missing", f"{short(CLAUDE / 'settings.json')} missing or not valid JSON")]
    local = load_json(CLAUDE / "settings.local.json") or {}
    cmds = [h.get("command", "") for src in (settings, local)
            for e in src.get("hooks", {}).get("PreToolUse", []) for h in e.get("hooks", [])]
    for script in ("no-em-dash.py", "guard-protected-branches.py"):
        src = REPO / "hooks" / script
        if not src.exists():
            out.append(check("Hooks", script, "info", "not in this checkout of the repo"))
            continue
        if any(script in c for c in cmds):
            out.append(check("Hooks", f"{script} registered", "ok", "listed under hooks.PreToolUse in settings.json or settings.local.json"))
        else:
            out.append(check("Hooks", f"{script} registered", "missing",
                             "not in hooks.PreToolUse; the rule it enforces is advisory only",
                             "merge the entry from hooks/README.md into hooks.PreToolUse in ~/.claude/settings.json"))
    test = REPO / "hooks" / "test.sh"
    if not probe:
        out.append(check("Hooks", "hooks/test.sh probes", "skip", "skipped (--no-probe)"))
    elif test.exists():
        code, so, se = run(["bash", str(test)], timeout=90)
        fails = [ln for ln in (so + se).splitlines() if ln.startswith("FAIL") or "WARN" in ln]
        if code == 0:
            n = sum(1 for ln in so.splitlines() if ln.startswith("ok"))
            out.append(check("Hooks", "hooks/test.sh probes", "ok", f"{n} allow/ask/deny probes pass"))
        else:
            out.append(check("Hooks", "hooks/test.sh probes", "fail",
                             "; ".join(fails[:4]) or (se.strip().splitlines() or ["exit " + str(code)])[-1],
                             f"bash {short(test)}"))
    other = {e.get("matcher", "") or "*" for ev in settings.get("hooks", {}).values() for e in ev}
    events = sorted(settings.get("hooks", {}).keys())
    out.append(check("Hooks", "Hook events wired", "info",
                     f"{len(events)} events ({', '.join(events)}); matchers: {', '.join(sorted(other))}"))
    return out


def collect_tools(probe, registry, project):
    out, rows = [], []
    reg_text = json.dumps(registry) if registry else ""
    remote = run(["git", "-C", str(project), "remote", "get-url", "origin"])[1] if project else ""
    # Missing CLIs that only matter when the project or registry uses them stay informational.
    needed = {"glab": "gitlab" in remote, "op": "op://" in reg_text,
              "vercel": "vercel" in reg_text.lower(), "supabase": "supabase" in reg_text.lower()}
    for name, kind, used_by, fix in TOOLS:
        path = shutil.which(name)
        version = ""
        if path and name not in ("npx",):
            code, so, se = run([name, "--version"], timeout=8)
            version = ((so or se).strip().splitlines() or [""])[0][:60]
        if path:
            status = "ok"
        elif kind == "required":
            status = "missing"
        elif name in needed:
            status = "missing" if needed[name] else "info"
        else:
            status = "warn"
        detail = (f"{version or short(path)}" if path else "not on PATH") + " - used by " + ", ".join(used_by)
        out.append(check("Tools", name, status, detail, "" if path else fix, group="tool"))
        rows.append({"name": name, "status": status, "version": version, "kind": kind, "used_by": used_by})

    if shutil.which("gh") and probe:
        code, so, se = run(["gh", "auth", "status"], timeout=15)
        acct = re.findall(r"account (\S+)", so + se)
        if code == 0:
            out.append(check("Tools", "gh auth", "ok", "logged in as " + (", ".join(sorted(set(acct))) or "unknown")))
        else:
            out.append(check("Tools", "gh auth", "fail", "gh is not logged in or the token expired", "! gh auth login"))
    return out, rows


def collect_plugins():
    out, plugins = [], []
    settings = load_json(CLAUDE / "settings.json") or {}
    enabled = settings.get("enabledPlugins", {})
    installed = (load_json(CLAUDE / "plugins" / "installed_plugins.json") or {}).get("plugins", {})
    mcp_names = []
    for pid, on in sorted(enabled.items()):
        inst = (installed.get(pid) or [{}])[-1]
        path = Path(inst.get("installPath", ""))
        mcp = load_json(path / ".mcp.json") or {}
        servers = sorted((mcp.get("mcpServers", mcp) or {}).keys()) if isinstance(mcp, dict) else []
        skills = sorted(p.name for p in (path / "skills").iterdir() if p.is_dir()) if (path / "skills").is_dir() else []
        mcp_names += servers
        plugins.append({"id": pid, "on": bool(on), "version": inst.get("version", "?"), "mcp": servers, "skills": len(skills)})
        if not on:
            out.append(check("Plugins & MCP", pid, "info", "installed but disabled"))
        elif not path.exists():
            out.append(check("Plugins & MCP", pid, "fail", "enabled but install path is missing", f"claude plugin install {pid}"))
        else:
            out.append(check("Plugins & MCP", pid, "ok",
                             f"v{inst.get('version', '?')}; {len(skills)} skills; MCP: {', '.join(servers) or 'none'}"))
    user_mcp = sorted(((load_json(HOME / ".claude.json") or {}).get("mcpServers") or {}).keys())
    mcp_names += user_mcp
    if user_mcp:
        out.append(check("Plugins & MCP", "User MCP servers", "info", ", ".join(user_mcp)))
    if any("playwright" in n.lower() for n in mcp_names):
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "ok", "Playwright MCP is available (first choice)"))
    elif shutil.which("npx"):
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "warn",
                         "no Playwright MCP; e2e-verify falls back to chrome-devtools-axi through npx",
                         "claude mcp add playwright -- npx -y @playwright/mcp@latest"))
    else:
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "missing", "no Playwright MCP and no npx",
                         "brew install node"))
    return out, plugins


def collect_hygiene():
    out = []
    settings = load_json(CLAUDE / "settings.json") or {}

    def literal_secrets(env):
        return [k for k, v in (env or {}).items()
                if SECRET_KEY.search(k) and isinstance(v, str) and v and not v.startswith(("op://", "$", "${"))]

    # Key names only, with where they sit; values never leave this function.
    found = [f"{k} (settings.json)" for k in literal_secrets(settings.get("env"))]
    found += [f"{k} (settings.local.json)" for k in literal_secrets((load_json(CLAUDE / "settings.local.json") or {}).get("env"))]
    for name, srv in (((load_json(HOME / ".claude.json") or {}).get("mcpServers")) or {}).items():
        found += [f"{k} (~/.claude.json MCP {name})" for k in literal_secrets((srv or {}).get("env"))]
    keys = {f.split(" ", 1)[0] for f in found}
    backups = sorted(CLAUDE.glob("settings*.json.bak*"))
    leaky = [b for b in backups if any(k in b.read_text(errors="ignore") for k in keys)] if keys else []
    if found:
        detail = "literal values for " + ", ".join(found) + " (values not shown)"
        if leaky:
            detail += "; also in " + ", ".join(b.name for b in leaky)
        out.append(check("Settings hygiene", "Plaintext secrets in settings", "fail", detail,
                         "move them to the macOS keychain or a gitignored env file, rotate the tokens, delete the backup copies that hold them"))
    else:
        out.append(check("Settings hygiene", "Plaintext secrets in settings", "ok", "no secret-looking env values"))
    if backups and len(backups) > len(leaky):
        out.append(check("Settings hygiene", "settings.json backups", "info",
                         f"{len(backups)} backup files next to settings.json", "review and delete the ones you no longer need"))
    if settings.get("skipDangerousModePermissionPrompt"):
        out.append(check("Settings hygiene", "Bypass-permissions prompt skipped", "info",
                         "bypass mode starts without a warning; guard-protected-branches denies protected pushes there"))
    return out


def collect_project(project):
    sec = "Project"
    out, registry = [], None
    if not project:
        return [check(sec, "Project", "skip", "no git project given (--project)")], None
    p = Path(project)
    out.append(check(sec, "Repository", "info", short(p)))
    agents = p / "AGENTS.md"
    if not agents.exists():
        out.append(check(sec, "AGENTS.md", "missing", "no project AGENTS.md", "run the project-init skill"))
        text = ""
    else:
        text = agents.read_text()
        starts, ends = text.count("project-init:start"), text.count("project-init:end")
        if starts == ends == 1:
            out.append(check(sec, "project-init block", "ok", "one start and one end marker"))
        elif starts == ends == 0:
            out.append(check(sec, "project-init block", "missing", "AGENTS.md has no project-init block", "run the project-init skill"))
        else:
            out.append(check(sec, "project-init block", "fail", f"{starts} start / {ends} end markers", "fix the markers by hand, then re-run project-init"))
    claude_md = p / "CLAUDE.md"
    if claude_md.exists() and "@AGENTS.md" in claude_md.read_text():
        out.append(check(sec, "CLAUDE.md imports AGENTS.md", "ok", "CLAUDE.md contains @AGENTS.md"))
    elif agents.exists():
        out.append(check(sec, "CLAUDE.md imports AGENTS.md", "warn", "Claude Code will not read AGENTS.md", "echo '@AGENTS.md' > CLAUDE.md"))

    reg = p / ".agents" / "environments.json"
    if reg.exists():
        registry = load_json(reg)
        if registry is None:
            out.append(check(sec, "Environment registry", "fail", ".agents/environments.json is not valid JSON", "fix the JSON, then validate per the environments skill"))
        else:
            envs = registry.get("environments", registry) if isinstance(registry, dict) else {}
            names = list(envs.keys()) if isinstance(envs, dict) else [e.get("name", "?") for e in envs]
            out.append(check(sec, "Environment registry", "ok", "environments: " + (", ".join(names) or "none")))
        gi = (p / ".gitignore").read_text() if (p / ".gitignore").exists() else ""
        if "secrets.env" not in gi:
            out.append(check(sec, "Secrets gitignored", "fail", ".agents/secrets.env is not in .gitignore", "echo '.agents/secrets.env' >> .gitignore"))
    else:
        out.append(check(sec, "Environment registry", "missing", "no .agents/environments.json; deploy/SSH skills will ask every time", "run the environments skill (create section)"))

    todos = []
    for f in (agents, reg):
        if f.exists():
            todos += [f"{f.name}:{i}" for i, ln in enumerate(f.read_text().splitlines(), 1) if "TODO(" in ln]
    if todos:
        out.append(check(sec, "Open TODO(owner)", "warn", ", ".join(todos[:8]), "answer them and re-run project-init"))

    int_branch = None
    if isinstance(registry, dict):
        envs = registry.get("environments", {})
        dev = envs.get("dev") if isinstance(envs, dict) else next((e for e in envs if e.get("name") == "dev"), None)
        int_branch = (dev or {}).get("branch")
    code, so, _ = run(["git", "-C", str(p), "branch", "-r", "--format=%(refname:short)"])
    remote = set(so.split())
    cand = int_branch or "dev"
    if f"origin/{cand}" in remote:
        out.append(check(sec, "Integration branch", "ok", f"origin/{cand} exists" + ("" if int_branch else " (default dev)")))
    else:
        out.append(check(sec, "Integration branch", "missing",
                         f"origin/{cand} not found in fetched refs; worktree-flow will stop and ask where PRs go",
                         "create the branch or record it as the dev environment's branch in .agents/environments.json"))

    pw = list(p.glob("playwright.config.*")) + list(p.glob("*/playwright.config.*")) + list(p.glob("apps/*/playwright.config.*"))
    out.append(check(sec, "Playwright config", "ok" if pw else "info",
                     ", ".join(short(x) for x in pw[:3]) if pw else "none found; e2e-verify drives the browser ad hoc"))
    return out, registry


# ---------------------------------------------------------------- render

CSS = r"""
:root{--bg:#f7f7f9;--surface:#fff;--surface-2:#f6f6f8;--surface-3:#eeeef2;--border:rgba(28,28,28,.08);--border-2:rgba(28,28,28,.13);
--text:#1c1c1c;--text-2:#3a3a41;--muted:#5f5f66;--accent:#4a38f5;--accent-soft:#efedfe;--accent-text:#3b2ad9;
--agent:#ed87fc;--agent-soft:#fcebfe;--agent-text:#7a1f87;
--ok:#1a7f37;--ok-soft:#e8f5ec;--ok-text:#156b2e;--warn:#9a8300;--warn-soft:#fdfbd0;--warn-text:#7a6a00;
--bad:#b42318;--bad-soft:#fdedeb;--bad-text:#b42318;--neutral:#8a8a93;--neutral-soft:#f0f0f3;--neutral-text:#55555c;
--code-bg:#15151b;--code-text:#e7e7ee;--code-muted:#a0a0ae;
--shadow-1:0 1px 2px rgba(0,0,0,.04);--shadow-2:0 6px 16px -4px rgba(16,16,40,.1),0 1px 3px rgba(16,16,40,.05);
--brand:linear-gradient(140deg,#6553ff 0%,#4a38f5 55%,#3420d8 100%);color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#0f1011;--surface:#141516;--surface-2:#191a1b;--surface-3:#1c1c1f;
--border:rgba(255,255,255,.08);--border-2:rgba(255,255,255,.13);--text:#ededf0;--text-2:#d2d2d9;--muted:#a3a3ad;
--accent:#6b5cff;--accent-soft:rgba(124,110,255,.16);--accent-text:#aba2ff;--agent-soft:rgba(237,135,252,.13);--agent-text:#f4b9fd;
--ok:#3fb760;--ok-soft:rgba(63,183,96,.15);--ok-text:#6fd68c;--warn:#e3cf3a;--warn-soft:rgba(254,255,183,.1);--warn-text:#eee68e;
--bad:#f26b5e;--bad-soft:rgba(242,107,94,.15);--bad-text:#ff9187;--neutral:#8e8e98;--neutral-soft:rgba(255,255,255,.07);--neutral-text:#bdbdc6;
--code-bg:#08090a;--shadow-1:0 1px 2px rgba(0,0,0,.35);--shadow-2:0 8px 20px -6px rgba(0,0,0,.5),0 1px 3px rgba(0,0,0,.35);color-scheme:dark}}
:root[data-theme="dark"]{--bg:#0f1011;--surface:#141516;--surface-2:#191a1b;--surface-3:#1c1c1f;
--border:rgba(255,255,255,.08);--border-2:rgba(255,255,255,.13);--text:#ededf0;--text-2:#d2d2d9;--muted:#a3a3ad;
--accent:#6b5cff;--accent-soft:rgba(124,110,255,.16);--accent-text:#aba2ff;--agent-soft:rgba(237,135,252,.13);--agent-text:#f4b9fd;
--ok:#3fb760;--ok-soft:rgba(63,183,96,.15);--ok-text:#6fd68c;--warn:#e3cf3a;--warn-soft:rgba(254,255,183,.1);--warn-text:#eee68e;
--bad:#f26b5e;--bad-soft:rgba(242,107,94,.15);--bad-text:#ff9187;--neutral:#8e8e98;--neutral-soft:rgba(255,255,255,.07);--neutral-text:#bdbdc6;
--code-bg:#08090a;--shadow-1:0 1px 2px rgba(0,0,0,.35);--shadow-2:0 8px 20px -6px rgba(0,0,0,.5),0 1px 3px rgba(0,0,0,.35);color-scheme:dark}
*{box-sizing:border-box}html,body{margin:0}
body{background:var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
.mono,code{font-family:"Azeret Mono",ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}
header.top{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--bg) 82%,transparent);backdrop-filter:blur(12px);border-bottom:1px solid var(--border)}
.top .wrap{display:flex;align-items:center;gap:12px;height:56px}
.mark{width:28px;height:28px;border-radius:8px;background:var(--brand);display:grid;place-items:center;box-shadow:0 1px 2px rgba(74,56,245,.3),inset 0 1px 0 rgba(255,255,255,.15)}
.brand{font-family:"Host Grotesk",Inter,sans-serif;font-weight:600;letter-spacing:-.01em}
.crumb{color:var(--muted)}.sp{flex:1}
.seg{display:inline-flex;background:var(--surface-3);border-radius:8px;padding:2px;gap:2px}
.seg button{all:unset;cursor:pointer;padding:4px 10px;border-radius:6px;color:var(--muted);font-size:12px;font-weight:500}
.seg button[aria-pressed="true"]{background:var(--surface);color:var(--text);box-shadow:0 1px 2px rgba(0,0,0,.08),0 0 0 1px var(--border)}
.hero{padding:40px 0 24px;display:grid;grid-template-columns:1fr auto;gap:32px;align-items:end}
.eyebrow{font-size:12px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:var(--accent-text)}
h1{font-family:"Host Grotesk",Inter,sans-serif;font-size:34px;line-height:1.15;letter-spacing:-.02em;margin:8px 0 10px;font-weight:600}
.sub{color:var(--muted);max-width:640px;margin:0}
.meta{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:16px;color:var(--muted);font-size:12px}
.meta b{color:var(--text-2);font-weight:500}
.ring{position:relative;width:132px;height:132px}
.ring svg{transform:rotate(-90deg)}
.ring .v{position:absolute;inset:0;display:grid;place-items:center;text-align:center}
.ring .v b{font-family:"Host Grotesk",Inter,sans-serif;font-size:32px;font-weight:600;letter-spacing:-.02em;display:block;line-height:1}
.ring .v span{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:28px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow-1)}
.stat .n{font-family:"Host Grotesk",Inter,sans-serif;font-size:26px;font-weight:600;letter-spacing:-.02em}
.stat .l{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px}
.dot{width:8px;height:8px;border-radius:50%;background:var(--neutral);flex:none}
.dot.ok{background:var(--ok)}.dot.warn{background:var(--warn)}.dot.fail,.dot.missing{background:var(--bad)}.dot.info{background:var(--accent)}
.grid{display:grid;grid-template-columns:240px 1fr;gap:28px;padding-bottom:64px}
nav.side{position:sticky;top:76px;align-self:start;display:flex;flex-direction:column;gap:2px}
nav.side .h{font-size:11px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding:8px 10px 4px}
nav.side a{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:6px;color:var(--text-2);text-decoration:none;font-size:13px}
nav.side a:hover{background:var(--surface-3)}
nav.side a .c{margin-left:auto;font-size:11px;color:var(--muted)}
section.card{background:var(--surface);border:1px solid var(--border);border-radius:14px;box-shadow:var(--shadow-1);margin-bottom:20px;overflow:hidden;scroll-margin-top:72px}
.card>.hd{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--border)}
.card>.hd h2{font-size:15px;font-weight:600;margin:0;letter-spacing:-.005em}
.card>.hd .desc{color:var(--muted);font-size:12px}
.card>.hd .bar{margin-left:auto;display:flex;gap:4px}
.pill{display:inline-flex;align-items:center;gap:5px;height:22px;padding:0 8px;border-radius:999px;font-size:11.5px;font-weight:500;white-space:nowrap;border:1px solid transparent}
.pill.ok{background:var(--ok-soft);color:var(--ok-text)}.pill.warn{background:var(--warn-soft);color:var(--warn-text)}
.pill.fail,.pill.missing{background:var(--bad-soft);color:var(--bad-text)}.pill.info{background:var(--accent-soft);color:var(--accent-text)}
.pill.skip{background:var(--neutral-soft);color:var(--neutral-text)}
.row{display:grid;grid-template-columns:104px 260px 1fr;gap:14px;padding:11px 18px;border-top:1px solid var(--border);align-items:start}
.row:first-of-type{border-top:0}
.row .t{font-weight:500;word-break:break-word}.row .d{color:var(--text-2);word-break:break-word}
.fix{display:flex;align-items:center;gap:8px;margin-top:6px;background:var(--code-bg);color:var(--code-text);border-radius:8px;padding:6px 6px 6px 10px}
.fix code{flex:1;overflow-x:auto;white-space:nowrap;color:var(--code-text)}
.fix code::before{content:"$ ";color:var(--agent)}
.hint{margin-top:6px;font-size:12.5px;color:var(--accent-text);display:flex;gap:6px}
.hint::before{content:"\2192"}
.copy{all:unset;cursor:pointer;font-size:11px;color:var(--code-muted);padding:2px 8px;border-radius:5px;border:1px solid rgba(255,255,255,.1)}
.copy:hover{color:#fff;border-color:rgba(255,255,255,.25)}
body.only-action .row[data-s="ok"],body.only-action .row[data-s="info"],body.only-action .row[data-s="skip"]{display:none}
body.only-action .skill[data-s="ok"]{display:none}
.todo{padding:6px 18px 14px}
.todo ol{margin:0;padding:0;list-style:none;counter-reset:t}
.todo li{counter-increment:t;display:grid;grid-template-columns:28px 1fr;gap:10px;padding:12px 0;border-top:1px solid var(--border)}
.todo li:first-child{border-top:0}
.todo li::before{content:counter(t);width:22px;height:22px;border-radius:6px;display:grid;place-items:center;font-size:11px;font-weight:600;background:var(--accent-soft);color:var(--accent-text)}
.todo .tt{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.todo .tt b{font-weight:600}
.todo .sec{font-size:11px;color:var(--muted)}
.skills{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px;padding:16px 18px}
.skill{border:1px solid var(--border);border-radius:10px;padding:12px 14px;background:var(--surface-2);display:flex;flex-direction:column;gap:8px;transition:border-color .15s,box-shadow .15s}
.skill:hover{border-color:var(--border-2);box-shadow:var(--shadow-2)}
.skill .nm{display:flex;align-items:center;gap:8px;font-weight:600}
.skill .nm .dot{margin-left:auto}
.skill p{margin:0;color:var(--muted);font-size:12px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{font-size:11px;padding:1px 7px;border-radius:5px;background:var(--surface-3);color:var(--text-2)}
.chip.agent{background:var(--agent-soft);color:var(--agent-text)}.chip.acc{background:var(--accent-soft);color:var(--accent-text)}
.chip.bad{background:var(--bad-soft);color:var(--bad-text)}.chip.warn{background:var(--warn-soft);color:var(--warn-text)}
.flow{padding:18px;overflow-x:auto}
.flow svg{display:block;min-width:720px;width:100%;height:auto}
.flow text{font-family:Inter,sans-serif;font-size:12px;fill:var(--text)}
.flow .lbl{font-size:10.5px;fill:var(--muted);text-transform:uppercase;letter-spacing:.06em}
.empty{padding:28px 18px;color:var(--muted);text-align:center}
footer{color:var(--muted);font-size:12px;padding:0 0 40px}
.seg button,.brand{white-space:nowrap}
@media (max-width:900px){.crumb,.seg[aria-label="Theme"]{display:none}.grid{grid-template-columns:1fr}nav.side{display:none}.stats{grid-template-columns:repeat(2,1fr)}
.hero{grid-template-columns:1fr}.row{grid-template-columns:1fr;gap:4px}.wrap{padding:0 16px}h1{font-size:28px}}
"""

JS = r"""
(function(){
  var root=document.documentElement, KEY='harness-map-theme';
  function setTheme(t){ if(t==='system'){root.removeAttribute('data-theme')}else{root.setAttribute('data-theme',t)}
    document.querySelectorAll('[data-theme-btn]').forEach(function(b){b.setAttribute('aria-pressed',String(b.dataset.themeBtn===t))});
    try{localStorage.setItem(KEY,t)}catch(e){} }
  var saved='system'; try{saved=localStorage.getItem(KEY)||'system'}catch(e){}
  setTheme(saved);
  document.querySelectorAll('[data-theme-btn]').forEach(function(b){b.onclick=function(){setTheme(b.dataset.themeBtn)}});
  document.querySelectorAll('[data-view]').forEach(function(b){b.onclick=function(){
    document.body.classList.toggle('only-action',b.dataset.view==='action');
    document.querySelectorAll('[data-view]').forEach(function(x){x.setAttribute('aria-pressed',String(x===b))});}});
  document.querySelectorAll('.copy').forEach(function(b){b.onclick=function(){
    var t=b.previousElementSibling.textContent;
    (navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(function(){b.textContent='Copied';setTimeout(function(){b.textContent='Copy'},1200)},function(){b.textContent='Select'});}});
})();
"""

ICONS = {
    "Global instructions": '<path d="M4 4h12v12H4z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M7 8h6M7 11h4" stroke="currentColor" stroke-width="1.6"/>',
    "Skills": '<path d="M10 3l6 3.5v7L10 17l-6-3.5v-7z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Hooks": '<path d="M7 4v6a3 3 0 006 0V8" fill="none" stroke="currentColor" stroke-width="1.6"/><circle cx="13" cy="6" r="2" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Tools": '<path d="M4 6l4 4-4 4M10 14h6" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Plugins & MCP": '<path d="M8 3v4M12 3v4M6 7h8v3a4 4 0 01-8 0zM10 14v3" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Settings hygiene": '<path d="M10 3l6 2.5V10c0 3.5-2.6 6-6 7-3.4-1-6-3.5-6-7V5.5z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
    "Project": '<path d="M3 6h5l2 2h7v8H3z" fill="none" stroke="currentColor" stroke-width="1.6"/>',
}
DESCS = {
    "Global instructions": "Files install.sh links so every session reads them",
    "Skills": "This repo's skills, their install link and frontmatter health",
    "Hooks": "Gates that turn AGENTS.md rules into enforcement",
    "Tools": "CLIs the skills shell out to",
    "Plugins & MCP": "Enabled plugins and the MCP servers they bring",
    "Settings hygiene": "Secrets and risky toggles in ~/.claude/settings.json",
    "Project": "Per-repo agent setup written by project-init",
}
ORDER = list(DESCS)


def esc(s):
    return html.escape(str(s), quote=True)


def icon(sec):
    return f'<svg width="16" height="16" viewBox="0 0 20 20" aria-hidden="true">{ICONS.get(sec, "")}</svg>'


def pill(s):
    return f'<span class="pill {s}"><span class="dot {s}"></span>{LABEL[s]}</span>'


CMD = re.compile(r"^(~|/|!|\$|(brew|npm|npx|bash|echo|rm|claude|corepack|git|gh|glab)\b)")


def fix_html(fix):
    if not fix:
        return ""
    if not CMD.match(fix):
        return f'<div class="hint">{esc(fix)}</div>'
    return f'<div class="fix"><code>{esc(fix)}</code><button class="copy" type="button">Copy</button></div>'


def ring(score):
    r, c = 54, 2 * 3.14159 * 54
    color = "var(--ok)" if score >= 85 else "var(--warn)" if score >= 60 else "var(--bad)"
    return (f'<div class="ring"><svg width="132" height="132" viewBox="0 0 132 132">'
            f'<circle cx="66" cy="66" r="{r}" fill="none" stroke="var(--surface-3)" stroke-width="10"/>'
            f'<circle cx="66" cy="66" r="{r}" fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round" '
            f'stroke-dasharray="{c * score / 100:.1f} {c:.1f}"/></svg>'
            f'<div class="v"><div><b>{score}%</b><span>ready</span></div></div></div>')


def flow_svg(by_sec):
    """Layered picture of the harness: what loads always, on demand, as gates, and what it calls out to."""
    def worst(sec):
        items = by_sec.get(sec, [])
        return min((c["status"] for c in items), key=RANK.get, default="skip")
    cols = [
        ("Always loaded", [("AGENTS.md", "Global instructions"), ("OPINIONS.md", "Global instructions")]),
        ("On demand", [("Skills", "Skills"), ("Plugins", "Plugins & MCP")]),
        ("Gates", [("PreToolUse hooks", "Hooks"), ("Settings", "Settings hygiene")]),
        ("Calls out to", [("CLIs", "Tools"), ("Project setup", "Project")]),
    ]
    color = {"ok": "var(--ok)", "warn": "var(--warn)", "fail": "var(--bad)", "missing": "var(--bad)", "info": "var(--accent)", "skip": "var(--neutral)"}
    w, colw, boxw, boxh = 960, 240, 196, 52
    parts = ['<svg viewBox="0 0 960 190" role="img" aria-label="Harness layers">']
    for i, (lbl, boxes) in enumerate(cols):
        x = i * colw + 22
        parts.append(f'<text class="lbl" x="{x}" y="16">{esc(lbl)}</text>')
        for j, (name, sec) in enumerate(boxes):
            y = 32 + j * 76
            st = worst(sec)
            parts.append(f'<rect x="{x}" y="{y}" width="{boxw}" height="{boxh}" rx="10" fill="var(--surface-2)" stroke="var(--border-2)"/>'
                         f'<rect x="{x}" y="{y + 14}" width="3" height="{boxh - 28}" rx="1.5" fill="{color[st]}"/>'
                         f'<text x="{x + 16}" y="{y + 22}" font-weight="600">{esc(name)}</text>'
                         f'<text x="{x + 16}" y="{y + 40}" style="fill:var(--muted);font-size:11px">{esc(LABEL[st])}</text>')
            if i < len(cols) - 1:
                parts.append(f'<path d="M{x + boxw + 4} {y + boxh / 2} H{x + colw - 6}" stroke="var(--border-2)" stroke-width="1.5" '
                             f'fill="none" marker-end="url(#ah)"/>')
    parts.append('<defs><marker id="ah" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
                 '<path d="M0 0L8 4L0 8z" fill="var(--border-2)"/></marker></defs></svg>')
    return "".join(parts)


def render(checks, cards, plugins, project, probe):
    by_sec = {}
    for c in checks:
        by_sec.setdefault(c["section"], []).append(c)
    # Every skill row is one check, so together they weigh 3; otherwise 20 uninstalled skills drown everything else.
    scored = [c for c in checks if c["status"] in ("ok", "warn", "fail", "missing")]
    n_skill = sum(1 for c in scored if c["group"] == "skill")
    weight = lambda c: 3 / n_skill if c["group"] == "skill" else 1
    value = {"ok": 1, "warn": 0.5}
    score = round(100 * sum(weight(c) * value.get(c["status"], 0) for c in scored) / max(1, sum(weight(c) for c in scored)))
    count = {s: sum(1 for c in checks if c["status"] == s) for s in RANK}
    actions = group_actions(checks)

    code, sha, _ = run(["git", "-C", str(REPO), "log", "-1", "--format=%h %s"])
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    h = []
    h.append('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
             '<title>Harness Map</title>'
             '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Host+Grotesk:wght@500;600&family=Azeret+Mono:wght@400;500&display=swap" rel="stylesheet">'
             f'<style>{CSS}</style></head><body>')
    h.append('<header class="top"><div class="wrap"><div class="mark"><svg width="16" height="16" viewBox="0 0 20 20"><path d="M10 2l7 4v8l-7 4-7-4V6z" fill="none" stroke="#fff" stroke-width="1.8"/><circle cx="10" cy="10" r="2.4" fill="#fff"/></svg></div>'
             '<span class="brand">Harness Map</span><span class="crumb">/ ' + esc(socket.gethostname().split(".")[0]) + '</span><span class="sp"></span>'
             '<div class="seg" role="group" aria-label="Filter"><button data-view="all" aria-pressed="true">All</button><button data-view="action" aria-pressed="false">Needs action</button></div>'
             '<div class="seg" role="group" aria-label="Theme"><button data-theme-btn="light">Light</button><button data-theme-btn="system">Auto</button><button data-theme-btn="dark">Dark</button></div>'
             '</div></header><main class="wrap">')
    proj = f'<span>Project <b class="mono">{esc(short(project))}</b></span>' if project else ""
    h.append(f'<div class="hero"><div><div class="eyebrow">Agent harness</div><h1>What is set up, what is missing</h1>'
             f'<p class="sub">Global instructions, skills, hooks, tools, plugins and the current project, checked live on this machine. '
             f'Fix the numbered list from the top; every command is copyable.</p>'
             f'<div class="meta"><span>Generated <b>{now}</b></span><span>Repo <b class="mono">{esc(short(REPO))}</b></span>'
             f'<span>Commit <b class="mono" title="{esc(sha.strip())}">{esc(sha.strip() if len(sha.strip()) <= 52 else sha.strip()[:50] + "...")}</b></span>{proj}'
             f'{"" if probe else "<span><b>Probes skipped</b></span>"}</div></div>{ring(score)}</div>')
    h.append('<div class="stats">' + "".join(
        f'<div class="stat"><div class="n">{n}</div><div class="l"><span class="dot {cls}"></span>{lbl}</div></div>'
        for n, cls, lbl in [(count["ok"], "ok", "OK"), (count["warn"], "warn", "Attention"),
                            (count["fail"] + count["missing"], "fail", "Missing or failing"),
                            (sum(1 for c in cards if c["installed"]), "info", f"of {len(cards)} skills installed"),
                            (len([p for p in plugins if p["on"]]), "info", "plugins enabled")]) + '</div>')

    h.append('<div class="grid"><nav class="side"><div class="h">Overview</div><a href="#map">Harness layers</a>'
             f'<a href="#todo">Fix first<span class="c">{len(actions)}</span></a><div class="h">Checks</div>')
    for sec in ORDER:
        if sec in by_sec:
            bad = sum(1 for c in by_sec[sec] if c["status"] in ("fail", "missing", "warn"))
            st = min((c["status"] for c in by_sec[sec]), key=RANK.get)
            h.append(f'<a href="#{slug(sec)}"><span class="dot {st}"></span>{esc(sec)}<span class="c">{bad or ""}</span></a>')
    h.append('<a href="#catalog">Skill catalog</a></nav><div>')

    h.append(f'<section class="card" id="map"><div class="hd">{icon("Skills")}<h2>Harness layers</h2><span class="desc">Each box shows its worst check</span></div>'
             f'<div class="flow">{flow_svg(by_sec)}</div></section>')

    h.append(f'<section class="card" id="todo"><div class="hd">{icon("Tools")}<h2>Fix first</h2><span class="desc">Failing and missing before attention items</span></div>')
    if actions:
        h.append('<div class="todo"><ol>')
        for c in actions:
            h.append(f'<li><div><div class="tt">{pill(c["status"])}<b>{esc(c["title"])}</b><span class="sec">{esc(c["section"])}</span></div>'
                     f'<div class="d" style="color:var(--text-2);margin-top:4px">{esc(c["detail"])}</div>{fix_html(c["fix"])}</div></li>')
        h.append('</ol></div>')
    else:
        h.append('<div class="empty">Nothing to fix. The harness is fully set up.</div>')
    h.append('</section>')

    for sec in ORDER:
        if sec not in by_sec:
            continue
        rows = sorted(by_sec[sec], key=lambda c: RANK[c["status"]])
        h.append(f'<section class="card" id="{slug(sec)}"><div class="hd">{icon(sec)}<h2>{esc(sec)}</h2><span class="desc">{esc(DESCS[sec])}</span><div class="bar">')
        for s in ("fail", "missing", "warn", "ok"):
            n = sum(1 for c in rows if c["status"] == s)
            if n:
                h.append(f'<span class="pill {s}">{n} {LABEL[s]}</span>')
        h.append('</div></div>')
        seen = set()
        for c in rows:
            # A fix shared by many rows (install.sh for every skill) is shown once, on its first row.
            fx = "" if c["fix"] in seen else fix_html(c["fix"])
            seen.add(c["fix"])
            h.append(f'<div class="row" data-s="{c["status"]}"><div>{pill(c["status"])}</div><div class="t">{esc(c["title"])}</div>'
                     f'<div class="d">{esc(c["detail"])}{fx}</div></div>')
        h.append('</section>')

    h.append(f'<section class="card" id="catalog"><div class="hd">{icon("Skills")}<h2>Skill catalog</h2><span class="desc">{len(cards)} skills in this repo</span></div><div class="skills">')
    for s in cards:
        chips = ['<span class="chip acc">/' + esc(s["name"]) + '</span>' if s["invocable"] else '<span class="chip agent">auto-loaded</span>']
        chips.append('<span class="chip">installed</span>' if s["installed"] else '<span class="chip bad">not installed</span>')
        chips += [f'<span class="chip">{esc(x)}/</span>' for x in s["extras"]]
        chips += [f'<span class="chip warn">{esc(i)}</span>' for i in s["issues"]]
        h.append(f'<div class="skill" data-s="{s["status"]}"><div class="nm"><span class="mono" style="font-size:13px;font-weight:600">{esc(s["name"])}</span><span class="dot {s["status"]}"></span></div>'
                 f'<p title="{esc(s["desc"])}">{esc(s["desc"])}</p><div class="chips">{"".join(chips)}</div></div>')
    h.append('</div></section>')
    h.append(f'<footer>Generated by <span class="mono">skills/harness-map/scripts/harness_map.py</span>. Read-only; secret values are never shown. '
             f'Re-run to refresh.</footer></div></div></main><script>{JS}</script></body></html>')
    return "".join(h), score, count, actions


def group_actions(checks):
    """One to-do per distinct fix: rows that share status, section and fix collapse into a single item."""
    groups = {}
    for c in checks:
        if c["status"] not in ("fail", "missing", "warn"):
            continue
        key = (c["status"], c["section"], c["fix"] or id(c))
        groups.setdefault(key, []).append(c)
    actions = []
    for (status, sec, _), items in groups.items():
        if len(items) == 1:
            actions.append(items[0])
        else:
            title = (f"{len(items)} skills not installed" if sec == "Skills" and status == "missing"
                     else f"{len(items)} items, same fix")
            actions.append(check(sec, title, status,
                                 ", ".join(i["title"] for i in items), items[0]["fix"]))
    return sorted(actions, key=lambda c: (RANK[c["status"]], ORDER.index(c["section"])))


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def git_root(path):
    code, so, _ = run(["git", "-C", str(path), "rev-parse", "--show-toplevel"])
    return Path(so.strip()) if code == 0 else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--project", help="git repo to check (default: the current directory if it is one, else skipped)")
    ap.add_argument("--out", default=str(CLAUDE / "harness-map.html"))
    ap.add_argument("--no-probe", action="store_true", help="skip hooks/test.sh and gh auth status")
    ap.add_argument("--open", action="store_true", help="open the report in the default browser")
    a = ap.parse_args()

    project = git_root(a.project or os.getcwd())
    if a.project and not project:
        sys.exit(f"--project {a.project} is not inside a git repo")
    probe = not a.no_probe

    checks = collect_global()
    sk, cards = collect_skills()
    checks += sk
    checks += collect_hooks(probe)
    pc, registry = collect_project(project)
    tc, _ = collect_tools(probe, registry, project)
    checks += tc
    plc, plugins = collect_plugins()
    checks += plc + collect_hygiene() + pc

    page, score, count, actions = render(checks, cards, plugins, project, probe)
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)

    print(f"Harness map: {out}")
    print(f"Ready {score}%  ok {count['ok']}  attention {count['warn']}  missing/failing {count['missing'] + count['fail']}")
    for i, c in enumerate(actions, 1):
        print(f"{i:>2}. [{LABEL[c['status']]}] {c['section']} / {c['title']}: {c['detail']}" + (f"\n    fix: {c['fix']}" if c["fix"] else ""))
    if a.open:
        run(["open" if sys.platform == "darwin" else "xdg-open", str(out)])


if __name__ == "__main__":
    main()
