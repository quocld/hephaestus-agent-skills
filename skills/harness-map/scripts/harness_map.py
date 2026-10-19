#!/usr/bin/env python3
"""Inspect the agent harness (this repo's install, hooks, tools, plugins, one project) and write one self-contained HTML report.

Read-only: it never writes outside --out, never prints a secret value, and never runs anything that builds, installs or deploys.
Usage: python3 harness_map.py [--project DIR] [--out FILE] [--no-probe] [--open]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import socket
import sys
from pathlib import Path

from page import (CLAUDE, HOME, LABEL, MAIN, PILLARS, RANK, REPO, SKILL, SKILLS_DIR, WHEEL_WORD, esc, frontmatter, icon,
                  load_json, pill, pillar_cards, render_page, run, short, slug, wheel_svg)

SKILL_TIER = {n: s["tier"] for n, s in (load_json(SKILL / "assets" / "lifecycle.json") or {}).get("skills", {}).items()}

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
        return [check("Hooks", "settings.json", "missing",
                      f"{short(CLAUDE / 'settings.json')} missing or not valid JSON, so no hook is registered and no rule is enforced",
                      "create it with the hooks.PreToolUse entries from hooks/README.md, then run hooks/test.sh")]
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
            out += env_checks(registry, p)
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


# ---------------------------------------------------------------- environments

POLICY = {"autonomous": ("ok", "Autonomous"), "confirm-writes": ("warn", "Confirm writes"),
          "confirm-each-step": ("fail", "Confirm each step")}
PROD_NAMES = {"prod", "production", "live"}


def env_map(registry):
    envs = (registry or {}).get("environments", {}) if isinstance(registry, dict) else {}
    return envs if isinstance(envs, dict) else {e.get("name", f"env{i}"): e for i, e in enumerate(envs)}


def secret_names(project):
    """Names (never values) defined in .agents/secrets.env."""
    f = Path(project) / ".agents" / "secrets.env"
    if not f.exists():
        return set()
    return {ln.split("=", 1)[0].removeprefix("export ").strip() for ln in f.read_text().splitlines()
            if "=" in ln and not ln.lstrip().startswith("#")}


def secret_state(ref, known):
    """(label, status) for a secret reference; the value is never read or shown."""
    ref = (ref or {}).get("secret", "") if isinstance(ref, dict) else str(ref or "")
    if ref.startswith("env:"):
        name = ref[4:]
        return f"env:{name}", "ok" if name in os.environ or name in known else "missing"
    if ref.startswith("op://"):
        return "1Password", "info"
    return (ref or "no secret"), ("info" if ref else "missing")


def env_checks(registry, project):
    """Registry rules worth flagging: prod without step-by-step policy, no version command, unresolved secrets."""
    out, known = [], secret_names(project)
    for name, e in env_map(registry).items():
        policy = e.get("policy", "")
        if (name.lower() in PROD_NAMES or e.get("branch") in ("main", "master")) and policy != "confirm-each-step" and name != "dev":
            out.append(check("Project", f"{name}: policy", "fail", f"policy is '{policy or 'unset'}'; prod must be confirm-each-step",
                             "set policy to confirm-each-step in .agents/environments.json"))
        # Version status matters where code is deployed; an autonomous (local dev) environment runs the working tree.
        remote = [s_ for s_ in e.get("services", []) if s_.get("type") != "local" and policy != "autonomous"]
        if remote and not all(s_.get("version") for s_ in remote):
            miss = ", ".join(s_.get("name", "?") for s_ in remote if not s_.get("version"))
            out.append(check("Project", f"{name}: version command", "warn", f"no version command for {miss}; what runs there is unknown",
                             "add the version endpoint per the environments skill (references/version-endpoint.md)"))
        refs = [a.get("password") for a in e.get("accounts", [])] + \
               [s_.get("access", {}).get("dbUrl") for s_ in e.get("services", []) if s_.get("access", {}).get("dbUrl")]
        unresolved = [lab for lab, st in (secret_state(r, known) for r in refs if r) if st == "missing"]
        if unresolved:
            out.append(check("Project", f"{name}: secrets", "warn", "not set in the shell or .agents/secrets.env: " + ", ".join(unresolved),
                             "add them to .agents/secrets.env (gitignored); never commit values"))
    return out


def project_facts(project):
    """The project-init block's bullets as (key, value) pairs."""
    f = Path(project) / "AGENTS.md"
    text = f.read_text() if f.exists() else ""
    m = re.search(r"project-init:start -->(.*?)<!-- project-init:end", text, re.S)
    facts = []
    for ln in (m.group(1).splitlines() if m else []):
        kv = re.match(r"^- ([^:]{2,40}):\s*(.+)$", ln.strip())
        if kv:
            facts.append((kv.group(1), kv.group(2)))
    return facts


