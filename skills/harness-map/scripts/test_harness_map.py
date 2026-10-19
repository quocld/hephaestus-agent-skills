#!/usr/bin/env python3
"""Regression tests for harness_map.py: no secret value reaches the page or stdout, malformed inputs do not crash,
and the scripts compile on the oldest python3 a fresh Mac ships (3.9). Builds throwaway HOME and project folders;
never touches the real ~/.claude. Usage: python3 test_harness_map.py  (exit 1 on any failure)
"""
import json
import re
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "harness_map.py"
# Each value stands in for a real secret; none may appear in the page or the terminal output. Token-like prefixes are
# joined at run time so this file never looks like it holds a real token to secret scanners.
LEAKS = {
    "registry literal password": "LeakRegistryPass1",
    "registry literal secret object": "LeakRegistrySecret2",
    "git remote credentials": "gh" + "p_LeakRemoteToken3",
    "inline env in a hook command": "xox" + "b-LeakHookToken4",
    "settings env literal": "LeakSettingsEnv5",
    "secrets.env value": "LeakSecretsFile6",
    "MCP server env literal": "LeakMcpEnv7",
    "marketplace URL credentials": "gl" + "dt-LeakMarketplace8",
    "environment URL basic auth": "LeakEnvUrlPass9",
    "quoted inline env in a hook": "LeakQuotedHook10",
    "@ inside a remote password": "LeakAfterAt11",
    "token-only marketplace URL": "gh" + "p_LeakTokenOnly12",
    "literal mfa": "LeakMfa13",
    "URL with leading whitespace": "LeakSpaceUrl14",
    "URL with a newline": "LeakNewlineUrl15",
    "slash in a URL password": "LeakSlashUrl16",
    "literal dbUrl string": "LeakDbUrl17",
    "unbalanced quote in a hook": "LeakUnbalanced18",
}
FAILS = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def run(home, project, extra=(), python=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("JIRA_", "CLAUDE_"))}
    env["HOME"] = str(home)
    out = home / "page.html"
    if out.exists():
        out.unlink()
    p = subprocess.run([python or sys.executable, str(SCRIPT), "--no-probe", "--project", str(project), "--out", str(out), *extra],
                       capture_output=True, text=True, env=env, timeout=120)
    page = out.read_text() if out.exists() else ""
    return p.returncode, p.stdout + p.stderr, page


def leaky_machine(root):
    home, project = root / "home", root / "project"
    claude = home / ".claude"
    (claude / "plugins").mkdir(parents=True)
    hook_cmd = "SLACK_TOKEN=" + LEAKS["inline env in a hook command"] + " python3 /opt/hooks/notify.py"
    quoted = 'API_KEY="abc ' + LEAKS["quoted inline env in a hook"] + '" python3 /opt/hooks/other.py'
    unbalanced = 'API_KEY="abc ' + LEAKS["unbalanced quote in a hook"] + ' python3 /opt/hooks/third.py'
    (claude / "settings.json").write_text(json.dumps({
        "env": {"SLACK_TOKEN": LEAKS["settings env literal"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": hook_cmd},
                                                               {"type": "command", "command": quoted},
                                                               {"type": "command", "command": unbalanced}]}]},
    }))
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"x": {"env": {"API_KEY": LEAKS["MCP server env literal"]}}}}))
    url = "https://gitlab+deploy-token-1:" + LEAKS["marketplace URL credentials"] + "@git.example.com/x.git"
    token_only = "https://" + LEAKS["token-only marketplace URL"] + "@github.com/acme/market.git"
    (claude / "plugins" / "known_marketplaces.json").write_text(json.dumps({
        "team": {"source": {"source": "git", "url": url}}, "tokenonly": {"source": {"source": "git", "url": token_only}}}))
    (project / ".agents").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "remote", "add", "origin",
                    "https://user:" + LEAKS["git remote credentials"] + "@" + LEAKS["@ inside a remote password"]
                    + "@github.com/acme/app.git"], check=True)
    (project / ".gitignore").write_text(".agents/secrets.env\n")
    (project / ".agents" / "secrets.env").write_text("STAGING_DB_URL=" + LEAKS["secrets.env value"] + "\n")
    (project / ".agents" / "environments.json").write_text(json.dumps({"project": "acme", "defaultEnvironment": "dev", "environments": {
        "staging": {"policy": "confirm-writes", "url": "https://admin:" + LEAKS["environment URL basic auth"] + "@staging.acme.test", "services": [
            {"name": "web", "type": "vps", "access": {"dbUrl": {"secret": "env:STAGING_DB_URL"}}},
            {"name": "db", "type": "supabase", "access": {"dbUrl": "postgres://u:" + LEAKS["literal dbUrl string"] + "@h/db"}}],
            "accounts": [{"role": "admin", "login": "a@acme.test", "password": LEAKS["registry literal password"],
                          "mfa": LEAKS["literal mfa"]},
                         {"role": "member", "login": "m@acme.test", "password": {"secret": LEAKS["registry literal secret object"]}}]},
        "qa1": {"policy": "confirm-writes", "url": " https://admin:" + LEAKS["URL with leading whitespace"] + "@qa1.acme.test", "services": []},
        "qa2": {"policy": "confirm-writes", "url": "https://admin:" + LEAKS["URL with a newline"] + "@qa2.acme.test\nx", "services": []},
        "qa3": {"policy": "confirm-writes", "url": "https://admin:SE/" + LEAKS["slash in a URL password"] + "@qa3.acme.test/x", "services": []}}}))
    return home, project


