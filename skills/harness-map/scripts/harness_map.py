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

from harness_docs import LIFE, docs_body, live_hooks, unplaced_skills
import page as page_mod
from page import (release_version, skill_sources, links_into_agent_skills, _dict, _dicts, _str, load_obj, plugin_entry, strip_userinfo, ULTIMATE, ult, CLAUDE, HOME, LABEL, MAIN, PILLARS, RANK, REPO, SKILL, SKILLS_DIR, WHEEL_WORD, esc, frontmatter, icon,
                  load_json, pill, pillar_cards, render_page, run, short, slug, wheel_svg)

SKILL_TIER = {n: s["tier"] for n, s in (load_json(SKILL / "assets" / "lifecycle.json") or {}).get("skills", {}).items()}

# CLI tools the skills call. kind: required = most sessions need it; skill = only the named skills need it.
TOOLS = [
    ("git", "required", ["worktree-flow"], "brew install git"),
    ("python3", "required", ["hooks"], "brew install python"),
    ("gh", "required", ["worktree-flow", "fresh-review"], "brew install gh && gh auth login"),
    ("jq", "required", ["project-init", "environments"], "brew install jq"),
    ("node", "required", ["vision", "chrome-devtools-axi", "gnhf", "environments"], "brew install node"),
    ("npx", "required", ["vision", "chrome-devtools-axi", "gnhf", "environments"], "brew install node"),
    ("pnpm", "skill", ["project-init"], "corepack enable pnpm"),
    ("glab", "skill", ["worktree-flow (GitLab repos)"], "brew install glab && glab auth login"),
    ("docker", "skill", ["server-touch"], "brew install --cask docker"),
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

INSTALL_FIX = "/plugin marketplace add quocld/hephaestus-agent-skills, then /plugin install agent-skills@quocld"
MIGRATE_FIX = "python3 migrate-to-plugin.py (from the agent-skills plugin folder or any clone)"
LEGACY = [("~/.claude/CLAUDE.md -> AGENTS.md", CLAUDE / "CLAUDE.md", "AGENTS.md"),
          ("~/OPINIONS.md -> OPINIONS.md", HOME / "OPINIONS.md", "OPINIONS.md"),
          ("~/.claude/agent-skills-hooks -> hooks/", CLAUDE / "agent-skills-hooks", "hooks")]


def agent_skills_plugin(project=None):
    """(plugin id, install folder) when the agent-skills plugin is enabled for this project, else (None, None).
    Enablement merges user, project and project-local settings (later wins); the install record follows its scope."""
    sources = [CLAUDE / "settings.json"]
    if project:
        sources += [Path(project) / ".claude" / "settings.json", Path(project) / ".claude" / "settings.local.json"]
    enabled = {}
    for f in sources:
        enabled.update(_dict(load_obj(f).get("enabledPlugins")))
    installed = _dict(load_obj(CLAUDE / "plugins" / "installed_plugins.json").get("plugins"))
    for pid, on in enabled.items():
        if on is True and pid.split("@")[0] == "agent-skills":
            records = _dicts(installed.get(pid)) or [plugin_entry(installed, pid)]
            here = [r for r in records if r.get("scope") in ("project", "local") and _str(r.get("projectPath")) == str(project)]
            rec = (here or [r for r in records if r.get("scope", "user") == "user"] or records)[-1]
            path = Path(_str(rec.get("installPath"))) if rec.get("installPath") else None
            return pid, (path if path and path.is_dir() else None)
    return None, None


PLUGIN_ID, PLUGIN_DIR = None, None   # set in main() once the project is known


def is_ours(link, rel):
    """A symlink to <rel> in any agent-skills checkout (the old install.sh links)."""
    return links_into_agent_skills(link, rel)


def collect_global():
    sec = "Global instructions"
    if PLUGIN_ID:
        out = [check(sec, "agent-skills plugin", "ok" if PLUGIN_DIR else "fail",
                     f"{PLUGIN_ID} enabled; skills, gate hooks and the global rules (AGENTS.md at session start) come from it"
                     if PLUGIN_DIR else f"{PLUGIN_ID} is enabled but its install folder is missing",
                     "" if PLUGIN_DIR else f"claude plugin install {PLUGIN_ID}")]
        legacy = [title for title, link, src in LEGACY if is_ours(link, src)]
        if legacy:
            out.append(check(sec, "Legacy install.sh links", "warn",
                             "still linked next to the plugin, so the rules or skills load twice: " + ", ".join(legacy), MIGRATE_FIX))
        return out
    legacy_ok = all(is_ours(link, src) for _, link, src in LEGACY[:1])
    return [check(sec, "agent-skills plugin", "warn" if legacy_ok else "missing",
                  "not installed; running from the old install.sh links instead" if legacy_ok else
                  "not installed: no skills, gate hooks or global rules from this repo reach Claude Code",
                  INSTALL_FIX)]


def skill_clashes(project):
    """{name: [(where, same_text, folder)]} for repo skills whose name another skill already uses: the user's own skills
    (not links into agent-skills), the project's .claude/skills, or another enabled plugin. Two skills with one name
    both load by description, so the agent follows whichever it happens to pick."""
    places = [("~/.claude/skills", CLAUDE / "skills")]
    if project:
        places.append((f"{Path(project).name}/.claude/skills", Path(project) / ".claude" / "skills"))
    settings = load_obj(CLAUDE / "settings.json")
    installed = _dict(load_obj(CLAUDE / "plugins" / "installed_plugins.json").get("plugins"))
    for pid, on in _dict(settings.get("enabledPlugins")).items():
        if (on is True or isinstance(on, list)) and pid.split("@")[0] != "agent-skills":
            root = Path(_str(plugin_entry(installed, pid).get("installPath")))
            places.append((f"plugin {pid.split('@')[0]}", root / "skills"))
    out = {}
    for d in sorted(p for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").exists()):
        ours = (d / "SKILL.md").read_text(errors="replace")
        for where, base in places:
            other = base / d.name
            if not (other / "SKILL.md").exists() or links_into_agent_skills(other, f"skills/{d.name}"):
                continue
            try:
                same = (other / "SKILL.md").read_text(errors="replace") == ours
            except OSError:
                same = False
            out.setdefault(d.name, []).append((where, same, base))
    return out


def clash_decision(name, where, base, project, refs):
    """How a different same-name skill was settled, per place: ("ok", text) for the user's recorded choice (ours forked
    next to it as hx-<name>, which keeps theirs), ("info", text) or ("pending", text) when that choice, or the switch to
    ours (theirs deleted), is merged on origin or in an open PR/MR, else None: still a clash to decide."""
    fork = f"hx-{name}/SKILL.md"
    in_project = bool(project) and base == Path(project) / ".claude" / "skills"
    homes = [base] if in_project or base == CLAUDE / "skills" else [CLAUDE / "skills"]   # a plugin's clash: fork in ~/.claude/skills
    if any((h / fork).exists() for h in homes):
        return "ok", f"kept the existing {name} in {where}; ours is forked as hx-{name} (the user's choice)"
    if not (in_project and refs):
        return None
    found = refs.find(f".claude/skills/{fork}")
    if found and found[0] in ("origin", "pending"):
        return ("info", f"ours forked as hx-{name} on {found[1]}, pull to get it") if found[0] == "origin" else \
            ("pending", f"ours forked as hx-{name} in {found[1]}: merge it to finish")
    gone = refs.gone(f".claude/skills/{name}/SKILL.md")
    if gone:
        return ("info", f"switched to ours: the project's copy is deleted on {gone[1]}, pull to get it") if gone[0] == "origin" else \
            ("pending", f"switched to ours: {gone[1]} deletes the project's copy: merge it to finish")
    return None


def collect_skills(project=None, refs=None):
    checks, cards = [], []
    readme = (REPO / "README.md").read_text() if (REPO / "README.md").exists() else ""
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
        if name not in LIFE["skills"]:
            issues.append("not placed in harness-map assets/lifecycle.json (docs and wheel skip it)")

        dst = CLAUDE / "skills" / name
        in_plugin = bool(PLUGIN_DIR and (PLUGIN_DIR / "skills" / name / "SKILL.md").exists())
        linked = is_ours(dst, f"skills/{name}")
        if in_plugin and linked:
            lc = check("Skills", name, "warn", f"loaded twice: from {PLUGIN_ID} and from the legacy link {short(dst)}", MIGRATE_FIX)
        elif in_plugin:
            lc = check("Skills", name, "ok", f"from {PLUGIN_ID} as /agent-skills:{name}")
        elif linked:
            lc = check("Skills", name, "ok", f"legacy link {short(dst)}")
        elif PLUGIN_DIR:
            lc = check("Skills", name, "missing", f"not in the installed {PLUGIN_ID}; it is newer than the plugin",
                       "claude plugin marketplace update quocld && claude plugin update " + PLUGIN_ID)
        else:
            lc = check("Skills", name, "missing", "not installed", INSTALL_FIX)
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
            "installed": in_plugin or linked,
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
    for name, hits in skill_clashes(project).items():
        differ = [(w, base) for w, same, base in hits if not same]
        if not differ:
            checks.append(check("Skills", f"{name}: duplicate copy", "info",
                                "an identical copy is also in " + ", ".join(w for w, _, _ in hits) + "; it loads twice"))
            continue
        decided = [clash_decision(name, w, base, project, refs) for w, base in differ]
        open_ = [w for (w, _), d in zip(differ, decided) if d is None]
        if open_:
            checks.append(check("Skills", f"{name}: name clash", "warn",
                                "another skill named " + name + " is active in " + ", ".join(open_)
                                + "; both load by description, so the agent follows either one",
                                f"keep the existing {name} and fork ours next to it as hx-{name} (in a project: in the setup PR/MR), "
                                "or remove one of them"))
            continue
        status = "pending" if any(d[0] == "pending" for d in decided) else "info"
        checks.append(check("Skills", f"{name}: name clash settled", status, "; ".join(d[1] for d in decided),
                            "merge it (the user's call), then git pull" if status == "pending" else
                            "git pull" if any(d[0] == "info" for d in decided) else ""))
    return checks, cards


def collect_hooks(probe, project):
    out = []
    settings = load_json(CLAUDE / "settings.json")
    if not isinstance(settings, dict):
        return [check("Hooks", "settings.json", "missing",
                      f"{short(CLAUDE / 'settings.json')} missing or not valid JSON, so no hook is registered and no rule is enforced",
                      INSTALL_FIX)]
    local = load_obj(CLAUDE / "settings.local.json") or {}
    cmds = [_str(h.get("command")) for src in (settings, local)
            for e in _dicts(_dict(src.get("hooks")).get("PreToolUse")) for h in _dicts(e.get("hooks"))]
    plugin_hooks = (PLUGIN_DIR / "hooks" / "hooks.json").read_text() if PLUGIN_DIR and (PLUGIN_DIR / "hooks" / "hooks.json").exists() else ""
    for script in ("no-em-dash.py", "guard-protected-branches.py", "feature-status-guard.py"):
        src = REPO / "hooks" / script
        if not src.exists():
            out.append(check("Hooks", script, "info", "not in this checkout of the repo"))
            continue
        in_settings = any(script in c for c in cmds)
        if script in plugin_hooks and in_settings:
            out.append(check("Hooks", f"{script} registered", "warn", f"runs twice: from {PLUGIN_ID} and from settings.json",
                             "delete its agent-skills-hooks entry from hooks.PreToolUse in ~/.claude/settings.json, then run " + MIGRATE_FIX))
        elif script in plugin_hooks:
            out.append(check("Hooks", f"{script} registered", "ok", f"registered by {PLUGIN_ID} (hooks/hooks.json)"))
        elif in_settings:
            out.append(check("Hooks", f"{script} registered", "ok", "listed under hooks.PreToolUse in settings.json or settings.local.json"))
        else:
            out.append(check("Hooks", f"{script} registered", "missing",
                             "not registered; the rule it enforces is advisory only",
                             INSTALL_FIX))
    test = REPO / "hooks" / "test.sh"
    if not probe:
        out.append(check("Hooks", "hooks/test.sh probes", "skip", "skipped (--no-probe)"))
    elif test.exists():
        # The test builds throwaway repos; an inherited GIT_DIR or GIT_WORK_TREE would point its git calls at a real one.
        clean = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
        if project:
            clean["CLAUDE_PROJECT"] = str(project)
        code, so, se = run(["bash", str(test)], timeout=90, env=clean)
        fails = [ln for ln in (so + se).splitlines() if ln.startswith("FAIL") or "WARN" in ln]
        if code == 0:
            n = sum(1 for ln in so.splitlines() if ln.startswith("ok"))
            out.append(check("Hooks", "hooks/test.sh probes", "ok", f"{n} allow/ask/deny probes pass"))
        else:
            out.append(check("Hooks", "hooks/test.sh probes", "fail",
                             "; ".join(fails[:4]) or (se.strip().splitlines() or ["exit " + str(code)])[-1],
                             f"bash {short(test)}"))
    wired = _dict(settings.get("hooks"))
    other = {_str(e.get("matcher")) or "*" for ev in wired.values() for e in _dicts(ev)}
    events = sorted(wired.keys())
    out.append(check("Hooks", "Hook events wired", "info",
                     f"{len(events)} events ({', '.join(events)}); matchers: {', '.join(sorted(other))}"))
    return out


def collect_tools(probe, registry, project):
    out, rows = [], []
    reg_text = json.dumps(registry) if registry else ""
    remote = run(["git", "-C", str(project), "remote", "get-url", "origin"])[1] if project else ""
    # Missing CLIs that only matter when the project or registry uses them stay informational.
    needed = {"glab": "gitlab" in remote, "op": "op://" in reg_text or secrets_use_op(project),
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
    # Logins and subcommands the project or registry needs; status only, never an account token.
    compose = '"composeproject"' in reg_text.lower() or "docker compose" in reg_text.lower()
    for title, used, cmd, fix in (("glab auth", needed["glab"], ["glab", "auth", "status"], "! glab auth login"),
                                  ("vercel login", needed["vercel"], ["vercel", "whoami"], "! vercel login"),
                                  ("op sign-in", needed["op"], ["op", "whoami"], "! eval $(op signin)"),
                                  ("docker compose", compose, ["docker", "compose", "version"], "install Docker Desktop (brew install --cask docker)")):
        if used and probe and shutil.which(cmd[0]):
            code, _, _ = run(cmd, timeout=20)
            out.append(check("Tools", title, "ok" if code == 0 else "fail",
                             f"`{' '.join(cmd)}` " + ("passes" if code == 0 else f"exits {code}"), "" if code == 0 else fix))
    return out, rows


def uses_betterstack(registry):
    return any(isinstance(s_.get("logs"), dict) and s_["logs"].get("provider") == "betterstack"
               for e in env_map(registry).values() for s_ in e.get("services", []))


AXI_PROBE = ["npx", "-y", "--prefer-offline", "chrome-devtools-axi", "--help"]


def git_batch_env():
    """Environment for a git call that reaches origin: it fails instead of waiting for a password or a host-key prompt."""
    return dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_SSH_COMMAND="ssh -o BatchMode=yes")


def betterstack_connection(probe):
    """The Better Stack MCP row from `claude mcp list`: ok only on a Connected line."""
    cmd = "claude mcp list"
    if not probe:
        return check("Plugins & MCP", "Better Stack MCP", "skip", "configured; connection not probed (--no-probe)", cmd)
    if not shutil.which("claude"):
        return check("Plugins & MCP", "Better Stack MCP", "skip", "configured; the claude CLI is not on PATH to probe it", cmd)
    so = run(cmd.split(), timeout=60)[1]
    line = next((ln for ln in so.splitlines() if re.match(r"^(plugin:betterstack:)?betterstack(-ro)?:", ln)), "")
    if "Connected" in line:
        return check("Plugins & MCP", "Better Stack MCP", "ok", "connected (betterstack-logs)")
    if "Needs authentication" in line:
        return check("Plugins & MCP", "Better Stack MCP", "fail", "added but not signed in (betterstack-logs section 1)",
                     "/mcp, select betterstack and sign in")
    return check("Plugins & MCP", "Better Stack MCP", "fail",
                 "`claude mcp list` shows it failing to connect" if line else "`claude mcp list` does not list it",
                 "/mcp to reconnect, or re-add it per betterstack-logs section 1")


def collect_plugins(project=None, registry=None, probe=False, deep=False):
    """deep (the project-init doctor only) also runs `claude mcp list` and the npx browser-tool probe."""
    out, plugins = [], []
    settings = load_obj(CLAUDE / "settings.json") or {}
    enabled = _dict(settings.get("enabledPlugins"))
    installed = _dict(load_obj(CLAUDE / "plugins" / "installed_plugins.json").get("plugins"))
    mcp_names = []
    for pid, on in sorted(enabled.items()):
        inst = plugin_entry(installed, pid)
        path = Path(_str(inst.get("installPath")))
        mcp = load_obj(path / ".mcp.json")
        servers = sorted(_dict(mcp.get("mcpServers", mcp)).keys())
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
    cj = load_obj(HOME / ".claude.json") or {}
    user_mcp = sorted(_dict(cj.get("mcpServers")).keys())
    mcp_names += user_mcp
    if user_mcp:
        out.append(check("Plugins & MCP", "User MCP servers", "info", ", ".join(user_mcp)))
    if project:
        proj_mcp = sorted(set(_dict(_dict(_dict(cj.get("projects")).get(str(project))).get("mcpServers")).keys())
                          | set(_dict(load_obj(Path(project) / ".mcp.json").get("mcpServers")).keys()))
        mcp_names += proj_mcp
        if proj_mcp:
            out.append(check("Plugins & MCP", "Project MCP servers", "info", ", ".join(proj_mcp)))
    names = " ".join(mcp_names).lower() + " " + " ".join(enabled).lower()
    # Key names only: whether a Jira token is configured, never its value.
    jira_env = any(k.startswith("JIRA_") for k in list(_dict(settings.get("env")).keys()) + list(os.environ))
    if "atlassian" in names or "jira" in names:
        out.append(check("Plugins & MCP", "Jira access", "ok", "Atlassian/Jira MCP available for bug-triage and jira-bug-hunter"))
    elif jira_env:
        out.append(check("Plugins & MCP", "Jira access", "ok", "JIRA_* variables set; skills use the REST API (no MCP)"))
    else:
        out.append(check("Plugins & MCP", "Jira access", "warn", "no Atlassian MCP and no JIRA_* variables; bug-triage and jira-bug-hunter cannot read tickets",
                         "claude mcp add --transport http --scope user atlassian https://mcp.atlassian.com/v1/sse"))
    if "betterstack" in names and not deep:
        out.append(check("Plugins & MCP", "Better Stack MCP", "ok", "configured for betterstack-logs (connection not probed)"))
    elif "betterstack" in names:
        # Only `claude mcp list` tells a connected server from a failed one or one still waiting for its OAuth sign-in.
        out.append(betterstack_connection(probe))
    elif uses_betterstack(registry):
        out.append(check("Plugins & MCP", "Better Stack MCP", "missing", "the registry names Better Stack log sources but no Better Stack MCP is connected",
                         "! claude mcp add --transport http --scope user betterstack https://mcp.betterstack.com"))
    else:
        out.append(check("Plugins & MCP", "Better Stack MCP", "info", "not connected; needed only once a project ships logs to Better Stack (betterstack-logs)"))
    if any("playwright" in n.lower() for n in mcp_names):
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "ok", "Playwright MCP is available (first choice)"))
    elif shutil.which("npx") and deep and not probe:
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "skip",
                         "no Playwright MCP; the chrome-devtools-axi fallback was not probed (--no-probe)", " ".join(AXI_PROBE)))
    elif shutil.which("npx"):
        code = run(AXI_PROBE, timeout=120)[0] if deep else 0
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "warn" if code == 0 else "fail",
                         "no Playwright MCP; e2e-verify falls back to chrome-devtools-axi through npx" +
                         ("" if code == 0 else f", and `{' '.join(AXI_PROBE)}` exits {code}"),
                         "claude mcp add playwright -- npx -y @playwright/mcp@latest"))
    else:
        out.append(check("Plugins & MCP", "Browser tool for e2e-verify", "missing", "no Playwright MCP and no npx",
                         "brew install node"))
    return out, plugins