def inline_code(text):
    return re.sub(r"`([^`]+)`", r'<code>\1</code>', esc(text))


def env_panel(project, registry):
    if not project:
        return ""
    known = secret_names(project)
    _, remote, _ = run(["git", "-C", str(project), "remote", "get-url", "origin"])
    _, branch, _ = run(["git", "-C", str(project), "branch", "--show-current"])
    platform = "GitHub" if "github" in remote else "GitLab" if "gitlab" in remote else "no remote"
    head = [("Repository", short(project)), ("Remote", (remote.strip() or "none") + f" ({platform})"),
            ("Current branch", branch.strip() or "detached")]
    facts = project_facts(project)
    kv = "".join(f'<div class="kv"><span>{esc(k)}</span><b>{inline_code(v)}</b></div>' for k, v in head + facts)
    block = (kv if facts else kv + '<div class="kvempty">No project-init block yet: integration branch, tracker, commands, '
             'sources of truth and E2E setup will show here. <code>run the project-init skill</code></div>')

    envs = env_map(registry)
    if not envs:
        ghost = "".join(f'<div class="env ghost"><div class="eh"><b>{n}</b><span class="pill skip">{p_}</span></div>'
                        f'<div class="gl"></div><div class="gl s"></div><div class="gl"></div><div class="gl s"></div></div>'
                        for n, p_ in (("dev", "Autonomous"), ("staging", "Confirm writes"), ("prod", "Confirm each step")))
        envhtml = (f'<div class="envempty"><div class="envs">{ghost}</div><div class="eo"><b>No environment registry yet</b>'
                   '<p>Each environment will show its URL, branch, policy, services with deploy, verify, rollback and version commands, '
                   'test accounts (secret references only) and rules. Deploy, SSH and test-account skills ask every time until it exists.</p>'
                   '<code>run the environments skill (create section) -> .agents/environments.json</code></div></div>')
    else:
        cards_ = []
        default = registry.get("defaultEnvironment")
        for name, e in envs.items():
            st, word = POLICY.get(e.get("policy", ""), ("skip", e.get("policy", "no policy")))
            url = e.get("url", "")
            link = f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a>' if url.startswith("http") else esc(url or "no URL")
            svc = []
            for s_ in e.get("services", []):
                acc = s_.get("access", {})
                where = acc.get("ssh") or acc.get("vercelProjectId") or acc.get("supabaseProjectRef") or acc.get("composeProject") or ""
                flags = "".join(f'<span class="chip {"" if s_.get(k) else "warn"}">{k}{"" if s_.get(k) else " missing"}</span>'
                                for k in ("deploy", "verify", "rollback", "version")
                                if (s_.get("type") != "local" and e.get("policy") != "autonomous") or k in ("deploy", "verify"))
                runtime = f'<div class="sr">{esc(s_["runtime"])}</div>' if s_.get("runtime") else ""
                place = f'<span class="mono">{esc(where)}</span>' if where else ""
                svc.append(f'<li><div class="sn"><b>{esc(s_.get("name", "?"))}</b><span class="chip">{esc(s_.get("type", "?"))}</span>'
                           f'{place}</div>{runtime}<div class="chips">{flags}</div></li>')
            accs = []
            for a in e.get("accounts", []):
                lab, sst = secret_state(a.get("password"), known)
                accs.append(f'<li><span class="chip acc">{esc(a.get("role", "?"))}</span><span class="mono">{esc(a.get("login", ""))}</span>'
                            f'<span class="pill {sst}">{esc(lab)}{" set" if sst == "ok" else " missing" if sst == "missing" else ""}</span></li>')
            data = e.get("data", {})
            testing = e.get("testing", {})
            rules = e.get("rules", []) + testing.get("rules", [])
            meta = [("Branch", f'<code>{esc(e.get("branch", "?"))}</code>'),
                    ("Testing", esc(testing.get("scope", "not set"))),
                    ("Test data", ("allowed, marker " + f'<code>{esc(data.get("testDataMarker", "none"))}</code>') if data.get("testDataAllowed") else "not allowed")]
            if e.get("deployOrder"):
                meta.append(("Deploy order", " -> ".join(esc(x) for x in e["deployOrder"])))
            cards_.append(
                f'<div class="env" data-p="{st}"><div class="eh"><b>{esc(name)}</b>{"<span class=chip>default</span>" if name == default else ""}'
                f'<span class="sp"></span><span class="pill {st}">{esc(word)}</span></div>'
                f'<div class="eu">{link}</div><p class="ed">{esc(e.get("description", ""))}</p>'
                + "".join(f'<div class="kv"><span>{k}</span><b>{v}</b></div>' for k, v in meta)
                + f'<div class="lbl3">Services</div><ul class="svc">{"".join(svc) or "<li>none</li>"}</ul>'
                + f'<div class="lbl3">Test accounts</div><ul class="acc">{"".join(accs) or "<li class=none>none</li>"}</ul>'
                + (f'<div class="lbl3">Rules</div><ul class="rules">{"".join(f"<li>{esc(r)}</li>" for r in rules)}</ul>' if rules else "")
                + '</div>')
        envhtml = f'<div class="envs">{"".join(cards_)}</div>'
    return (f'<section class="card" id="envs"><div class="hd">{icon("Project")}<h2>Project & environments</h2>'
            f'<span class="desc">From the project-init block and .agents/environments.json; secret values are never read</span></div>'
            f'<div class="facts">{block}</div>{envhtml}</section>')