MALFORMED = {
    "services null": {"environments": {"dev": {"policy": "autonomous", "services": None}}},
    "accounts null": {"environments": {"dev": {"policy": "autonomous", "services": [], "accounts": None}}},
    "access null": {"environments": {"prod": {"policy": "confirm-each-step", "services": [{"name": "web", "type": "vps", "access": None}]}}},
    "url null": {"environments": {"dev": {"policy": "autonomous", "url": None, "services": []}}},
    "testing a string": {"environments": {"dev": {"policy": "autonomous", "testing": "all", "services": []}}},
    "environment a string": {"environments": {"dev": "x"}},
    "environments a list of strings": {"environments": ["dev"]},
    "no environments key": {"defaultEnvironment": "dev"},
}


MALFORMED_FILES = {
    "registry secret null": (".agents/environments.json", {"environments": {"dev": {"policy": "autonomous", "services": [],
                             "accounts": [{"role": "a", "login": "x", "password": {"secret": None}}]}}}),
    "registry secret a number": (".agents/environments.json", {"environments": {"dev": {"policy": "autonomous", "services": [],
                                 "accounts": [{"role": "a", "login": "x", "password": {"secret": 5}}]}}}),
    "service name a number": (".agents/environments.json", {"environments": {"prod": {"policy": "confirm-each-step",
                              "services": [{"name": 5, "type": "vps", "logs": "x"}]}}}),
    "marketplaces a list": ("~/.claude/plugins/known_marketplaces.json", ["x"]),
    "marketplace url a number": ("~/.claude/plugins/known_marketplaces.json", {"m": {"source": {"url": 5}}}),
    "enabledPlugins null": ("~/.claude/settings.json", {"enabledPlugins": None}),
    "plugin index null": ("~/.claude/plugins/installed_plugins.json", {"plugins": None}),
    "settings env a list": ("~/.claude/settings.json", {"env": ["X"]}),
    "settings a list": ("~/.claude/settings.json", ["x"]),
    "MCP server a string": ("~/.claude.json", {"mcpServers": {"x": "y"}}),
    "hook command null": ("~/.claude/settings.json", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": None}]}]}}),
    "hook entry hooks strings": ("~/.claude/settings.json", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": ["x"]}]}}),
}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home, project = leaky_machine(root)
        code, out, page = run(home, project)
        check(code == 0 and bool(page), "leaky machine: the page is written")
        for what, value in LEAKS.items():
            check(value not in page, f"{what}: value not in the page")
            check(value not in out, f"{what}: value not in stdout")
        for title in ("Remote URL credentials", "Credentials in plugin marketplace URLs", "literal secrets"):
            check(title in page, f"check fires: {title}")
        check("tokenonly" in page, "token-only marketplace URL is reported by name")
        check("5 secret value(s)" in page, "staging counts 5 literal secrets (password, secret object, mfa, URL, dbUrl)")
        code, out, _ = run(home, project, ["--prompt"])
        check(all(v not in out for v in LEAKS.values()), "setup prompt holds no secret value")
        check(not any(p in out for p in (str(home), "/Users/", "Desktop")), "setup prompt holds no machine path")

        for name, registry in MALFORMED.items():
            (project / ".agents" / "environments.json").write_text(json.dumps(registry))
            code, out, page = run(home, project)
            check(code == 0 and bool(page), f"malformed registry ({name}): no crash")


        for name, (rel, content) in MALFORMED_FILES.items():
            target = home / rel[2:] if rel.startswith("~/") else project / rel
            saved = target.read_text() if target.exists() else None
            target.write_text(json.dumps(content))
            code, out, page = run(home, project)
            check(code == 0 and bool(page), f"malformed file ({name}): no crash")
            if saved is None:
                target.unlink()
            else:
                target.write_text(saved)

        saved = (home / ".claude" / "settings.json").read_text()
        (home / ".claude" / "settings.json").unlink()
        code, out, page = run(home, project)
        check(code == 0 and "settings.json missing or not valid JSON" in page, "missing settings.json: headline check shown")
        (home / ".claude" / "settings.json").write_text(saved)

        plug = root / "plug"
        plug.mkdir()
        (plug / ".mcp.json").write_text(json.dumps({"mcpServers": ["x"]}))
        (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"p@m": True}}))
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"p@m": [{"installPath": str(plug)}]}}))
        code, out, page = run(home, project)
        check(code == 0 and bool(page), "plugin .mcp.json with a list: no crash")

        subprocess.run(["git", "-C", str(project), "remote", "set-url", "origin", "https://jdoe@bitbucket.org/team/app.git"], check=True)
        code, out, page = run(home, project)
        check("Remote URL credentials" not in page, "a Bitbucket user@ remote is not reported as a credential")

        (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": None, "enabledPlugins": {"a@b": True}}))
        (home / ".claude" / "settings.local.json").write_text(json.dumps({"hooks": None}))
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"a@b": {"installPath": "/nope"}}}))
        code, out, page = run(home, project)
        check(code == 0 and bool(page), "hooks null and a dict plugin index of an enabled plugin: no crash")

    # The agent-skills plugin, as Claude Code installs it: a copy with no .git. Legacy links point into another clone.
    repo = HERE.parents[2]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        home, project, plug, clone = tmp / "home", tmp / "project", tmp / "plug", tmp / "old-clone"
        (home / ".claude" / "plugins").mkdir(parents=True)
        (home / ".claude" / "skills").mkdir()
        for d in (project, plug, clone):
            d.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        for d in (plug, clone):
            tar = subprocess.run(["git", "-C", str(repo), "archive", "HEAD"], capture_output=True, check=True).stdout
            subprocess.run(["tar", "-x", "-C", str(d)], input=tar, check=True)
        shutil.copy(repo / "migrate-to-plugin.py", plug / "migrate-to-plugin.py")   # the working tree's, not HEAD's
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"agent-skills@quocld": [{"scope": "user", "installPath": str(plug)}]}}))
        (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"agent-skills@quocld": True}}))
        (home / ".claude" / "skills" / "root-cause").symlink_to(clone / "skills" / "root-cause")
        (home / ".claude" / "CLAUDE.md").symlink_to(clone / "AGENTS.md")
        code, out, page = run(home, project)
        check(code == 0 and "registered by agent-skills@quocld" in page, "plugin: gates count as registered by the plugin")
        check("from agent-skills@quocld as /agent-skills:worktree-flow" in page, "plugin: skills count as installed from the plugin")
        check("skills not installed" not in out, "plugin: no skill reported missing")
        check("loaded twice" in page, "plugin copy without git: a legacy skill link into another clone is a duplicate")
        check("Legacy install.sh links" in page, "plugin copy without git: the legacy CLAUDE.md link is reported")

        # Enabled only in the project's settings, installed at project scope.
        (home / ".claude" / "settings.json").write_text(json.dumps({}))
        (project / ".claude").mkdir()
        (project / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"agent-skills@quocld": True}}))
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"agent-skills@quocld": [{"scope": "project", "projectPath": str(project), "installPath": str(plug)}]}}))
        code, out, page = run(home, project)
        check("from agent-skills@quocld as /agent-skills:worktree-flow" in page, "plugin enabled at project scope is found")
        (project / ".claude" / "settings.local.json").write_text(json.dumps({"enabledPlugins": {"agent-skills@quocld": False}}))
        code, out, page = run(home, project)
        check("agent-skills@quocld enabled" not in page, "plugin turned off in the project's local settings is not counted")

        # migrate-to-plugin.py run from the plugin copy (no git): only links into agent-skills checkouts go.
        other = tmp / "other" / "skills" / "foo"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("x")
        (home / ".claude" / "skills" / "foo").symlink_to(other)
        (home / ".claude" / "agent-skills-hooks").symlink_to(clone / "hooks")
        (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": {"bad": "shape"}}}))
        env = dict(os.environ, HOME=str(home))
        env.pop("CLAUDE_DIR", None)
        m = subprocess.run([sys.executable, str(plug / "migrate-to-plugin.py")], capture_output=True, text=True, env=env)
        check(m.returncode == 0, "migrate: no crash on odd settings")
        check((home / ".claude" / "skills" / "foo").is_symlink(), "migrate: keeps a link into a folder that is not agent-skills")
        check(not (home / ".claude" / "skills" / "root-cause").exists(), "migrate: removes a skill link into another agent-skills clone")
        check(not (home / ".claude" / "CLAUDE.md").exists(), "migrate: removes the CLAUDE.md link")
        check((home / ".claude" / "agent-skills-hooks").is_symlink(), "migrate: never removes agent-skills-hooks")

    # Skill reader: every repo skill's SKILL.md is in the page, rendered safely, and its name opens it everywhere.
    with tempfile.TemporaryDirectory() as tmp:
        home, project = Path(tmp) / "home", Path(tmp) / "project"
        (home / ".claude").mkdir(parents=True)
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        code, out, page = run(home, project)
        repo = HERE.parents[2]
        names = sorted(d.name for d in (repo / "skills").iterdir() if (d / "SKILL.md").exists())
        check(all(f'id="skill-src-{n}"' in page for n in names), f"skill reader: all {len(names)} SKILL.md files are in the page")
        check('data-skill="worktree-flow"' in page and '<g class="skl" data-skill="worktree-flow"' in page,
              "skill reader: names in tables and chips in diagrams open the skill")
        phrase = "Every task gets its own worktree and branch"
        check(phrase in page, "skill reader: a skill's body text is readable in the page")
        check('id="reader"' in page and "openSkill" in page, "skill reader: the reader panel and its script are mounted")
        ids = re.findall(r'\bid="([^"]+)"', page)
        check('class="logo"' in page and 'id="hx-hot"' in page and 'rel="icon"' in page,
              "logo: the README logo (assets/icon.svg) is the header mark and the favicon")
        check(len(ids) == len(set(ids)), "logo: inlining it adds no duplicate id to the page")
        # The reader must not carry data-skill itself, or every click inside it (the close button too) reopens it.
        check("reader.dataset.skill" not in page and 'id="reader" data-skill' not in page, "skill reader: the panel itself is not a skill link")
    sys.path.insert(0, str(HERE))
    try:
        from page import render_markdown
        bad = render_markdown("<script>alert(1)</script> [x](javascript:alert(1)) <img src=x onerror=y>")
        check("<script" not in bad and "<img" not in bad and 'href="javascript' not in bad,
              "skill reader: markdown is escaped before rendering (no script, img or javascript: link)")
    except ImportError:
        check(False, "skill reader: page.render_markdown exists")

    old = shutil.which("python3.9") or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else None)
    if old:
        with tempfile.TemporaryDirectory() as tmp:
            home, project = leaky_machine(Path(tmp))
            code, out, page = run(home, project, python=old)
            check(code == 0 and bool(page), f"runs on {old}")
            check(all(v not in page and v not in out for v in LEAKS.values()), f"no secret value on {old}")
        p = subprocess.run([old, "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True)
        for f in sorted(HERE.glob("*.py")):
            r = subprocess.run([old, "-m", "py_compile", str(f)], capture_output=True, text=True)
            check(r.returncode == 0, f"{f.name} compiles on {old} {p.stdout.strip()}")
    else:
        print("SKIP no python3.9 or /usr/bin/python3 to check old-version syntax")

    print("all passed" if not FAILS else f"{len(FAILS)} FAILED")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