def collect_hygiene():
    out = []
    settings = load_obj(CLAUDE / "settings.json") or {}

    def literal_secrets(env):
        return [k for k, v in _dict(env).items()
                if SECRET_KEY.search(k) and isinstance(v, str) and v and not v.startswith(("op://", "$", "${"))]

    # Key names only, with where they sit; values never leave this function.
    found = [f"{k} (settings.json)" for k in literal_secrets(settings.get("env"))]
    found += [f"{k} (settings.local.json)" for k in literal_secrets((load_obj(CLAUDE / "settings.local.json") or {}).get("env"))]
    for name, srv in _dict(load_obj(HOME / ".claude.json").get("mcpServers")).items():
        found += [f"{k} (~/.claude.json MCP {name})" for k in literal_secrets(_dict(srv).get("env"))]
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
    leaky = []
    for name, m in sorted(load_obj(CLAUDE / "plugins" / "known_marketplaces.json").items()):
        if strip_userinfo(_dict(_dict(m).get("source")).get("url"))[1]:
            leaky.append(name)
    if leaky:
        out.append(check("Settings hygiene", "Credentials in plugin marketplace URLs", "fail",
                         "a token is written into the URL of: " + ", ".join(leaky) + " (values not shown)",
                         "re-add the marketplace without the token (a credential helper or SSH key), then rotate it"))
    if settings.get("skipDangerousModePermissionPrompt"):
        out.append(check("Settings hygiene", "Bypass-permissions prompt skipped", "info",
                         "bypass mode starts without a warning; guard-protected-branches denies protected pushes there"))
    return out


def integration_branch(registry):
    """(<int>, how) per worktree-flow section 0: how is "recorded" (the registry's integrationBranch), "legacy" (the
    dev environment's branch, honoured but not recorded explicitly), or None with <int> None: nothing is recorded,
    and no branch is assumed, not dev and not main. An integrationBranch that is not a non-blank string is "invalid":
    nothing is used, the same rule as feature-status's resolve_int."""
    if not isinstance(registry, dict):
        return None, None
    named = registry.get("integrationBranch")
    if named is not None:
        return (named.strip(), "recorded") if isinstance(named, str) and named.strip() else (None, "invalid")
    legacy = env_map(registry).get("dev", {}).get("branch", "").strip()
    return (legacy, "legacy") if legacy else (None, None)