# ---------------------------------------------------------------- render

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


CMD = re.compile(r"^(~|/|!|\$|(brew|npm|npx|bash|echo|rm|claude|corepack|git|gh|glab)\b)")


# Core = every session depends on it; optional = only some skills, stacks or habits need it.
OPTIONAL_TITLES = {"~/OPINIONS.md -> OPINIONS.md", "Other user skills", "settings.json backups",
                   "Bypass-permissions prompt skipped", "Playwright config", "Open TODO(owner)", "Repository"}
CORE_PLUGIN_TITLES = {"Browser tool for e2e-verify"}
TOOL_KIND = {name: kind for name, kind, _, _ in TOOLS}


def tier_of(c):
    sec, title = c["section"], c["title"]
    if title in OPTIONAL_TITLES:
        return "optional"
    if sec == "Skills":
        return SKILL_TIER.get(title, "optional")
    if sec == "Tools":
        return "core" if TOOL_KIND.get(title, "required") == "required" else "optional"
    if sec == "Plugins & MCP":
        return "core" if title in CORE_PLUGIN_TITLES else "optional"
    return "core"


def readiness(checks):
    """Percent ready; every skill row together weighs 3 checks so 20 skills do not drown the rest."""
    scored = [c for c in checks if c["status"] in ("ok", "warn", "fail", "missing")]
    n_skill = sum(1 for c in scored if c["group"] == "skill") or 1
    weight = lambda c: 3 / n_skill if c["group"] == "skill" else 1
    value = {"ok": 1, "warn": 0.5}
    total = sum(weight(c) for c in scored)
    return round(100 * sum(weight(c) * value.get(c["status"], 0) for c in scored) / total) if total else 100


def tier_chip(t):
    return f'<span class="tier {t}">{"Core" if t == "core" else "Optional"}</span>'


def fix_html(fix):
    if not fix:
        return ""
    if not CMD.match(fix):
        return f'<div class="hint">{esc(fix)}</div>'
    return f'<div class="fix"><code>{esc(fix)}</code><button class="copy" type="button">Copy</button></div>'


def ring(score, label="ready", size=132):
    sw = 10 if size > 100 else 7
    r = size / 2 - sw - 2
    c = 2 * 3.14159 * r
    color = "var(--ok)" if score >= 85 else "var(--warn)" if score >= 60 else "var(--bad)"
    return (f'<div class="ring" style="width:{size}px;height:{size}px"><svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="var(--surface-3)" stroke-width="{sw}"/>'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{r}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-dasharray="{c * score / 100:.1f} {c:.1f}"/></svg>'
            f'<div class="v"><div><b>{score}%</b>{f"<span>{esc(label)}</span>" if label else ""}</div></div></div>')


TIER_TEXT = {
    "core": ("Core", "Every session depends on these. Fix all of them first."),
    "optional": ("Optional", "Only some skills, stacks or habits need these. Fix when you use them."),
}


def tier_block(tier, checks, by_sec, actions):
    """One overview panel: per section, how many of this tier's checks pass, as a bar."""
    mine = [c for c in checks if c["tier"] == tier]
    title, text = TIER_TEXT[tier]
    gaps = sum(1 for c in actions if c["tier"] == tier)
    rows = []
    for sec in ORDER:
        items = [c for c in by_sec.get(sec, []) if c["tier"] == tier and c["status"] in ("ok", "warn", "fail", "missing")]
        if not items:
            continue
        ok = sum(1 for c in items if c["status"] == "ok")
        bad = sum(1 for c in items if c["status"] in ("fail", "missing"))
        warn = len(items) - ok - bad
        st = "ok" if ok == len(items) else "fail" if bad else "warn"
        seg = lambda n, cls: f'<i class="{cls}" style="flex:{n}"></i>' if n else ""
        rows.append(f'<a class="trow" href="#{slug(sec)}"><span class="dot {st}"></span><span class="tn">{esc(sec)}</span>'
                    f'<span class="tbar">{seg(ok, "ok")}{seg(warn, "warn")}{seg(bad, "bad")}</span>'
                    f'<span class="tc">{ok}/{len(items)}</span></a>')
    status = (f'<span class="pill {"fail" if tier == "core" else "warn"}">{gaps} to fix</span>' if gaps else
              '<span class="pill ok">All set</span>' if tier == "core" else '<span class="pill info">As needed</span>')
    return (f'<div class="tierblock {tier}" data-t="{tier}"><div class="th">{ring(readiness(mine), "", 72)}<div>'
            f'<div class="tt2">{tier_chip(tier)}{status}</div><b>{title}</b><p>{text}</p></div></div>{"".join(rows)}</div>')


def pillar_status(checks):
    """Per pillar: designed coverage (ok, or warn when the repo lists known gaps), whether this machine is
    missing pieces of it (alert), and notes naming those pieces."""
    status, related, alerts = {}, {}, {}
    for pl in PILLARS:
        cov = pl["covered_by"]
        rel = [c for c in checks if c["section"] in cov.get("sections", [])
               or (c["section"] == "Skills" and c["title"] in cov.get("skills", []))
               or (c["section"] == "Plugins & MCP" and any(c["title"].startswith(x) for x in cov.get("plugins", [])))]
        bad = [c for c in rel if c["status"] in ("fail", "missing")]
        warn = [c for c in rel if c["status"] == "warn"]
        missing_plugins = [x for x in cov.get("plugins", []) if not any(c["title"].startswith(x) and c["status"] == "ok" for c in rel)]
        status[pl["id"]] = "warn" if pl.get("gaps") else "ok"
        alerts[pl["id"]] = bool(bad or missing_plugins)
        skills = [c["title"] for c in bad if c["section"] == "Skills"]
        names = ": " + ", ".join(skills) if len(skills) <= 6 else " (run install.sh)"
        notes = [f"{len(skills)} skill{'s' if len(skills) > 1 else ''} not installed{names}"] if skills else []
        notes += [f'{c["title"]}: {c["detail"]}' for c in bad + warn if c["section"] != "Skills"]
        notes += [f"plugin {x} not enabled" for x in missing_plugins]
        related[pl["id"]] = notes
    return status, related, alerts