def integration_guess(project):
    """The draft answer shown when asking which branch PRs go into: origin/dev if fetched, else the remote default."""
    refs = run(["git", "-C", str(project), "branch", "-r", "--format=%(refname:short)"])[1].split()
    if "origin/dev" in refs:
        return "dev"
    code, head, _ = run(["git", "-C", str(project), "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    return head.strip().split("/", 1)[-1] if code == 0 and head.strip() else None


def integration_check(p, registry, probe=False, deep=False):
    """The Integration branch row: ok only when integrationBranch is recorded and origin has it; a legacy dev
    environment branch or nothing recorded is missing (core), with the likely answer shown for the question."""
    sec = "Project"
    cand, how = integration_branch(registry)
    record = "record it as integrationBranch in .agents/environments.json: project-init asks which branch PRs go into"
    if how == "invalid":
        return check(sec, "Integration branch", "fail", "integrationBranch in .agents/environments.json is not a branch name",
                     "set integrationBranch to the branch the user chose, as a string")
    if not cand:
        guess = integration_guess(p)
        return check(sec, "Integration branch", "missing", "not recorded; worktree-flow stops and asks which branch PRs go into"
                     + (f" (likely {guess}: origin/{guess} exists)" if guess else ""), record)
    if run(["git", "-C", str(p), "remote", "get-url", "origin"])[0] != 0:
        code, where = 2, "(the repo has no origin remote)"
    elif deep and probe:   # the remote itself, as worktree-flow section 0 asks; otherwise the fetched refs
        code = run(["git", "-C", str(p), "ls-remote", "--exit-code", "--heads", "origin", f"refs/heads/{cand}"],
                   timeout=20, env=git_batch_env())[0]
        where = "on origin"
    else:
        so = run(["git", "-C", str(p), "branch", "-r", "--format=%(refname:short)"])[1]
        code, where = (0 if f"origin/{cand}" in so.split() else 2), "in fetched refs"
    if code not in (0, 2):
        return check(sec, "Integration branch", "fail", f"git ls-remote origin exits {code}: origin is unreachable or needs a login",
                     "! gh auth login (GitHub) or ! glab auth login (GitLab), then rerun")
    found = f"origin/{cand} exists" if code == 0 else f"origin/{cand} not found {where}"
    if how == "legacy":
        return check(sec, "Integration branch", "missing",
                     f"not recorded explicitly: {cand} is only the dev environment's branch (legacy); {found}", record)
    if code == 0:
        return check(sec, "Integration branch", "ok", f"{cand}, recorded as integrationBranch; {found}")
    return check(sec, "Integration branch", "missing", f"integrationBranch is {cand}, but {found}; worktree-flow will stop and ask where PRs go",
                 "push that branch, or correct integrationBranch in .agents/environments.json with the user's answer")


AGENTS_TITLE = "Project AGENTS.md"
AGENTS_WHAT = "project facts from project-init; the plugin's global rules load separately"
REGISTRY_REL = ".agents/environments.json"


def has_block(text):
    return text.count("project-init:start") == text.count("project-init:end") == 1


def git_text(p, ref, rel):
    """The file at <ref>:<rel>, or None when that ref does not have it."""
    code, so, _ = run(["git", "-C", str(p), "show", f"{ref}:{rel}"])
    return so if code == 0 else None


def open_prs(p, probe):
    """[(number, url, head branch, changed paths)] of the repo's open PRs from gh, or None when gh cannot tell
    (no probe, no gh, not logged in, not a GitHub repo): nothing is then called pending."""
    if not (probe and shutil.which("gh")):
        return None
    code, so, _ = run(["gh", "pr", "list", "--state", "open", "--limit", "50", "--json", "number,url,headRefName,files"],
                      cwd=str(p), timeout=30)
    try:
        data = json.loads(so) if code == 0 else None
    except ValueError:
        data = None
    if not isinstance(data, list):
        return None
    return [(pr.get("number"), _str(pr.get("url")), _str(pr.get("headRefName")),
             {_str(x.get("path")) for x in _dicts(pr.get("files"))}) for pr in _dicts(data)]


class Refs:
    """What origin already holds for one project, asked lazily and once per run. merged(): the refs a merge lands on
    (origin/<int>, the remote default, origin/main, origin/master), where a file only means this checkout is behind.
    prs(): the open PRs/MRs from gh, the only source that makes a row pending. Without gh, another fetched branch that
    has the file is only a hint on a row that stays a gap, since nothing says that branch has an open PR/MR."""

    def __init__(self, p, probe, registry=None):
        self.p, self.probe = Path(p), probe
        self.adopt(registry)
        self._prs, self._asked = None, False

    def adopt(self, registry):
        """The integration branch from a registry; a guess only while none is recorded."""
        self.int_ = integration_branch(registry)[0]
        self.guessed = not self.int_
        if self.guessed:
            self.int_ = integration_guess(self.p)
        self._merged = None

    def remote_refs(self):
        return [r for r in run(["git", "-C", str(self.p), "for-each-ref", "--sort=-committerdate", "--format=%(refname:short)",
                                "refs/remotes/origin"])[1].split() if r not in ("origin", "origin/HEAD")]

    def merged(self):
        if self._merged is None:
            names = [self.int_] if self.int_ else []
            code, head, _ = run(["git", "-C", str(self.p), "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
            if code == 0 and head.strip():
                names.append(head.strip().split("/", 1)[-1])
            elif self.probe:   # no origin/HEAD in this clone: ask origin for its default branch
                code, so, _ = run(["git", "-C", str(self.p), "ls-remote", "--symref", "origin", "HEAD"], timeout=20, env=git_batch_env())
                m = re.search(r"^ref: refs/heads/(\S+)\s+HEAD", so, re.M) if code == 0 else None
                if m:
                    names.append(m.group(1))
            have = set(self.remote_refs())
            self._merged = [f"origin/{b}" for b in dict.fromkeys(names + ["main", "master"]) if f"origin/{b}" in have]
        return self._merged

    def prs(self):
        if not self._asked:
            self._prs, self._asked = open_prs(self.p, self.probe), True
        return self._prs

    def pr_label(self, num, url):
        return f"PR #{num}" + (f" ({url})" if url else "")

    def find(self, rel, want=lambda text: True):
        """Where a file missing from the working tree exists: ("origin", <merged ref>, text), ("pending", "PR #n", text
        or None), ("branch", <other ref>, text) without gh, or None. want() tells a usable copy from a stub."""
        for ref in self.merged():
            text = git_text(self.p, ref, rel)
            if text is not None and want(text):
                return "origin", ref, text
        prs = self.prs()
        if prs is not None:
            for num, url, head, files in prs:
                if rel in files:
                    text = git_text(self.p, f"origin/{head}", rel) if head else None
                    if text is None or want(text):
                        return "pending", self.pr_label(num, url), text
            return None
        skip = set(self.merged())
        for ref in self.remote_refs()[:200]:
            if ref in skip:
                continue
            text = git_text(self.p, ref, rel)
            if text is not None and want(text):
                return "branch", ref, text
        return None

    def gone(self, rel):
        """Where a tracked file still in the working tree was deleted: ("origin", <merged ref>) when a merged ref's history
        has it and its tip does not, ("pending", "PR #n") when an open PR/MR deletes it, else None."""
        for ref in self.merged():
            touched = run(["git", "-C", str(self.p), "log", "-1", "--format=%H", ref, "--", rel])[1].strip()
            if touched and git_text(self.p, ref, rel) is None:
                return "origin", ref
        for num, url, head, files in self.prs() or []:
            if rel in files and head and git_text(self.p, f"origin/{head}", rel) is None:
                return "pending", self.pr_label(num, url)
        return None


def elsewhere_row(sec, title, found, status, detail, fix):
    """The row for a file the working tree lacks, given where Refs.find saw it; status, detail, fix: the row without it."""
    kind, where = found[0], found[1]
    if kind == "origin":
        return check(sec, title, "info", f"on {where}, pull to get it: this checkout is behind", "git pull")
    if kind == "pending":
        return check(sec, title, "pending", f"in {where}: merge it to finish", "merge it (the user's call), then git pull")
    return check(sec, title, status, f"{detail}; branch {where} has it: if that branch has an open PR/MR, merge it",
                 f"merge {where.split('/', 1)[-1]} if it is the setup PR/MR, else {fix}")


def registry_rows(sec, registry, where=""):
    """The Environment registry row for a registry read from the working tree (where="") or from origin (where=<ref>)."""
    on = f"on {where}, pull to get it: " if where else ""
    fix_at = f"fix it on {where}, " if where else ""
    if registry is None:
        return check(sec, "Environment registry", "fail", f"{on}.agents/environments.json is not valid JSON",
                     f"{fix_at}fix the JSON, then validate per the environments skill")
    names = list(env_map(registry))
    if names:
        return check(sec, "Environment registry", "info" if where else "ok", f"{on}environments: " + ", ".join(names),
                     "git pull" if where else "")
    if isinstance(registry, dict) and registry.get("environments") == {}:   # valid: only project facts such as integrationBranch so far
        return check(sec, "Environment registry", "missing", f"{on}no environment recorded yet; deploy/SSH skills will ask every time",
                     "run the environments skill (create section), which asks which environments exist")
    return check(sec, "Environment registry", "fail", f"{on}no environment object found under `environments`; the registry shape is invalid",
                 f"{fix_at}fix it per the environments skill's schema (templates/environments.schema.json)")


def collect_project(project, probe=False, deep=False, refs=None):
    """deep (the project-init doctor only) asks origin itself for the integration branch instead of the fetched refs.
    A project file missing from the working tree but already merged on origin is info (pull to get it), and one in an
    open PR/MR that gh confirms is pending (merge it), not missing: project-init's own PR is the usual reason."""
    sec = "Project"
    out, registry = [], None
    if not project:
        return [check(sec, "Project", "skip", "no git project given (--project)")], None
    p = Path(project)
    out.append(check(sec, "Repository", "info", short(p)))
    reg = p / ".agents" / "environments.json"
    local_reg = load_json(reg) if reg.exists() else None
    refs = refs or Refs(p, probe, local_reg)

    # The registry first: a merged copy on origin also names the real integration branch for the other rows.
    gi = (p / ".gitignore").read_text() if (p / ".gitignore").exists() else ""
    pending_reg, reg_row = None, None
    if reg.exists():
        registry = local_reg
        reg_row = registry_rows(sec, registry)
    else:
        found = refs.find(REGISTRY_REL)
        if found and found[0] == "origin":
            try:
                registry = json.loads(found[2])
            except ValueError:
                registry = None
            reg_row = registry_rows(sec, registry, found[1])
            if registry is not None:
                if refs.guessed:
                    refs.adopt(registry)
                gi += "\n" + (git_text(p, found[1], ".gitignore") or "")
        else:
            missing = ("missing", "no .agents/environments.json; deploy/SSH skills will ask every time", "run the environments skill (create section)")
            if found:
                pending_reg = found if found[0] == "pending" else None
                reg_row = elsewhere_row(sec, "Environment registry", found, *missing)
            else:
                reg_row = check(sec, "Environment registry", *missing)

    agents = p / "AGENTS.md"
    text = agents.read_text() if agents.exists() else ""
    starts, ends = text.count("project-init:start"), text.count("project-init:end")
    if starts == ends == 1:
        out.append(check(sec, "project-init block", "ok", "one start and one end marker"))
    elif starts or ends:
        out.append(check(sec, "project-init block", "fail", f"{starts} start / {ends} end markers", "fix the markers by hand, then re-run project-init"))
    else:
        title = "project-init block" if agents.exists() else AGENTS_TITLE
        missing = ("missing", "AGENTS.md has no project-init block" if agents.exists() else f"none in this repo yet ({AGENTS_WHAT})",
                   "run the project-init skill")
        found = refs.find("AGENTS.md", has_block)
        out.append(elsewhere_row(sec, title, found, *missing) if found else check(sec, title, *missing))
    claude_md = p / "CLAUDE.md"
    if claude_md.exists() and "@AGENTS.md" in claude_md.read_text():
        out.append(check(sec, "CLAUDE.md imports AGENTS.md", "ok", "CLAUDE.md contains @AGENTS.md"))
    elif agents.exists():
        out.append(check(sec, "CLAUDE.md imports AGENTS.md", "warn", "Claude Code will not read AGENTS.md", "echo '@AGENTS.md' > CLAUDE.md"))

    out.append(reg_row)
    if registry is not None:
        out += env_checks(registry, p)
    if (reg.exists() or registry is not None) and "secrets.env" not in gi:
        out.append(check(sec, "Secrets gitignored", "fail", ".agents/secrets.env is not in .gitignore", "echo '.agents/secrets.env' >> .gitignore"))

    todos = []
    for f in (agents, reg):
        if f.exists() and "TODO(" in f.read_text():
            todos.append(f.name)
    if todos:
        out.append(check(sec, "Open TODO(owner)", "warn", ", ".join(todos), "answer them and re-run project-init"))

    ib = integration_check(p, registry, probe, deep)
    if pending_reg and ib["status"] == "missing" and not integration_branch(registry)[1]:
        text = pending_reg[2]
        try:
            named = integration_branch(json.loads(text))[0] if text else None
        except ValueError:
            named = None
        ib = check(sec, "Integration branch", "pending", (f"{named}, recorded" if named else "recorded")
                   + f" in {pending_reg[1]}: merge it to finish", "merge it (the user's call), then git pull")
        ib["branch"] = named   # the banner shows it
    out.append(ib)

    _, url, _ = run(["git", "-C", str(p), "remote", "get-url", "origin"])
    if strip_userinfo(url.strip())[1]:
        out.append(check(sec, "Remote URL credentials", "fail", "the origin URL holds a user:token part (not shown)",
                         "git remote set-url origin <the same URL without user:token@>, use gh auth or a credential helper, and rotate the token"))
    pc = sorted((p / ".agents" / "checks").glob("*.md"))
    out.append(check(sec, "Project checks (verify-loop)", "ok" if pc else "info",
                     f"{len(pc)} in .agents/checks/: " + ", ".join(x.stem for x in pc[:8]) if pc else
                     "none yet; add one when a bug class repeats (verify-loop: checks.py new <id>)"))

    pw = list(p.glob("playwright.config.*")) + list(p.glob("*/playwright.config.*")) + list(p.glob("apps/*/playwright.config.*"))
    out.append(check(sec, "Playwright config", "ok" if pw else "info",
                     ", ".join(short(x) for x in pw[:3]) if pw else "none found; e2e-verify drives the browser ad hoc"))
    return out, registry


# ---------------------------------------------------------------- environments

POLICY = {"autonomous": ("ok", "Autonomous"), "confirm-writes": ("warn", "Confirm writes"),
          "confirm-each-step": ("fail", "Confirm each step")}
PROD_NAMES = {"prod", "production", "live"}


def _strs(x):
    return [str(i) for i in x if isinstance(i, (str, int, float))] if isinstance(x, list) else []


def normalize_env(e):
    """One environment with every field the page reads in a safe shape, so a hand-edited registry cannot crash it."""
    out = dict(e)
    out.update({k: _str(e.get(k)) for k in ("url", "branch", "policy", "description")})
    out.update({k: _dict(e.get(k)) for k in ("data", "testing")})
    out["testing"] = dict(out["testing"], rules=_strs(out["testing"].get("rules")))
    out.update({k: _strs(e.get(k)) for k in ("rules", "deployOrder")})
    out["accounts"] = [dict(a, role=_str(a.get("role"), "?"), login=_str(a.get("login"))) for a in _dicts(e.get("accounts"))]
    out["services"] = [dict(s_, name=_str(s_.get("name"), "?"), type=_str(s_.get("type"), "?"), access=_dict(s_.get("access")))
                       for s_ in _dicts(e.get("services"))]
    # A URL with user:password@ (basic auth on staging) is shown without it; the literal secrets check counts it.
    out["url"], out["_url_credential"] = strip_userinfo(out["url"])
    return out


def env_map(registry):
    """Environment name -> normalised environment; entries that are not objects are dropped."""
    envs = registry.get("environments") if isinstance(registry, dict) else None
    if isinstance(envs, dict):
        return {str(k): normalize_env(v) for k, v in envs.items() if isinstance(v, dict)}
    if isinstance(envs, list):
        return {str(v.get("name") or f"env{i}"): normalize_env(v) for i, v in enumerate(envs) if isinstance(v, dict)}
    return {}


def secrets_file(project):
    """The project's .agents/secrets.env, else its main checkout's: a worktree links it from there (worktree-flow)."""
    if not project:
        return None
    own = Path(project) / ".agents" / "secrets.env"
    if own.exists():
        return own
    code, so, _ = run(["git", "-C", str(project), "rev-parse", "--path-format=absolute", "--git-common-dir"])
    main_ = Path(so.strip()).parent / ".agents" / "secrets.env" if code == 0 and so.strip() else None
    return main_ if main_ and main_.exists() else own


def shell_value_set(raw):
    """Whether the text after NAME= gives a non-empty value when the shell sources it (set -a; . file), without
    running the file: a value is one word, quoted or not; whitespace right after = leaves it empty (what follows is a
    comment or another word), and # inside an unquoted word is part of the value (NAME=#abc is "#abc")."""
    if not raw or raw[0] in " \t":
        return False
    if raw[0] in "\"'":
        end = raw.find(raw[0], 1)
        return (end if end != -1 else len(raw)) > 1
    return True


def secret_names(project):
    """Name -> whether .agents/secrets.env gives it a value; the value itself is never kept.
    An empty value (NAME=, NAME="", NAME="" # fill me, NAME= # fill me) is a line the user has not filled yet."""
    f = secrets_file(project)
    out = {}
    if not (f and f.exists()):
        return out
    for ln in f.read_text(errors="ignore").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$", ln)
        if m:
            out[m.group(1)] = shell_value_set(m.group(2))   # the last line wins, as in the shell
    return out


def secrets_use_op(project):
    """Whether .agents/secrets.env holds an op:// reference; only that text is looked for, no value is kept."""
    f = secrets_file(project)
    return bool(f and f.exists() and "op://" in f.read_text(errors="ignore"))


def secret_state(ref, known):
    """(label, status) for a secret reference; the value is never read or shown. known is secret_names()."""
    ref = _str(ref.get("secret")) if isinstance(ref, dict) else _str(ref)
    if ref.startswith("env:"):
        name = ref[4:]
        return f"env:{name}", "ok" if os.environ.get(name) or known.get(name) else "missing"
    if ref.startswith("op://"):
        return "1Password", "info"
    # Anything else is a value written into the registry itself: say so, never show it.
    return ("literal value (not shown)", "fail") if ref else ("no secret", "missing")


def secret_note(label, status, known):
    """Why a secret reference is (not) usable, in words, without its value."""
    if status == "ok":
        return "set"
    if status == "info":
        return "op:// reference, resolved by op when used"
    if status == "fail":
        return "a value written into the registry"
    name = label[4:] if label.startswith("env:") else ""
    if name in known:
        return "empty in .agents/secrets.env: fill it there"
    return "not in .agents/secrets.env or the shell" if name else "no reference"


DEV_NAMES = {"dev", "local", "development"}
STAGING_NAMES = {"staging", "stage"}
# The environments every project is asked about (environments section 10): slot, names that fill it, default policy.
STANDARD_ENVS = [("dev", DEV_NAMES, "autonomous"), ("staging", STAGING_NAMES, "confirm-writes"), ("prod", PROD_NAMES, "confirm-each-step")]
ENV_FIX = "run the environments skill (create section): it asks for what is missing and records it in .agents/environments.json"


def is_prod(name, e):
    """Named prod, or deployed from main/master under a name that is not a dev or staging one (a local env on main is
    not prod). standard_slots fills the prod slot with the same rule, so a card is never both prod and missing."""
    n = name.lower()
    return n in PROD_NAMES or (e.get("branch") in ("main", "master") and n not in DEV_NAMES | STAGING_NAMES)


def needed_commands(e, s_):
    """The commands a service needs: deploy and verify always; rollback and version where code is deployed remotely."""
    remote = s_.get("type") != "local" and e.get("policy") != "autonomous"
    return ("deploy", "verify", "rollback", "version") if remote else ("deploy", "verify")


def secret_refs(e):
    """(where, reference) for every secret an environment names: account passwords and MFA, secret-like access keys."""
    refs = [(f'{a.get("role", "?")} {k}', a.get(k)) for a in e.get("accounts", []) for k in ("password", "mfa") if a.get(k)]
    refs += [(f'{s_.get("name", "?")} {k}', v if isinstance(v, dict) else {"secret": "literal"})
             for s_ in e.get("services", []) for k, v in s_.get("access", {}).items()
             if (isinstance(v, dict) and "secret" in v)
             or (isinstance(v, str) and (k == "dbUrl" or SECRET_KEY.search(k) or strip_userinfo(v)[1]))]
    return refs


def item(key, label, status, value="", parts=None):
    return {"key": key, "label": label, "status": status, "value": value, "parts": parts or []}


def env_items(name, e, known):
    """The checklist of one recorded environment: what it should have and whether it does (secret names only)."""
    prod = is_prod(name, e)
    policy = e.get("policy", "")
    url = e.get("url", "")
    out = [item("url", "URL", "fail" if e.get("_url_credential") else "ok" if url else "missing",
                (url + " (holds a user:password, not shown)") if e.get("_url_credential") else url or "not recorded"),
           item("branch", "Branch", "ok" if e.get("branch") else "missing", e.get("branch") or "not recorded")]
    if prod and policy != "confirm-each-step":
        out.append(item("policy", "Policy", "fail", f"{policy or 'unset'}; prod must be confirm-each-step"))
    else:
        out.append(item("policy", "Policy", "ok" if policy in POLICY else "missing", policy or "not recorded"))
    services = e.get("services", [])
    for s_ in services:
        need = needed_commands(e, s_)
        parts = [(k, bool(s_.get(k))) for k in need]
        out.append(item("service", s_.get("name", "?"), "ok" if all(v for _, v in parts) else "missing", s_.get("type", "?"), parts))
    if not services:
        out.append(item("service", "Services", "missing", "none recorded: deploy, verify, rollback and version commands"))
    accs = e.get("accounts", [])
    scope = e.get("testing", {}).get("scope", "")
    # Smoke-only or no testing needs a login only when the app has one; the registry cannot tell, so it is not required.
    out.append(item("accounts", "Test accounts", "ok" if accs else "info" if scope in ("none", "smoke-only") else "missing",
                    ", ".join(f'{a.get("role", "?")} {a.get("login", "")}'.strip() for a in accs)
                    or (f"none recorded; {scope} testing needs one only if the app has a login" if scope in ("none", "smoke-only")
                        else "none recorded")))
    for where, ref in secret_refs(e):
        lab, st = secret_state(ref, known)
        out.append(item("secret", lab, st, f"{where}: {secret_note(lab, st, known)}"))
    return out


def absent_slots(registry):
    """Standard environments the user said this project does not have (absentEnvironments), so nothing asks for them."""
    absent = registry.get("absentEnvironments") if isinstance(registry, dict) else None
    return {x for x in _strs(absent) if x in {slot for slot, _, _ in STANDARD_ENVS}}


def standard_slots(envs):
    """slot -> the recorded environment name that fills it, or None; prod also takes the first environment is_prod picks."""
    out = {slot: next((n for n in envs if n.lower() in names), None) for slot, names, _ in STANDARD_ENVS}
    if not out["prod"]:
        out["prod"] = next((n for n, e in envs.items() if n not in out.values() and is_prod(n, e)), None)
    return out


def env_checks(registry, project):
    """Registry gaps as check rows: prod policy and literal secrets are core; every other environment gap is optional."""
    out, known = [], secret_names(project)
    envs = env_map(registry)
    for name, e in envs.items():
        items = env_items(name, e, known)
        miss = lambda key: [i for i in items if i["key"] == key and i["status"] == "missing"]
        opt = lambda title, status, detail, fix=ENV_FIX: out.append(check("Project", f"{name}: {title}", status, detail, fix, group="env"))
        policy = next(i for i in items if i["key"] == "policy")
        if policy["status"] == "fail":
            out.append(check("Project", f"{name}: policy", "fail", f"policy is '{e.get('policy') or 'unset'}'; prod must be confirm-each-step",
                             "set policy to confirm-each-step in .agents/environments.json"))
        elif policy["status"] == "missing":
            opt("policy", "missing", "no policy recorded; autonomous, confirm-writes or confirm-each-step")
        for key, title in (("url", "URL"), ("branch", "branch"), ("accounts", "test accounts")):
            if miss(key):
                opt(title, "missing", f"no {title} recorded for {name}")
        cmds = [f'{i["label"]} has no {", ".join(k for k, ok in i["parts"] if not ok and k != "version")}' for i in miss("service")
                if any(not ok and k != "version" for k, ok in i["parts"])]
        if cmds or (miss("service") and not e.get("services")):
            opt("commands", "missing", "; ".join(cmds) or "no service recorded")
        # Version status matters where code is deployed; an autonomous (local dev) environment runs the working tree.
        nover = [i["label"] for i in items if i["key"] == "service" and ("version", False) in i["parts"]]
        if nover:
            opt("version command", "warn", f"no version command for {', '.join(nover)}; what runs there is unknown",
                "add the version endpoint per the environments skill (references/version-endpoint.md)")
        old = [s_.get("name", "?") for s_ in e.get("services", []) if isinstance(s_.get("logs"), str)]
        if old:
            opt("logs field", "warn", f"{', '.join(old)} still use the old string `logs`; it is now `logsCommand`, and `logs` names a Better Stack source",
                "rename logs to logsCommand in .agents/environments.json (environments skill)")
        literal = sum(1 for i in items if i["key"] == "secret" and i["status"] == "fail") + (1 if e.get("_url_credential") else 0)
        if literal:
            out.append(check("Project", f"{name}: literal secrets", "fail",
                             f"{literal} secret value(s) written into .agents/environments.json (values not shown)",
                             "replace each with an env:NAME or op:// reference, rotate the value, and keep it in .agents/secrets.env"))
        unresolved = [i for i in items if i["key"] == "secret" and i["status"] == "missing"]
        if unresolved:
            filed = lambda i: i["label"].startswith("env:") and i["label"][4:] in known
            empty = [i["label"] for i in unresolved if filed(i)]
            absent = [i["label"] for i in unresolved if not filed(i)]
            opt("secrets", "missing", "; ".join(x for x in (("empty in .agents/secrets.env: " + ", ".join(empty)) if empty else "",
                                                             ("not in .agents/secrets.env or the shell: " + ", ".join(absent)) if absent else "") if x),
                "fill them in .agents/secrets.env (gitignored, in the main checkout) yourself, values or op:// references; never paste them in chat")
    if envs:
        settled = absent_slots(registry)
        absent = [slot for slot, have in standard_slots(envs).items() if not have and slot not in settled]
        if absent:
            out.append(check("Project", "Standard environments", "missing",
                             "not in the registry: " + ", ".join(absent) + " (the page shows what each needs)",
                             ENV_FIX + "; one the project does not have goes in absentEnvironments", group="env"))
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


def feature_status_fact(project):
    """Whether the repo tracks features with feature-status, read from the working tree (never a remote call)."""
    status = Path(project) / "docs" / "status"
    agents = Path(project) / "AGENTS.md"
    named = agents.exists() and "feature-status" in agents.read_text(errors="ignore")
    files = sorted(f for f in status.glob("*.md") if f.name.lower() != "readme.md") if status.is_dir() else []
    if status.is_dir() or named:
        return f"opted in: {len(files)} feature file(s) in `docs/status/`"
    return "not used (feature-status; project-init offers the opt-in)"


def inline_code(text):
    return re.sub(r"`([^`]+)`", r'<code>\1</code>', esc(text))


MARK = {
    "ok": '<path d="M5 8.2l2 2L11 6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>',
    "missing": '<path d="M5.8 5.8l4.4 4.4M10.2 5.8l-4.4 4.4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/>',
    "fail": '<path d="M8 4.6v4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="11.2" r="1" fill="currentColor"/>',
    "info": '<circle cx="8" cy="8" r="1.6" fill="currentColor"/>',
}
MARK["warn"] = MARK["fail"]
MARK["pending"] = '<path d="M8 4.8V8l2.2 1.4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
MARK_WORD = {"ok": "done", "missing": "missing", "fail": "wrong", "warn": "attention", "info": "not checked", "pending": "waiting on merge"}


def mark(status, size=16):
    st = status if status in MARK else "info"
    return (f'<svg class="mk {st}" width="{size}" height="{size}" viewBox="0 0 16 16" role="img" aria-label="{MARK_WORD[st]}">'
            f'<title>{MARK_WORD[st]}</title>{MARK[st]}</svg>')


def checklist(items):
    """One row per expected item: a done or missing mark, the item, and what is recorded (secret names only)."""
    rows = []
    for i in items:
        if i["parts"]:
            val = "".join(f'<span class="part {"ok" if ok else "missing"}">{mark("ok" if ok else "missing", 12)}{esc(k)}</span>'
                          for k, ok in i["parts"])
            label = f'{esc(i["label"])}<span class="chip">{esc(i["value"])}</span>'
        else:
            val = esc(i["value"])
            label = esc(i["label"])
        cn = " mono" if i["key"] == "secret" else ""
        cv = " mono" if i["key"] in ("branch", "url") and i["status"] != "missing" else ""
        rows.append(f'<li class="ci" data-s="{i["status"]}">{mark(i["status"])}<span class="cn{cn}">{label}</span>'
                    f'<span class="cv{cv}">{val}</span></li>')
    return f'<ul class="cl">{"".join(rows)}</ul>'


def progress(items):
    scored = [i for i in items if i["status"] != "info"]
    ok = sum(1 for i in scored if i["status"] == "ok")
    bad = len(scored) - ok
    wrong = sum(1 for i in scored if i["status"] in ("fail", "warn"))
    st = "ok" if not bad else "fail" if wrong else "missing"
    seg = lambda n, cls: f'<i class="{cls}" style="flex:{n}"></i>' if n else ""
    word = ", ".join(x for x in (f"{bad - wrong} missing" if bad - wrong else "", f"{wrong} wrong" if wrong else "") if x)
    return (f'<div class="eprog" data-s="{st}"><span class="tbar">{seg(ok, "ok")}{seg(bad, "bad")}</span>'
            f'<span class="tc">{ok}/{len(scored)}</span><span class="ew">{word or "ready"}</span></div>')


GHOST_NEEDS = {
    "dev": ["URL, e.g. http://localhost:3000", "Branch it runs from", "Policy autonomous", "Each service with deploy and verify commands",
            "Test accounts, passwords as env: or op:// references"],
    "staging": ["URL", "Branch it deploys from", "Policy confirm-writes", "Each service with deploy, verify, rollback and version commands",
                "Test accounts, passwords as env: or op:// references"],
    "prod": ["URL", "Branch it deploys from", "Policy confirm-each-step", "Each service with deploy, verify, rollback and version commands",
             "A read-only smoke account if the app has a login, password as an op:// reference"],
}


def ghost_card(slot, policy):
    st, word = POLICY[policy]
    rows = "".join(f'<li class="ci" data-s="missing">{mark("missing")}<span class="cn">{esc(x)}</span></li>' for x in GHOST_NEEDS[slot])
    return (f'<div class="env ghost" data-slot="{slot}"><div class="eh"><b>{slot}</b><span class="sp"></span>'
            f'<span class="pill skip">Not in registry</span></div>'
            f'<p class="ed">Not recorded yet. If this project has a {slot} environment, it needs:</p>'
            f'<ul class="cl">{rows}</ul><div class="lbl3">Default policy</div><div><span class="pill {st}">{esc(word)}</span></div>'
            f'<div class="gfix"><span>Run the environments skill (create section). No {slot} in this project? '
            f'Record it in <code>absentEnvironments</code> and this card goes quiet.</span></div></div>')


def absent_card(slot):
    return (f'<div class="env ghost quiet" data-slot="{slot}"><div class="eh"><b>{slot}</b><span class="sp"></span>'
            f'<span class="pill skip">Not used</span></div>'
            f'<p class="ed">This project has no {slot} environment (<code>absentEnvironments</code> in .agents/environments.json).</p></div>')


IB_TEXT = {"ok": "Recorded", "warn": "Check", "missing": "Not recorded", "fail": "Unreachable"}


def integration_banner(project, registry, row=None):
    """The branch every PR goes into, as recorded (worktree-flow section 0), legacy, or not recorded yet.
    row: the page's own Integration branch row, so a branch recorded only in an open PR/MR shows as pending here too."""
    c = row if row and row["status"] == "pending" else integration_check(project, registry)
    cand, how = integration_branch(registry)
    if c["status"] == "pending":
        word, st, cand = "Pending merge", "pending", c.get("branch")
    elif cand and how == "recorded" and c["status"] != "ok":
        word, st = "Recorded, not on origin", "warn"
    elif how == "legacy":
        word, st = "Legacy: not recorded", "missing"
    elif how == "invalid":
        word, st = "Invalid", "fail"
    else:
        word, st = IB_TEXT.get(c["status"], c["status"]), c["status"]
    guess = None if cand or how == "invalid" or st == "pending" else integration_guess(project)
    # Nothing recorded: the box shows the drafted answer to the question, not the pill's words again.
    shown = (f'<code class="ibb">{esc(cand)}</code>' if cand else
             f'<span class="ibb none" title="likely answer, not recorded">{esc(guess)}?</span>' if guess else
             '<span class="ibb none" title="asked on the next run">?</span>')
    return (f'<div class="ib" data-s="{st}">{mark(st, 22)}<div class="ibm"><div class="ibl">Integration branch '
            f'<span class="pill {st if st in ("ok", "warn", "pending") else "fail"}">{esc(word)}</span></div>'
            f'<div class="ibv">{shown}<span class="ibd">{esc(c["detail"] if cand else c["detail"].replace("not recorded; ", "", 1))}</span></div>{fix_html(c["fix"]) if st != "ok" else ""}</div></div>')


def env_panel(project, registry, ib_row=None):
    if not project:
        return ""
    known = secret_names(project)
    _, remote, _ = run(["git", "-C", str(project), "remote", "get-url", "origin"])
    remote, _ = strip_userinfo(remote.strip())
    _, branch, _ = run(["git", "-C", str(project), "branch", "--show-current"])
    platform = "GitHub" if "github" in remote else "GitLab" if "gitlab" in remote else "no remote"
    checks_ = sorted((Path(project) / ".agents" / "checks").glob("*.md"))
    head = [("Repository", short(project)), ("Remote", (remote.strip() or "none") + f" ({platform})"),
            ("Current branch", branch.strip() or "detached"),
            ("Project checks", f"{len(checks_)} in `.agents/checks/`" if checks_ else "none in `.agents/checks/` (verify-loop)"),
            ("Feature status", feature_status_fact(project))]
    facts = project_facts(project)
    kv = "".join(f'<div class="kv"><span>{esc(k)}</span><b>{inline_code(v)}</b></div>' for k, v in head + facts)
    block = (kv if facts else kv + '<div class="kvempty">No project-init block yet: tracker, commands, '
             'sources of truth and E2E setup will show here. <code>run the project-init skill</code></div>')

    envs = env_map(registry)
    slots = standard_slots(envs)
    cards_, ready, total = [], 0, 0
    default = registry.get("defaultEnvironment") if isinstance(registry, dict) else None
    # Standard environments first, in dev, staging, prod order, then every other recorded one.
    order = [slots[s] for s, _, _ in STANDARD_ENVS if slots[s]] + [n for n in envs if n not in slots.values()]
    settled = absent_slots(registry)
    for idx, (slot, _names, policy) in enumerate(STANDARD_ENVS):
        if not slots[slot]:
            cards_.append((idx, absent_card(slot) if slot in settled else ghost_card(slot, policy)))
    for pos, name in enumerate(order):
        e = envs[name]
        items = env_items(name, e, known)
        total += 1
        ready += all(i["status"] in ("ok", "info") for i in items)
        st, word = POLICY.get(e.get("policy", ""), ("skip", e.get("policy") or "no policy"))
        url = e.get("url", "")
        link = (f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(url)}</a>' if url.startswith("http")
                else f'<span class="none">{esc(url or "no URL")}</span>')
        data = e.get("data", {})
        testing = e.get("testing", {})
        rules = e.get("rules", []) + testing.get("rules", [])
        meta = [("Testing", esc(testing.get("scope", "not set"))),
                ("Test data", ("allowed, marker " + f'<code>{esc(data.get("testDataMarker", "none"))}</code>') if data.get("testDataAllowed") else "not allowed")]
        if e.get("deployOrder"):
            meta.append(("Deploy order", " -> ".join(esc(x) for x in e["deployOrder"])))
        logs = [f'{esc(s_.get("name", "?"))}: {esc(s_["logs"].get("source", "?"))} ({esc(s_["logs"].get("shipping", "?"))})'
                for s_ in e.get("services", []) if isinstance(s_.get("logs"), dict)]
        if logs:
            meta.append(("Logs", ", ".join(logs)))
        slot = next((s for s, n in slots.items() if n == name), None)
        rank = [s for s, _, _ in STANDARD_ENVS].index(slot) if slot else len(STANDARD_ENVS) + pos
        cards_.append((rank,
            f'<div class="env" data-p="{st}"><div class="eh"><b>{esc(name)}</b>'
            + (f'<span class="chip" title="fills the standard {slot} slot">{slot}</span>' if slot and slot != name.lower() else "")
            + f'{"<span class=chip>default</span>" if name == default else ""}'
            f'<span class="sp"></span><span class="pill {st}">{esc(word)}</span></div>'
            f'<div class="eu">{link}</div>' + (f'<p class="ed">{esc(e["description"])}</p>' if e.get("description") else "")
            + progress(items) + '<div class="lbl3">Checklist</div>' + checklist(items)
            + "".join(f'<div class="kv"><span>{k}</span><b>{v}</b></div>' for k, v in meta)
            + (f'<div class="lbl3">Rules</div><ul class="rules">{"".join(f"<li>{esc(r)}</li>" for r in rules)}</ul>' if rules else "")
            + '</div>'))
    cards_.sort(key=lambda x: x[0])
    absent = [s for s, n in slots.items() if not n and s not in settled]
    summary = (f'{ready} of {total} recorded environment{"s" if total != 1 else ""} complete'
               + (f'; not in the registry: {", ".join(absent)}' if absent else "")) if envs else \
        "No environment recorded yet: dev, staging and prod below are what the environments skill will ask for"
    envhtml = (f'<div class="envhd"><span class="lbl3">Environments</span><span class="es">{esc(summary)}</span></div>'
               f'<div class="envs">{"".join(c for _, c in cards_)}</div>')
    if not envs:
        envhtml += ('<div class="eo"><b>No environment registry yet</b><p>Each environment will show a checklist: URL, branch, policy, '
                    'services with deploy, verify, rollback and version commands, test accounts and every secret reference '
                    '(names only, never values). Deploy, SSH and test-account skills ask every time until it exists.</p>'
                    '<code>run the environments skill (create section) -> .agents/environments.json</code></div>')
    return (f'<section class="card" id="envs"><div class="hd">{icon("Project")}<h2>Project & environments</h2>'
            f'<span class="desc">From the project-init block and .agents/environments.json; secret values are never shown</span></div>'
            f'{integration_banner(project, registry, ib_row)}<div class="facts">{block}</div>{envhtml}</section>')


# ---------------------------------------------------------------- render

DESCS = {
    "Global instructions": "The agent-skills plugin, which brings the skills, the gate hooks and the global rules",
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
OPTIONAL_TITLES = {"Legacy install.sh links", "~/OPINIONS.md -> OPINIONS.md", "Other user skills", "settings.json backups",
                   "Bypass-permissions prompt skipped", "Playwright config", "Open TODO(owner)", "Repository",
                   "Project checks (verify-loop)", "vercel login", "op sign-in", "docker compose"}
CORE_PLUGIN_TITLES = {"Browser tool for e2e-verify"}
TOOL_KIND = {name: kind for name, kind, _, _ in TOOLS}


def tier_of(c):
    sec, title = c["section"], c["title"]
    if c.get("group") == "env":   # environment gaps other than prod policy and literal secrets (env_checks)
        return "optional"
    if title in OPTIONAL_TITLES or title.endswith(": logs field"):
        return "optional"
    if sec == "Skills":
        return SKILL_TIER.get(title.split(":")[0], "optional")
    if sec == "Tools":
        return "core" if TOOL_KIND.get(title, "required") == "required" else "optional"
    if sec == "Plugins & MCP":
        return "core" if title in CORE_PLUGIN_TITLES else "optional"
    return "core"


def readiness(checks):
    """Percent ready; every skill row together weighs 3 checks so 20 skills do not drown the rest. A pending row (in an
    open PR/MR) counts as not done until it is merged."""
    scored = [c for c in checks if c["status"] in ("ok", "warn", "fail", "missing", "pending")]
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
        items = [c for c in by_sec.get(sec, []) if c["tier"] == tier and c["status"] in ("ok", "warn", "fail", "missing", "pending")]
        if not items:
            continue
        ok = sum(1 for c in items if c["status"] == "ok")
        bad = sum(1 for c in items if c["status"] in ("fail", "missing"))
        pend = sum(1 for c in items if c["status"] == "pending")
        warn = len(items) - ok - bad - pend
        st = "ok" if ok == len(items) else "fail" if bad else "warn" if warn else "pending"
        seg = lambda n, cls: f'<i class="{cls}" style="flex:{n}"></i>' if n else ""
        rows.append(f'<a class="trow" href="#{slug(sec)}"><span class="dot {st}"></span><span class="tn">{esc(sec)}</span>'
                    f'<span class="tbar">{seg(ok, "ok")}{seg(pend, "pending")}{seg(warn, "warn")}{seg(bad, "bad")}</span>'
                    f'<span class="tc">{ok}/{len(items)}</span></a>')
    pending = sum(1 for c in mine if c["status"] == "pending")
    # Pending rows are not gaps to fix, but the tier is not done until they are merged, so "All set" waits for them.
    status = (f'<span class="pill {"fail" if tier == "core" else "warn"}">{gaps} to fix</span>' if gaps else
              f'<span class="pill pending">{pending} waiting on merge</span>' if pending else
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
        names = ": " + ", ".join(skills) if len(skills) <= 6 else " (install the agent-skills plugin)"
        notes = [f"{len(skills)} skill{'s' if len(skills) > 1 else ''} not installed{names}"] if skills else []
        notes += [f'{c["title"]}: {c["detail"]}' for c in bad + warn if c["section"] != "Skills"]
        notes += [f"plugin {x} not enabled" for x in missing_plugins]
        related[pl["id"]] = notes
    return status, related, alerts


SETUP_PROMPT = """Check my agent harness and finish setting it up in this run, with the harness-map skill's setup flow (section 3 of its SKILL.md). This is a setup request: do not stop after the report.
If the harness-map skill is not installed, follow https://hephaestus-skills-docs.vercel.app/install.md, which clones, checks and installs it, and continue this setup in the same run.

1. Run harness-map for this project and open the page so I can see what is set up and what is missing.
2. Draft every decision the whole setup needs, from the machine and the repo: the plugin install, each name clash (keep mine, fork yours as hx-<name>, or switch), deleting a legacy hook entry, which branch PRs go into (never assume dev or main), which environments exist (local or dev, staging, prod, any other, each with its URL, drafted from env docs such as .claude/environments*.md, .env*.example, .vercel, supabase, CI and deploy scripts), the tracker, test account roles and logins, whether to run the version and verify probe on prod once (default no), and which optional items I want.
3. Ask me all of it in one message, your drafted answers shown, then do everything without asking again; project-init and environments take those answers instead of asking their own.
4. Run project-init and environments for this repo in the same run; if this is not a git repo, say so and skip only those two.
5. After each step, regenerate the page and open it again so I can see the progress.
6. You are done only when a final run shows core 100%, except what only I can do (moving or rotating a secret, a login, filling .agents/secrets.env, merging the setup PR) and changes I declined in the batch. End with those as "Waiting on you" and "Declined", each with its exact command, and show that every core gap left on the page is in one of them.

Never read, print, move or delete a secret value or its backups, and never ask me for one in chat; tell me what to do and I do it. Prod settings looser than the defaults need my explicit words. Give me the `! <command>` for any login."""


SETUP_PILL = '<span class="pill fail">Setup</span>'


def setup_prompt():
    """The prompt the user pastes to start the setup flow (SKILL.md section 3); the agent finds the gaps itself."""
    return SETUP_PROMPT


def render(checks, cards, plugins, project, probe, registry=None, opt=0):
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
                 f'<span class="chips">{SETUP_PILL if palert[pl["id"]] else ""}'
                 f'<span class="pill {pst[pl["id"]]}">{WHEEL_WORD[pst[pl["id"]]]}</span></span></a>' for pl in PILLARS)
    covered = sum(1 for v in pst.values() if v == "ok")
    need = sum(1 for v in palert.values() if v)
    prompt = setup_prompt()
    ncore = sum(1 for c in actions if c["tier"] == "core")
    nopt = len(actions) - ncore
    h.append(f'<section class="card prompt" id="prompt"><div class="hd">{icon("Tools")}<h2>Setup prompt</h2>'
             f'<span class="desc">Paste into Claude Code in your project: the agent checks what is missing, asks you for what it needs, and reopens this page after each step. Now: {ncore} core and {nopt} optional gaps</span>'
             f'<div class="bar"><button class="btn ghost" type="button" data-expand="prompt-text">Expand</button>'
             f'<button class="btn primary" type="button" data-copy="prompt-text">Copy prompt</button></div></div>'
             f'<pre id="prompt-text" class="ptext">{esc(prompt)}</pre></section>')
    h.append(f'<section class="card" id="wheel"><div class="hd">{icon("Skills")}<h2>Harness wheel</h2>'
             f'<span class="desc">Color: how fully this repo covers each component. Red badge: not set up on this machine. Hover or tap for details</span></div>'
             f'<div class="wheelwrap">{wheel_svg(pst, ("Agent Harness", f"{covered}/{len(PILLARS)} fully covered"), palert)}<div class="wlist">{wl}</div></div>'
             f'{pillar_cards(pst, prel, {c["name"]: c["installed"] for c in cards}, palert)}</section>')
    h.append(f'<div class="tiers" id="overview">{tier_block("core", checks, by_sec, actions)}{tier_block("optional", checks, by_sec, actions)}</div>')

    h.append('<div class="grid"><nav class="side"><div class="h">Overview</div><a href="#prompt">Setup prompt</a><a href="#wheel">Harness wheel</a><a href="#overview">Core and optional</a><a href="#envs">Project & environments</a>'
             f'<a href="#todo">Fix first<span class="c">{len(actions)}</span></a><div class="h">Checks</div>')
    for sec in ORDER:
        if sec in by_sec:
            bad = sum(1 for c in by_sec[sec] if c["status"] in ("fail", "missing", "warn"))
            st = min((c["status"] for c in by_sec[sec]), key=RANK.get)
            h.append(f'<a href="#{slug(sec)}"><span class="dot {st}"></span>{esc(sec)}<span class="c">{bad or ""}</span></a>')
    h.append('<a href="#catalog">Skill catalog</a></nav><div>')


    h.append(env_panel(project, registry, next((c for c in checks if c["section"] == "Project" and c["title"] == "Integration branch"), None)))
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
        for s in ("fail", "missing", "warn", "pending", "ok"):
            n = sum(1 for c in rows if c["status"] == s)
            if n:
                h.append(f'<span class="pill {s}">{n} {LABEL[s]}</span>')
        h.append('</div></div>')
        seen = set()
        for c in rows:
            # A fix shared by many rows (install.sh for every skill) is shown once, on its first row.
            fx = "" if c["fix"] in seen else fix_html(c["fix"])
            seen.add(c["fix"])
            h.append(f'<div class="row" data-s="{c["status"]}" data-t="{c["tier"]}"><div>{pill(c["status"])}</div><div class="t">{ult(c["title"]) if c["section"] == "Skills" else esc(c["title"])} {tier_chip(c["tier"])}</div>'
                     f'<div class="d">{esc(c["detail"])}{fx}</div></div>')
        h.append('</section>')

    h.append(f'<section class="card" id="catalog"><div class="hd">{icon("Skills")}<h2>Skill catalog</h2><span class="desc">{len(cards)} skills in this repo</span></div>')
    for tier in ("core", "optional"):
        group = [s for s in cards if SKILL_TIER.get(s["name"], "optional") == tier]
        if not group:
              continue
        h.append(f'<div class="cath" data-t="{tier}">{tier_chip(tier)}<span>{len(group)} skills. {esc(TIER_TEXT[tier][1])}</span></div><div class="skills">')
        for s in group:
            chips = ['<span class="chip acc">' + ult(s["name"], "/" + s["name"]) + '</span>' if s["invocable"] else '<span class="chip agent">auto-loaded</span>']
            if s["name"] in ULTIMATE:
                chips.insert(0, '<span class="chip ultchip"><span class="ult">ultimate</span></span>')
            chips.append('<span class="chip">installed</span>' if s["installed"] else '<span class="chip bad">not installed</span>')
            chips += [f'<span class="chip">{esc(x)}/</span>' for x in s["extras"]]
            chips += [f'<span class="chip warn">{esc(i)}</span>' for i in s["issues"]]
            h.append(f'<div class="skill" data-s="{s["status"]}" data-t="{tier}"><div class="nm"><span class="mono" style="font-size:13px;font-weight:600">{ult(s["name"])}</span><span class="dot {s["status"]}"></span></div>'
                     f'<p title="{esc(s["desc"])}">{esc(s["desc"])}</p><div class="chips">{"".join(chips)}</div></div>')
        h.append('</div>')
    h.append('</section>')
    h.append('</div></div>')
    # One page, two tabs: the live dashboard and the docs; a link to a docs section opens the Docs tab.
    body = (f'<div class="pane" data-pane="dash">{"".join(h)}</div>'
            f'<div class="pane" data-pane="docs">{docs_body(live_hooks())}</div>' + skill_sources())
    tools = ('<div class="seg tabs" role="tablist" aria-label="View"><button data-tab="dash" role="tab" aria-pressed="true">Dashboard</button>'
             '<button data-tab="docs" role="tab" aria-pressed="false">Docs</button></div>'
             '<div class="seg" role="group" aria-label="Filter"><button data-view="all" aria-pressed="true">All</button>'
             '<button data-view="core" aria-pressed="false">Core only</button>'
             '<button data-view="action" aria-pressed="false">Needs action</button></div>')
    footer = (f'Generated by <span class="mono">skills/harness-map/scripts/harness_map.py</span>, docs {esc(release_version())}. '
              'Read-only; secret values are never shown. Re-run to refresh.')
    page = render_page("Harness Map", "Hephaestus Skills", "/ Harness Map / " + socket.gethostname().split(".")[0], body, footer, tools)
    return page, score, count, actions


SITE_NAME = "Hephaestus Skills"
SITE_DESC = ("Hephaestus Skills, a Claude Code plugin: 25 agent skills, safety hooks and global rules, "
             "with the lifecycle map, task path and every skill in full.")
REPO_URL = "https://github.com/quocld/hephaestus-agent-skills"
AUTHOR = {"name": "Ryan Le", "login": "quocld", "url": "https://github.com/quocld"}
# Repo files the docs site publishes as pages of their own: (slug, source, title, description). The repo file is the
# one source; the page only renders it, and every page's footer links to all of them.
REPO_PAGES = [
    ("license", "LICENSE", "License", f"{SITE_NAME} is open source under the MIT License; adapted parts keep their upstream licenses."),
    ("privacy", "policies/privacy.md", "Privacy policy", f"What the {SITE_NAME} docs site and plugin collect: no accounts, no analytics, no telemetry."),
    ("terms", "policies/terms.md", "Terms of use", f"Terms for the {SITE_NAME} docs site and plugin: MIT License, no warranty, you review what your agent does."),
    ("contributing", "CONTRIBUTING.md", "Contributing", f"How to propose a change to {SITE_NAME}: issues, pull requests, commit style and the checks CI runs."),
    ("code-of-conduct", "CODE_OF_CONDUCT.md", "Code of conduct", f"The {SITE_NAME} code of conduct, based on the Contributor Covenant 2.1, and how to report a problem."),
]
GITHUB_ICON = ('<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 '
               '3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15'
               '-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82'
               '-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92'
               '.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 '
               '8.013 0 0016 8c0-4.42-3.58-8-8-8z"/></svg>')
HEADER_GITHUB = f'<a class="btn ghost ghlink" href="{REPO_URL}" rel="noopener" aria-label="{SITE_NAME} on GitHub">{GITHUB_ICON}<span>GitHub</span></a>'


def author_ld():
    return {"@type": "Person", "name": AUTHOR["name"], "alternateName": AUTHOR["login"], "url": AUTHOR["url"], "sameAs": [AUTHOR["url"]]}


def seo_head(title, desc, url, site_url, gsc_token, ld, og_type="website", crumbs=None):
    """Search and sharing metadata for one page of the docs site: description, author, license, canonical, Open Graph,
    Twitter, JSON-LD (the page, plus a breadcrumb trail for any page below the home page), and the Google Search
    Console verification tag when a token is given. crumbs: [(name, url)] from the home page down to this page."""
    tags = [f'<meta name="description" content="{esc(desc)}">', '<meta name="robots" content="index,follow">',
            f'<meta name="author" content="{esc(AUTHOR["name"])}">', '<meta name="theme-color" content="#0c0a09">',
            '<link rel="author" href="/about/">', '<link rel="license" href="/license/">']
    if site_url:
        tags += [f'<link rel="canonical" href="{esc(url)}">',
                 f'<meta property="og:url" content="{esc(url)}">',
                 f'<meta property="og:image" content="{esc(site_url)}/icon.png">',
                 '<meta property="og:image:width" content="512"><meta property="og:image:height" content="512">',
                 f'<meta property="og:image:alt" content="{SITE_NAME} logo: a hammer striking hot metal on an anvil">',
                 f'<meta name="twitter:image" content="{esc(site_url)}/icon.png">']
    tags += [f'<meta property="og:type" content="{esc(og_type)}">', f'<meta property="og:site_name" content="{SITE_NAME}">',
             '<meta property="og:locale" content="en_US">',
             f'<meta property="og:title" content="{esc(title)}">', f'<meta property="og:description" content="{esc(desc)}">',
             '<meta name="twitter:card" content="summary">', f'<meta name="twitter:title" content="{esc(title)}">',
             f'<meta name="twitter:description" content="{esc(desc)}">',
             '<link rel="apple-touch-icon" href="/icon.png">']
    if gsc_token:
        tags.append(f'<meta name="google-site-verification" content="{esc(gsc_token)}">')
    ld = dict(ld, author=author_ld(), inLanguage="en")
    if site_url:
        ld["license"] = f"{site_url}/license/"
    graph = [ld]
    if crumbs and site_url:
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i, "name": n, "item": u} for i, (n, u) in enumerate(crumbs, 1)]})
    data = {"@context": "https://schema.org", "@graph": [{k: v for k, v in g.items() if k != "@context"} for g in graph]}
    # JSON in a script tag: escape "<" so no value can close the tag.
    tags.append('<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False).replace("<", "\\u003c") + '</script>')
    return "\n".join(tags)


def short_desc(text, limit=155):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def site_footer(version, sha):
    """The footer of every docs page: author, the repo, the release, and the license, policy and contributing pages."""
    links = "".join(f'<a href="/{slug}/">{esc(title)}</a>' for slug, _, title, _ in REPO_PAGES)
    return (f'<div class="sitefoot"><div class="byline">Built by <a href="/about/" rel="author">{esc(AUTHOR["name"])}</a> '
            f'(<a href="{AUTHOR["url"]}" rel="noopener">@{esc(AUTHOR["login"])}</a>) · '
            f'<a href="{REPO_URL}" rel="noopener">Source on GitHub</a> · MIT License</div>'
            f'<nav class="footlinks" aria-label="Site">{links}<a href="/about/">About</a>'
            f'<a href="{REPO_URL}/issues" rel="noopener">Issues</a></nav>'
            f'<div>{SITE_NAME} <a href="{REPO_URL}/releases/tag/{esc(version)}" rel="noopener">{esc(version)}</a>, commit '
            f'<a class="mono" href="{REPO_URL}/commit/{esc(sha)}" rel="noopener">{esc(sha[:12])}</a>. '
            'Generated by <span class="mono">harness_map.py --docs-only</span> from the repo alone.</div></div>')


def repo_markdown(md):
    """Repo-relative links in a repo Markdown file, made absolute for the site: a file the site publishes as a page
    links to that page, anything else to the file on GitHub."""
    pages = {src: f"/{slug}/" for slug, src, _, _ in REPO_PAGES}
    def fix(m):
        target = m.group(2)
        if re.match(r"[a-z]+:|#|/", target):
            return m.group(0)
        path = target.lstrip("./").rstrip("/")
        dest = pages.get(path) or f"{REPO_URL}/{'tree' if target.endswith('/') else 'blob'}/main/{path}"
        return f"[{m.group(1)}]({SITE_URL_PLACEHOLDER}{dest})" if dest.startswith("/") else f"[{m.group(1)}]({dest})"
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", fix, md)


# render_markdown links only http(s) URLs; site pages get this prefix, swapped back to "" after rendering.
SITE_URL_PLACEHOLDER = "https://site.invalid"


def write_docs_site(out_dir, site_url=None, gsc_token=None):
    """The public docs site: no checks, no settings, no paths or host names, so it can be published as is.
    index.html, one crawlable page per skill under skills/<name>/, the install guide the onboarding prompt points at
    (install.md for agents, install/ for people), the about page, the license, policy and contributing pages
    (REPO_PAGES), 404.html, sitemap.xml, robots.txt, icon.png, version.json."""
    from harness_docs import ONBOARD_BUTTON, onboard_source, repo_hooks
    from page import render_markdown, repo_skills, skill_doc
    import shutil as _sh
    site_url = (site_url or "").rstrip("/") or None
    code, sha, _ = run(["git", "-C", str(REPO), "rev-parse", "HEAD"])
    sha = sha.strip() if code == 0 else os.environ.get("GIT_SHA", "unknown")
    code, when, _ = run(["git", "-C", str(REPO), "log", "-1", "--format=%cI"])
    lastmod = when.strip()[:10] if code == 0 and when.strip() else dt.date.today().isoformat()
    version = release_version()
    footer = site_footer(version, sha)
    tools = ONBOARD_BUTTON + HEADER_GITHUB
    out_dir.mkdir(parents=True, exist_ok=True)
    home = f"{site_url}/" if site_url else ""
    urls = []

    def md_html(md):
        """A repo Markdown file as page content: its "# " title becomes the page's one h1, the rest the article."""
        m = re.match(r"#\s+(.+)\n", md)
        title_ = f'<div class="rmeta"><h1 class="ptitle">{esc(m.group(1).strip())}</h1></div>' if m else ""
        html_ = title_ + '<article class="md">' + render_markdown(repo_markdown(md[m.end():] if m else md)) + "</article>"
        return re.sub(rf'href="{re.escape(SITE_URL_PLACEHOLDER)}(/[^"]*)" target="_blank" rel="noopener"', r'href="\1"', html_)

    def emit(path, title, crumb, desc, body, ld, og_type="website", crumbs=None):
        """Write one page at <path>/index.html ("" is the home page) and list it in the sitemap."""
        url = f"{site_url}/{path}/" if site_url and path else home
        if site_url:
            ld = dict(ld, url=url)
        trail = [(f"{SITE_NAME} Docs", home)] + [(n, f"{site_url}/{p}/") for n, p in (crumbs or [])] if path else None
        page = render_page(title, SITE_NAME, crumb, body, footer, tools,
                           head=seo_head(title, desc, url, site_url, gsc_token, ld, og_type, trail))
        (out_dir / path).mkdir(parents=True, exist_ok=True)
        (out_dir / path / "index.html").write_text(page)
        urls.append(url)

    def doc_page(path, title, crumb, desc, side, crumbs_html, content, ld, og_type="website", crumbs=None):
        """A page in the docs layout: side navigation, breadcrumbs, one card of content."""
        body = (f'<div class="grid skillpage"><nav class="side">{side}</nav>'
                f'<div><p class="crumbs">{crumbs_html}</p><section class="card"><div class="rbody">{content}</div></section></div></div>'
                + onboard_source())
        emit(path, f"{title} | {SITE_NAME}", crumb, desc, body, ld, og_type, crumbs)

    title = f"{SITE_NAME} Docs: agent skills for Claude Code"
    ld = {"@type": "WebSite", "name": f"{SITE_NAME} Docs", "description": SITE_DESC, "publisher": author_ld(),
          "sameAs": [REPO_URL]}
    body = docs_body(repo_hooks(), standalone=True) + skill_sources() + onboard_source()
    emit("", title, "/ Docs", SITE_DESC, body, ld)
    site_ld = {"@type": "WebSite", "name": f"{SITE_NAME} Docs", **({"url": home} if site_url else {})}

    skills = repo_skills()
    for d, fm in skills:
        nav = "".join(f'<a href="/skills/{esc(n.name)}/"' + (' aria-current="page"' if n.name == d.name else "") + f'>{esc(n.name)}</a>'
                      for n, _ in skills)
        doc = skill_doc(d, fm, title_tag="h1")
        if not doc:
            continue
        desc = short_desc(fm.get("description", "")) or f"The {d.name} agent skill of {SITE_NAME}."
        src = f"{REPO_URL}/blob/main/skills/{d.name}/SKILL.md"
        source = (f'<p class="srclinks"><a href="{REPO_URL}/tree/main/skills/{esc(d.name)}" rel="noopener">{GITHUB_ICON} View {esc(d.name)} on GitHub</a>'
                  f'<a href="{src}" rel="noopener">SKILL.md source</a><a href="{REPO_URL}/edit/main/skills/{esc(d.name)}/SKILL.md" rel="noopener">Suggest an edit</a></p>')
        ld = {"@type": "TechArticle", "headline": f"{d.name} skill", "description": desc, "isPartOf": site_ld,
              "dateModified": lastmod, "isBasedOn": src}
        doc_page(f"skills/{d.name}", f"{d.name} skill", f"/ Docs / {d.name}", desc,
                 f'<div class="h">Skills</div><a href="/">All docs</a>{nav}',
                 f'<a href="/">Docs</a> / <a href="/#skill-reference">Skills</a> / {esc(d.name)}',
                 doc[0] + source + doc[1], ld, "article", [(d.name, f"skills/{d.name}")])

    guide = (SKILL / "assets" / "install-guide.md").read_text()
    (out_dir / "install.md").write_text(guide)
    gdesc = f"How a coding agent installs {SITE_NAME} without overwriting the harness it already has."
    doc_page("install", f"Install {SITE_NAME}", "/ Docs / Install", gdesc,
             '<div class="h">Install</div><a href="/">All docs</a><a href="/install.md">install.md (for agents)</a>'
             f'<a href="{REPO_URL}/blob/main/skills/harness-map/assets/install-guide.md" rel="noopener">Source on GitHub</a>',
             '<a href="/">Docs</a> / Install', md_html(guide),
             {"@type": "HowTo", "name": f"Install {SITE_NAME}", "description": gdesc, "isPartOf": site_ld},
             crumbs=[("Install", "install")])

    def side_for(cur):
        """The side navigation of the project pages, with the current one marked."""
        items = [(s_, t) for s_, _, t, _ in REPO_PAGES] + [("about", "About")]
        return ('<div class="h">Project</div><a href="/">All docs</a>'
                + "".join(f'<a href="/{s_}/"' + (' aria-current="page"' if s_ == cur else "") + f'>{esc(t)}</a>' for s_, t in items)
                + f'<a href="{REPO_URL}" rel="noopener">GitHub</a>')

    about_desc = f"{SITE_NAME} is built and maintained by {AUTHOR['name']} (@{AUTHOR['login']}) on GitHub."
    about = (f'<div class="profile"><img src="{AUTHOR["url"]}.png?size=160" width="80" height="80" alt="{esc(AUTHOR["name"])} on GitHub" loading="lazy">'
             f'<div><h1 class="ptitle">{esc(AUTHOR["name"])}</h1><p class="rdesc"><a href="{AUTHOR["url"]}" rel="me noopener">{GITHUB_ICON} @{esc(AUTHOR["login"])} on GitHub</a></p></div></div>'
             f'<article class="md"><p>{esc(AUTHOR["name"])} builds and maintains {SITE_NAME}: a Claude Code plugin with global agent rules, agent skills for the '
             'whole development loop, and safety hooks, made for teams that run several AI coding agents in parallel on one repository.</p>'
             '<h2>The project</h2><ul>'
             f'<li>Source code, issues and releases: <a href="{REPO_URL}" rel="noopener">github.com/quocld/hephaestus-agent-skills</a></li>'
             f'<li>Releases and changelog: <a href="{REPO_URL}/releases" rel="noopener">GitHub releases</a></li>'
             '<li>License: <a href="/license/">MIT</a>; adapted parts keep their upstream licenses</li>'
             '<li>Contribute: <a href="/contributing/">contributing guide</a> and <a href="/code-of-conduct/">code of conduct</a></li>'
             '<li>Policies: <a href="/privacy/">privacy policy</a> and <a href="/terms/">terms of use</a></li></ul></article>')
    doc_page("about", f"About {AUTHOR['name']}", "/ Docs / About", about_desc, side_for("about"), '<a href="/">Docs</a> / About', about,
             {"@type": "ProfilePage", "name": f"About {AUTHOR['name']}", "description": about_desc, "isPartOf": site_ld,
              "mainEntity": author_ld()}, "profile", [("About", "about")])

    for slug, src, ptitle, desc in REPO_PAGES:
        text = (REPO / src).read_text()
        if src.endswith(".md"):
            content = md_html(text)
        else:
            sources = (REPO / "SOURCES.md").read_text().split("\n", 1)[1]
            content = (f'<div class="rmeta"><h1 class="ptitle">{esc(ptitle)}</h1></div><article class="md"><p>{SITE_NAME} is released '
                       f'under the MIT License below. <a href="{REPO_URL}/blob/main/{src}" rel="noopener">View it on GitHub</a>.</p>'
                       f'<pre class="license">{esc(text)}</pre></article>' + md_html("## Third-party sources\n\n" + sources))
        content += f'<p class="srclinks"><a href="{REPO_URL}/blob/main/{src}" rel="noopener">{GITHUB_ICON} {esc(src)} on GitHub</a><a href="{REPO_URL}/commits/main/{src}" rel="noopener">History</a></p>'
        doc_page(slug, ptitle, f"/ Docs / {ptitle}", desc, side_for(slug), f'<a href="/">Docs</a> / {esc(ptitle)}', content,
                 {"@type": "WebPage", "name": ptitle, "description": desc, "isPartOf": site_ld, "dateModified": lastmod},
                 crumbs=[(ptitle, slug)])

    nf = render_page(f"Page not found | {SITE_NAME}", SITE_NAME, "/ Docs / Not found",
                     '<section class="card notfound"><div class="rbody"><div class="rmeta"><h1 class="ptitle">Page not found</h1></div>'
                     '<p class="md">This page does not exist, or it moved. Try the <a href="/">docs home</a>, the '
                     '<a href="/#skill-reference">skill reference</a>, or the <a href="/install/">install guide</a>.</p></div></section>'
                     + onboard_source(), footer, tools, head='<meta name="robots" content="noindex">')
    (out_dir / "404.html").write_text(nf)

    icon = REPO / "assets" / "icon.png"
    if icon.exists():
        _sh.copy(icon, out_dir / "icon.png")
    robots = "User-agent: *\nAllow: /\n" + (f"Sitemap: {site_url}/sitemap.xml\n" if site_url else "")
    (out_dir / "robots.txt").write_text(robots)
    if site_url:
        entries = "".join(f"<url><loc>{esc(u)}</loc><lastmod>{lastmod}</lastmod></url>" for u in urls)
        (out_dir / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                             f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>\n')
    (out_dir / "version.json").write_text(json.dumps({"sha": sha, "version": version}) + "\n")
    print(f"Docs site {version}: {out_dir / 'index.html'} + {len(skills)} skill pages + install guide + about, "
          f"{len(REPO_PAGES)} project pages and 404 (commit {sha[:12]})"
          + ("" if site_url else "; no --site-url, so no canonical links or sitemap"))
    return 0


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
    ap.add_argument("--no-probe", action="store_true", help="skip hooks/test.sh and the login status checks (gh, glab, vercel, op)")
    ap.add_argument("--open", action="store_true", help="open the report in the default browser")
    ap.add_argument("--prompt", action="store_true", help="print only the setup prompt (still writes the page)")
    ap.add_argument("--version", help="release version to show (default: newest v* tag, else dev)")
    ap.add_argument("--site-url", default=os.environ.get("DOCS_SITE_URL"),
                    help="public URL of the docs site, for canonical links, Open Graph and sitemap.xml (--docs-only)")
    ap.add_argument("--gsc-token", default=os.environ.get("GOOGLE_SITE_VERIFICATION"),
                    help="Google Search Console HTML-tag verification token (--docs-only)")
    ap.add_argument("--docs-only", metavar="DIR", help="write the public docs site to DIR (index.html, version.json): "
                    "the Docs tab and the harness wheel only, built from the repo alone, nothing about this machine")
    a = ap.parse_args()
    page_mod.VERSION_OVERRIDE = a.version
    if a.docs_only:
        return write_docs_site(Path(a.docs_only), a.site_url, a.gsc_token)

    project = git_root(a.project or os.getcwd())
    if a.project and not project:
        sys.exit(f"--project {a.project} is not inside a git repo")
    global PLUGIN_ID, PLUGIN_DIR
    PLUGIN_ID, PLUGIN_DIR = agent_skills_plugin(project)
    probe = not a.no_probe

    checks = collect_global()
    refs = Refs(project, probe, load_json(project / ".agents" / "environments.json")) if project else None
    sk, cards = collect_skills(project, refs)
    checks += sk
    checks += collect_hooks(probe, project)
    pc, registry = collect_project(project, probe, refs=refs)
    tc, _ = collect_tools(probe, registry, project)
    checks += tc
    plc, plugins = collect_plugins(project, registry, probe)
    checks += plc + collect_hygiene() + pc
    for c in checks:
        c["tier"] = tier_of(c)

    opt = readiness([c for c in checks if c["tier"] == "optional"])
    page, score, count, actions = render(checks, cards, plugins, project, probe, registry, opt)
    out = Path(a.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page)

    if a.prompt:
        print(setup_prompt())
        return
    print(f"Harness map: {out}  (tabs: Dashboard, Docs)")
    print(f"Core ready {score}%  optional ready {opt}%  ok {count['ok']}  attention {count['warn']}  missing/failing {count['missing'] + count['fail']}"
          + (f"  pending {count['pending']}" if count["pending"] else ""))
    for i, c in enumerate(actions, 1):
        print(f"{i:>2}. [{c['tier']}] [{LABEL[c['status']]}] {c['section']} / {c['title']}: {c['detail']}" + (f"\n    fix: {c['fix']}" if c["fix"] else ""))
    pending = [c for c in checks if c["status"] == "pending"]
    if pending:
        print("Waiting on a merge (pending, not a gap to fix):")
        for c in pending:
            print(f"  - [{c['tier']}] {c['section']} / {c['title']}: {c['detail']}")
    unmapped, stale = unplaced_skills()
    if unmapped:
        print("Not placed in assets/lifecycle.json: " + ", ".join(unmapped))
    if stale:
        print("In assets/lifecycle.json but no such skill: " + ", ".join(stale))
    if a.open:
        run(["open" if sys.platform == "darwin" else "xdg-open", str(out)])


if __name__ == "__main__":
    main()