def render(checks, cards, plugins, project, probe, registry=None):
    by_sec = {}
    for c in checks:
        by_sec.setdefault(c["section"], []).append(c)
    score = readiness([c for c in checks if c["tier"] == "core"])
    count = {s: sum(1 for c in checks if c["status"] == s) for s in RANK}
    actions = group_actions(checks)

    code, sha, _ = run(["git", "-C", str(REPO), "log", "-1", "--format=%h %s"])
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    h = []
    proj = f'<span>Project <b class="mono">{esc(short(project))}</b></span>' if project else ""
    h.append(f'<div class="hero"><div><div class="eyebrow">Agent harness</div><h1>What is set up, what is missing</h1>'
             f'<p class="sub">Global instructions, skills, hooks, tools, plugins and the current project, checked live on this machine. '
             f'Core is what every session needs; optional only matters for some skills. Fix core first; every command is copyable.</p>'
             f'<div class="meta"><span>Generated <b>{now}</b></span><span>Repo <b class="mono">{esc(short(REPO))}</b></span>'
             f'<span>Commit <b class="mono" title="{esc(sha.strip())}">{esc(sha.strip() if len(sha.strip()) <= 52 else sha.strip()[:50] + "...")}</b></span>{proj}'
             f'{"" if probe else "<span><b>Probes skipped</b></span>"}</div></div>{ring(score, "core ready")}</div>')
    pst, prel, palert = pillar_status(checks)
    wl = "".join(f'<a data-pillar="{pl["id"]}" tabindex="0" role="button"><span class="n">{pl["no"]}</span><span>{esc(pl["name"])}</span>'
                 f'<span class="chips">{"<span class=\"pill fail\">Setup</span>" if palert[pl["id"]] else ""}'
                 f'<span class="pill {pst[pl["id"]]}">{WHEEL_WORD[pst[pl["id"]]]}</span></span></a>' for pl in PILLARS)
    covered = sum(1 for v in pst.values() if v == "ok")
    need = sum(1 for v in palert.values() if v)
    h.append(f'<section class="card" id="wheel"><div class="hd">{icon("Skills")}<h2>Harness wheel</h2>'
             f'<span class="desc">Color: how fully this repo covers each component. Red badge: not set up on this machine. Hover or tap for details</span></div>'
             f'<div class="wheelwrap">{wheel_svg(pst, ("Agent Harness", f"{covered}/{len(PILLARS)} fully covered"), palert)}<div class="wlist">{wl}</div></div>'
             f'{pillar_cards(pst, prel, {c["name"]: c["installed"] for c in cards}, palert)}</section>')
    h.append(f'<div class="tiers" id="overview">{tier_block("core", checks, by_sec, actions)}{tier_block("optional", checks, by_sec, actions)}</div>')

    h.append('<div class="grid"><nav class="side"><div class="h">Overview</div><a href="#wheel">Harness wheel</a><a href="#overview">Core and optional</a><a href="#envs">Project & environments</a>'
             f'<a href="#todo">Fix first<span class="c">{len(actions)}</span></a><div class="h">Checks</div>')
    for sec in ORDER:
        if sec in by_sec:
            bad = sum(1 for c in by_sec[sec] if c["status"] in ("fail", "missing", "warn"))
            st = min((c["status"] for c in by_sec[sec]), key=RANK.get)
            h.append(f'<a href="#{slug(sec)}"><span class="dot {st}"></span>{esc(sec)}<span class="c">{bad or ""}</span></a>')
    h.append('<a href="#catalog">Skill catalog</a></nav><div>')


    h.append(env_panel(project, registry))
    h.append(f'<section class="card" id="todo"><div class="hd">{icon("Tools")}<h2>Fix first</h2><span class="desc">Core gaps first, then optional ones</span></div>')
    if actions:
        for tier in ("core", "optional"):
            mine = [c for c in actions if c["tier"] == tier]
            if not mine:
                continue
            title, text = TIER_TEXT[tier]
            h.append(f'<div class="todo" data-t="{tier}"><div class="tgh">{tier_chip(tier)}<span>{esc(text)}</span></div><ol>')
            for c in mine:
                h.append(f'<li data-t="{tier}"><div><div class="tt">{pill(c["status"])}<b>{esc(c["title"])}</b><span class="sec">{esc(c["section"])}</span></div>'
                         f'<div class="d" style="color:var(--text-2);margin-top:4px">{esc(c["detail"])}</div>{fix_html(c["fix"])}</div></li>')
            h.append('</ol></div>')
    else:
        h.append('<div class="empty">Nothing to fix. The harness is fully set up.</div>')
    h.append('</section>')

    for sec in ORDER:
        if sec not in by_sec:
            continue
        rows = sorted(by_sec[sec], key=lambda c: (c["tier"] != "core", RANK[c["status"]]))
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
            h.append(f'<div class="row" data-s="{c["status"]}" data-t="{c["tier"]}"><div>{pill(c["status"])}</div><div class="t">{esc(c["title"])} {tier_chip(c["tier"])}</div>'
                     f'<div class="d">{esc(c["detail"])}{fx}</div></div>')
        h.append('</section>')

    h.append(f'<section class="card" id="catalog"><div class="hd">{icon("Skills")}<h2>Skill catalog</h2><span class="desc">{len(cards)} skills in this repo</span></div>')
    for tier in ("core", "optional"):
        group = [s for s in cards if SKILL_TIER.get(s["name"], "optional") == tier]
        if not group:
              continue
        h.append(f'<div class="cath" data-t="{tier}">{tier_chip(tier)}<span>{len(group)} skills. {esc(TIER_TEXT[tier][1])}</span></div><div class="skills">')
        for s in group:
            chips = ['<span class="chip acc">/' + esc(s["name"]) + '</span>' if s["invocable"] else '<span class="chip agent">auto-loaded</span>']
            chips.append('<span class="chip">installed</span>' if s["installed"] else '<span class="chip bad">not installed</span>')
            chips += [f'<span class="chip">{esc(x)}/</span>' for x in s["extras"]]
            chips += [f'<span class="chip warn">{esc(i)}</span>' for i in s["issues"]]
            h.append(f'<div class="skill" data-s="{s["status"]}" data-t="{tier}"><div class="nm"><span class="mono" style="font-size:13px;font-weight:600">{esc(s["name"])}</span><span class="dot {s["status"]}"></span></div>'
                     f'<p title="{esc(s["desc"])}">{esc(s["desc"])}</p><div class="chips">{"".join(chips)}</div></div>')
        h.append('</div>')
    h.append('</section>')
    h.append('</div></div>')
    tools = ('<div class="seg" role="group" aria-label="Filter"><button data-view="all" aria-pressed="true">All</button>'
             '<button data-view="core" aria-pressed="false">Core only</button>'
             '<button data-view="action" aria-pressed="false">Needs action</button></div>')
    footer = ('Generated by <span class="mono">skills/harness-map/scripts/harness_map.py</span>. '
              'Read-only; secret values are never shown. Re-run to refresh.')
    page = render_page("Harness Map", "Harness Map", "/ " + socket.gethostname().split(".")[0], "".join(h), footer, tools)
    return page, score, count, actions


def group_actions(checks):
    """One to-do per distinct fix: rows that share status, section and fix collapse into a single item."""
    groups = {}
    for c in checks:
        if c["status"] not in ("fail", "missing", "warn"):
            continue
        key = (c["status"], c["section"], c["tier"], c["fix"] or id(c))
        groups.setdefault(key, []).append(c)
    actions = []
    for (status, sec, tier, _), items in groups.items():
        if len(items) == 1:
            actions.append(items[0])
        else:
            title = (f"{len(items)} {tier} skills not installed" if sec == "Skills" and status == "missing"
                     else f"{len(items)} items, same fix")
            g = check(sec, title, status, ", ".join(i["title"] for i in items), items[0]["fix"])
            g["tier"] = tier
            actions.append(g)
    return sorted(actions, key=lambda c: (c["tier"] != "core", RANK[c["status"]], ORDER.index(c["section"])))


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
    for c in checks:
        c["tier"] = tier_of(c)

    page, score, count, actions = render(checks, cards, plugins, project, probe, registry)
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)

    print(f"Harness map: {out}")
    opt = readiness([c for c in checks if c["tier"] == "optional"])
    print(f"Core ready {score}%  optional ready {opt}%  ok {count['ok']}  attention {count['warn']}  missing/failing {count['missing'] + count['fail']}")
    for i, c in enumerate(actions, 1):
        print(f"{i:>2}. [{c['tier']}] [{LABEL[c['status']]}] {c['section']} / {c['title']}: {c['detail']}" + (f"\n    fix: {c['fix']}" if c["fix"] else ""))
    if a.open:
        run(["open" if sys.platform == "darwin" else "xdg-open", str(out)])


if __name__ == "__main__":
    main()
