#!/usr/bin/env python3
"""Regression tests for harness_map.py: no secret value reaches the page or stdout, malformed inputs do not crash,
and the scripts compile on the oldest python3 a fresh Mac ships (3.9). Builds throwaway HOME and project folders;
never touches the real ~/.claude. Usage: python3 test_harness_map.py  (exit 1 on any failure)
"""
import json
import re
import os
import shutil
import socket
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

    # The hephaestus plugin, as Claude Code installs it: a copy with no .git. Legacy links point into another clone.
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
        index = home / ".claude" / "plugins" / "installed_plugins.json"
        user_settings = home / ".claude" / "settings.json"

        def install(*pids, enabled=True):
            index.write_text(json.dumps({"plugins": {pid: [{"scope": "user", "installPath": str(plug)}] for pid in pids}}))
            user_settings.write_text(json.dumps({"enabledPlugins": {pid: enabled for pid in pids}}))

        install("hephaestus@quocld")
        (home / ".claude" / "skills" / "root-cause").symlink_to(clone / "skills" / "root-cause")
        (home / ".claude" / "CLAUDE.md").symlink_to(clone / "AGENTS.md")
        code, out, page = run(home, project)
        check(code == 0 and "registered by hephaestus@quocld" in page, "plugin: gates count as registered by the plugin")
        check("from hephaestus@quocld as /hephaestus:worktree-flow" in page, "plugin: skills count as installed from the plugin")
        check("skills not installed" not in out, "plugin: no skill reported missing")
        check("loaded twice" in page, "plugin copy without git: a legacy skill link into another clone is a duplicate")
        check("Legacy install.sh links" in page, "plugin copy without git: the legacy CLAUDE.md link is reported")
        check("Legacy plugin id" not in page and "Plugin installed twice" not in page, "plugin: the current id is no legacy or duplicate row")

        # The id before the rename is still ours: gates and skills count, no clash, and one core row says how to move.
        install("agent-skills@quocld")
        code, out, page = run(home, project)
        check("registered by agent-skills@quocld" in page and "from agent-skills@quocld as /agent-skills:worktree-flow" in page
              and "skills not installed" not in out, "legacy plugin id: gates and skills still count as installed")
        check(not re.search(r"[a-z]: (name clash|duplicate copy)", page), "legacy plugin id: its skills are ours, not a name clash")
        check("[core] [Attention] Global instructions / Legacy plugin id agent-skills@quocld" in out
              and "/plugin uninstall agent-skills@quocld, then /plugin install hephaestus@quocld" in out,
              "legacy plugin id: a core row with the uninstall and install fix")
        install("agent-skills@quocld", enabled=False)
        code, out, page = run(home, project)
        check("Legacy plugin id agent-skills@quocld" in out and "installed but disabled" in out,
              "legacy plugin id: installed but disabled is still reported")

        # Both ids at once: every gate would run twice.
        install("hephaestus@quocld", "agent-skills@quocld")
        code, out, page = run(home, project)
        check("[core] [Failing] Global instructions / Plugin installed twice: hephaestus@quocld and agent-skills@quocld" in out
              and "fix: /plugin uninstall agent-skills@quocld\n" in out + "\n" and "Legacy plugin id" not in out,
              "both ids: a failing duplicate row whose fix only uninstalls the legacy id")
        check("runs twice: from hephaestus@quocld and from agent-skills@quocld" in page and "from hephaestus@quocld as /hephaestus:" in page,
              "both ids: the gates show as running twice, the current id wins for skills")
        check(out.count("/plugin uninstall agent-skills@quocld") == 1 and "also under Hooks: no-em-dash.py registered" in out
              and "runs twice: from hephaestus@quocld and from agent-skills@quocld" in out,
              "both ids: one to-do, the gate rows fold into it with their shared reason")
        check('<code>/plugin uninstall agent-skills@quocld</code>' in page, "both ids: the copyable command is only the uninstall")

        # The legacy id enabled, the current one installed but disabled: the legacy id is the only live copy.
        index.write_text(json.dumps({"plugins": {p: [{"scope": "user", "installPath": str(plug)}]
                                                 for p in ("hephaestus@quocld", "agent-skills@quocld")}}))
        user_settings.write_text(json.dumps({"enabledPlugins": {"hephaestus@quocld": False, "agent-skills@quocld": True}}))
        code, out, page = run(home, project)
        check("Legacy plugin id agent-skills@quocld" in out and "the only live copy" in out and "Plugin installed twice" not in out
              and "fix: /plugin enable hephaestus@quocld, then /plugin uninstall agent-skills@quocld" in out
              and "enabling it would" not in out, "current id disabled, legacy enabled: enable the current id first, then uninstall")
        check('<code>/plugin enable hephaestus@quocld</code>' in page and '<code>/plugin uninstall agent-skills@quocld</code>' in page,
              "current id disabled, legacy enabled: each command is its own copyable line")

        # Mid-setup: the legacy plugin is uninstalled, the current one runs, the project's committed key is not renamed yet.
        install("hephaestus@quocld")
        (project / ".claude").mkdir()
        (project / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"agent-skills@quocld": True}}))
        code, out, page = run(home, project)
        check("Plugin installed twice" not in out and "runs twice: from" not in page and "Legacy plugin id" not in out
              and "registered by hephaestus@quocld" in page,
              "stale legacy key: no duplicate row and no gate running twice")
        check("Stale enabledPlugins key agent-skills@quocld" in out
              and "fix: in the setup PR/MR, rename the enabledPlugins key agent-skills@quocld to hephaestus@quocld in .claude/settings.json" in out
              and "/plugin uninstall" not in out, "stale legacy key: one row whose only fix is the key rename")
        check('class="hint">in the setup PR/MR, rename' in page and "<code>in the setup" not in page,
              "stale legacy key: the rename is a hint, not a $ command")

        # Nothing installed, the project still enables the legacy id: install the current id, never reinstall the legacy one.
        index.write_text(json.dumps({"plugins": {}}))
        user_settings.write_text(json.dumps({}))
        code, out, page = run(home, project)
        check("claude plugin install agent-skills@quocld" not in out and "/plugin install agent-skills" not in out
              and "Hephaestus plugin (not installed" in out and "fix: /plugin marketplace add quocld/hephaestus-agent-skills, then /plugin install hephaestus@quocld" in out
              and "Stale enabledPlugins key agent-skills@quocld" in out,
              "legacy key only: the fix installs hephaestus@quocld and renames the key")
        (project / ".claude" / "settings.json").unlink()

        # Enabled only in the project's settings, installed at project scope.
        user_settings.write_text(json.dumps({}))
        (project / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"hephaestus@quocld": True}}))
        index.write_text(json.dumps(
            {"plugins": {"hephaestus@quocld": [{"scope": "project", "projectPath": str(project), "installPath": str(plug)}]}}))
        code, out, page = run(home, project)
        check("from hephaestus@quocld as /hephaestus:worktree-flow" in page, "plugin enabled at project scope is found")
        (project / ".claude" / "settings.local.json").write_text(json.dumps({"enabledPlugins": {"hephaestus@quocld": False}}))
        code, out, page = run(home, project)
        check("hephaestus@quocld enabled" not in page, "plugin turned off in the project's local settings is not counted")
        (project / ".claude" / "settings.local.json").unlink()
        # A project that enables the legacy id in its committed settings renames that key in the setup PR/MR.
        (project / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"agent-skills@quocld": True}}))
        index.write_text(json.dumps(
            {"plugins": {"agent-skills@quocld": [{"scope": "project", "projectPath": str(project), "installPath": str(plug)}]}}))
        code, out, page = run(home, project)
        check("registered by agent-skills@quocld" in page and "Legacy plugin id agent-skills@quocld" in out
              and "in the setup PR/MR, rename the enabledPlugins key agent-skills@quocld to hephaestus@quocld in .claude/settings.json" in out,
              "legacy plugin id at project scope: counted, and the fix renames the project's enabledPlugins key in the setup PR/MR")

        # migrate-to-plugin.py run from the plugin copy (no git): only links into checkouts of this repo go.
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
        check((home / ".claude" / "skills" / "foo").is_symlink(), "migrate: keeps a link into a folder that is not this repo")
        check(not (home / ".claude" / "skills" / "root-cause").exists(), "migrate: removes a skill link into another clone of this repo")
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
        # A plain sentence from the skill's own body, so editing that skill's wording does not break this test.
        body = (repo / "skills" / "worktree-flow" / "SKILL.md").read_text().split("---", 2)[-1].splitlines()
        phrase = next((ln.strip()[:40] for ln in body if len(ln.strip()) > 40 and ln.strip()[0].isalpha()
                       and not re.search(r"[`*_\[\]<>&|\"']", ln)), "worktree-flow")
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
        fenced = render_markdown("- Wait for it:\n\n  ```ts\n  const x = 1;\n  ```\n- next")
        check("<pre><code>const x = 1;</code></pre>" in fenced and "```" not in fenced,
              "skill reader: a fenced block inside a list item renders as code, without the item's indent")
    except ImportError:
        check(False, "skill reader: page.render_markdown exists")

    # The public docs site (--docs-only) carries nothing about the machine that built it.
    with tempfile.TemporaryDirectory() as tmp:
        home, project = leaky_machine(Path(tmp))
        site = Path(tmp) / "site"
        env = {k: v for k, v in os.environ.items() if not k.startswith(("JIRA_", "CLAUDE_"))}
        env["HOME"] = str(home)
        p_ = subprocess.run([sys.executable, str(SCRIPT), "--docs-only", str(site)], capture_output=True, text=True, env=env, cwd=project)
        html_ = (site / "index.html").read_text() if (site / "index.html").exists() else ""
        check(p_.returncode == 0 and bool(html_) and (site / "version.json").exists(), "docs site: index.html and version.json are written")
        check(all(v not in html_ for v in LEAKS.values()), "docs site: no secret value from the machine")
        check(str(home) not in html_ and str(project) not in html_ and socket.gethostname().split(".")[0] not in html_,
              "docs site: no home path, project path or host name")
        check("SLACK_TOKEN" not in html_ and "notify.py" not in html_, "docs site: hooks come from the repo's hooks.json, not this machine's settings")
        check('id="wheel"' in html_ and 'data-tab="dash"' not in html_, "docs site: has the harness wheel and no Dashboard tab")

    # An existing harness: a project skill that shares a name with ours is reported, so it can be forked.
    with tempfile.TemporaryDirectory() as tmp:
        home, project = Path(tmp) / "home", Path(tmp) / "project"
        (home / ".claude" / "skills" / "root-cause").mkdir(parents=True)
        (home / ".claude" / "skills" / "root-cause" / "SKILL.md").write_text(
            (HERE.parents[1] / "root-cause" / "SKILL.md").read_text())
        (project / ".claude" / "skills" / "worktree-flow").mkdir(parents=True)
        (project / ".claude" / "skills" / "worktree-flow" / "SKILL.md").write_text("---\nname: worktree-flow\ndescription: ours\n---\nmain only\n")
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        code, out, page = run(home, project)
        check("worktree-flow: name clash" in page and "hx-worktree-flow" in page, "existing harness: a different same-name project skill is a clash, with the fork fix")
        check("root-cause: duplicate copy" in page and "root-cause: name clash" not in page, "existing harness: an identical copy is only a duplicate")
        (project / ".claude" / "skills" / "hx-worktree-flow").mkdir()
        (project / ".claude" / "skills" / "hx-worktree-flow" / "SKILL.md").write_text("---\nname: hx-worktree-flow\ndescription: fork\n---\n")
        code, out, page = run(home, project)
        check("worktree-flow: name clash:" not in out and "worktree-flow: name clash settled" in page,
              "existing harness: theirs kept and ours forked as hx-worktree-flow is settled, not a core gap")

    # A plaintext secret in the global settings is this machine's risk, never the project's need: a machine row per key,
    # whose fix depends on whether this project names the key, and no value anywhere.
    with tempfile.TemporaryDirectory() as tmp:
        home, project = Path(tmp) / "home", Path(tmp) / "shop"
        (home / ".claude").mkdir(parents=True)
        project.mkdir()
        subprocess.run(["git", "init", "-q", str(project)], check=True)
        (project / "pay.js").write_text("const t = process.env.STRIPE_SECRET_KEY;\n")
        subprocess.run(["git", "-C", str(project), "add", "pay.js"], check=True)
        (project / ".env.local.example").write_text("SENTRY_AUTH_TOKEN=\n")   # untracked example files count too
        values = {"SUPABASE_API_KEY": "LeakGlobalSupabase21", "JIRA_API_TOKEN": "LeakGlobalJira22", "SENTRY_AUTH_TOKEN": "LeakGlobalSentry23",
                  "STRIPE_SECRET_KEY": "LeakGlobalStripe24", "API_TOKEN": "LeakGlobalApi25"}
        (home / ".claude" / "settings.json").write_text(json.dumps({"env": values}))
        (home / ".claude" / "settings.json.bak1").write_text(json.dumps({"env": {"SUPABASE_API_KEY": "x"}}))
        # A backup that only holds a longer key name (JIRA_API_TOKEN_OLD contains API_TOKEN) does not hold API_TOKEN.
        (home / ".claude" / "settings.json.bak2").write_text(json.dumps({"env": {"JIRA_API_TOKEN_OLD": "x"}}))
        (home / ".claude" / "settings.json.bak3").write_text("not json, API_TOKEN_V2=x")
        code, out, page = run(home, project)
        check(all(v not in page and v not in out for v in values.values()), "global secrets: no value in the page or stdout")
        line = lambda key: next((ln for ln in out.splitlines() if f"/ Plaintext {key} in ~/.claude/settings.json:" in ln), "")
        supa = line("SUPABASE_API_KEY")
        check(supa.startswith(" ") and "[core] [Failing] This machine (every project) / Plaintext SUPABASE_API_KEY" in supa
              and "Project / Plaintext" not in out and "Settings hygiene" not in page,
              "global secrets: a core row per key in the machine section, never under Project")
        check("loaded into every session of every project" in supa and "this project (shop) does not reference SUPABASE_API_KEY" in supa
              and "also in the backup settings.json.bak1" in supa, "global secrets: says every project loads it, that this project does not use it, and the backup")
        fix = lambda key: out.split(line(key), 1)[1].splitlines()[1] if line(key) else ""
        check("remove SUPABASE_API_KEY from ~/.claude/settings.json (it is exposed to every project) and rotate it; "
              "if another project needs it, put it in that project's .agents/secrets.env or an op:// reference" in fix("SUPABASE_API_KEY"),
              "global secrets: a key this project does not reference is removed and rotated")
        check("references it in pay.js" in line("STRIPE_SECRET_KEY")
              and "move STRIPE_SECRET_KEY from ~/.claude/settings.json to this project's .agents/secrets.env (or an op:// reference) and rotate it"
              in fix("STRIPE_SECRET_KEY"), "global secrets: a key a tracked file references moves to this project's secrets.env")
        api = line("API_TOKEN")
        check(api and "also in the backup" not in api and "delete the backups" not in fix("API_TOKEN"),
              "global secrets: a backup holding only a longer key name (or a non-JSON one with API_TOKEN_V2) does not hold API_TOKEN")
        jira = line("JIRA_API_TOKEN")
        check("bug-triage and jira-bug-hunter read JIRA_* for the Jira REST API" in jira and "remove JIRA_API_TOKEN" not in fix("JIRA_API_TOKEN")
              and "into your shell profile as a keychain or 1Password lookup" in fix("JIRA_API_TOKEN")
              and "or use the Atlassian MCP instead" in fix("JIRA_API_TOKEN"),
              "global secrets: a JIRA_* key keeps a working Jira path (shell environment via keychain, or the MCP), never just remove")
        check("JIRA_* variables set; skills use the REST API (no MCP); they come from the env block of ~/.claude/settings.json in plaintext" in page,
              "global secrets: the Jira access row says it relies on the plaintext global key")
        check("references it in .env.local.example" in line("SENTRY_AUTH_TOKEN") and "move SENTRY_AUTH_TOKEN" in fix("SENTRY_AUTH_TOKEN"),
              "global secrets: a key in an untracked .env*.example counts as referenced")
        check('id="this-machine-every-project"' in page and ">This machine (every project)</h2>" in page,
              "global secrets: the page groups them under This machine (every project)")

    # The onboarding prompt has one source (assets/onboard-prompt.md); the README and the docs site carry it verbatim.
    # It stays one line that points at the install guide, which the docs site publishes as is.
    prompt = (HERE.parent / "assets" / "onboard-prompt.md").read_text().strip()
    readme = (HERE.parents[2] / "README.md").read_text()
    check(prompt in readme and "## Onboard your agent" not in readme
          and readme.index("## Install") < readme.index(prompt) < readme.index("<summary><b>Or install by hand</b>") < readme.index("### Update"),
          "onboard prompt: the README leads Install with it, the manual install is a folded alternative")
    with tempfile.TemporaryDirectory() as tmp:
        p_ = subprocess.run([sys.executable, str(SCRIPT), "--docs-only", tmp], capture_output=True, text=True)
        site = (Path(tmp) / "index.html").read_text() if (Path(tmp) / "index.html").exists() else ""
        import html as _html
        skill_page = (Path(tmp) / "skills" / "root-cause" / "index.html").read_text()
        guide = (HERE.parent / "assets" / "install-guide.md").read_text()
        check(len(prompt.splitlines()) == 1 and "https://hephaestus-skills-docs.vercel.app/install.md" in prompt,
              "onboard prompt: one line pointing at the published install guide")
        check((Path(tmp) / "install.md").exists() and (Path(tmp) / "install.md").read_text() == guide
              and "hx-&lt;name&gt;" in (Path(tmp) / "install" / "index.html").read_text(),
              "install guide: the docs site serves it raw at install.md and as a page at install/")
        check('data-open="onboard-src"' in site and 'id="onboard-src"' in site and _html.escape(prompt, quote=True) in site
              and 'data-open="onboard-src"' in skill_page, "onboard prompt: a header button on every docs page opens it")

    # Every page of the public site is indexable, credits the author, links back to the repo, and reaches the license,
    # policy and contributing pages; no internal link is broken.
    with tempfile.TemporaryDirectory() as tmp:
        url = "https://docs.example.test"
        p_ = subprocess.run([sys.executable, str(SCRIPT), "--docs-only", tmp, "--site-url", url], capture_output=True, text=True)
        site = Path(tmp)
        locs = re.findall(r"<loc>([^<]+)</loc>", (site / "sitemap.xml").read_text()) if (site / "sitemap.xml").exists() else []
        pages = {u: site / u[len(url) + 1:] / "index.html" for u in locs}
        check(p_.returncode == 0 and bool(locs) and all(f.exists() for f in pages.values()), "docs site: every sitemap URL is a page")
        repo_slugs = ("license", "privacy", "terms", "contributing", "code-of-conduct", "about", "install")
        check(all(f"{url}/{s}/" in locs for s in repo_slugs) and sum("/skills/" in u for u in locs) == len(list((HERE.parents[1]).glob("*/SKILL.md"))),
              "docs site: the sitemap lists the license, policy, contributing, about and install pages and every skill")
        bad_seo, bad_links, internal = [], [], set()
        for u, f in pages.items():
            h = f.read_text()
            ld_ = re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)
            graph = json.loads(ld_.group(1)).get("@graph", []) if ld_ else []
            ok = (f'<link rel="canonical" href="{u}">' in h and '<meta name="description"' in h and '<meta name="author" content="Ryan Le">' in h
                  and bool(graph) and graph[0].get("author", {}).get("url") == "https://github.com/quocld"
                  and (u == f"{url}/" or any(g.get("@type") == "BreadcrumbList" for g in graph)))
            if not ok:
                bad_seo.append(u)
            if not all(f'href="/{s}/"' in h for s in ("license", "privacy", "terms", "contributing", "code-of-conduct", "about")) \
                    or 'href="https://github.com/quocld/hephaestus-agent-skills"' not in h or 'class="btn ghost ghlink"' not in h:
                bad_links.append(u)
            internal |= set(re.findall(r'href="(/[^"#?]*)', h))
        check(not bad_seo, f"docs site: every page has canonical, description, author and JSON-LD with breadcrumbs ({bad_seo[:3]})")
        check(not bad_links, f"docs site: every page has the GitHub header link and the footer links ({bad_links[:3]})")
        broken = sorted(i for i in internal if not ((site / i.lstrip("/") / "index.html").exists() or (site / i.lstrip("/")).is_file()))
        check(not broken, f"docs site: every internal link resolves to a page or file ({broken[:5]})")
        skill_html = (site / "skills" / "root-cause" / "index.html").read_text()
        check("https://github.com/quocld/hephaestus-agent-skills/tree/main/skills/root-cause" in skill_html,
              "docs site: a skill page links to its source on GitHub")
        lic = (site / "license" / "index.html").read_text()
        check("MIT License" in lic and "Permission is hereby granted" in lic and "Third-party sources" in lic,
              "docs site: the license page renders LICENSE and the third-party sources")
        contrib = (site / "contributing" / "index.html").read_text()
        check('href="/code-of-conduct/"' in contrib and "](" not in contrib and "site.invalid" not in contrib,
              "docs site: repo-relative Markdown links become site links")
        nf = (site / "404.html").read_text() if (site / "404.html").exists() else ""
        check('content="noindex"' in nf and f"{url}/404" not in " ".join(locs), "docs site: 404.html exists, noindex and out of the sitemap")
    check((HERE.parents[2] / "LICENSE").read_text().startswith("MIT License"), "repo: LICENSE is the MIT License")
    # The integration branch is the user's recorded answer: never dev or the remote default by assumption.
    import harness_map as hm
    with tempfile.TemporaryDirectory() as tmp:
        origin, project = Path(tmp) / "origin.git", Path(tmp) / "project"
        git = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True,
                                        env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        git("init", "-q", "--bare", "-b", "main", str(origin))
        git("clone", "-q", str(origin), str(project))
        git("-C", str(project), "commit", "-q", "--allow-empty", "-m", "init")
        git("-C", str(project), "push", "-q", "origin", "HEAD:main", "HEAD:dev")
        git("-C", str(project), "fetch", "-q", "origin")
        row = lambda reg: hm.integration_check(project, reg)
        r = row(None)
        check(r["status"] == "missing" and "not recorded" in r["detail"] and "likely dev" in r["detail"],
              "integration branch: no registry is missing, never ok by assuming dev, and shows dev as the likely answer")
        r = row({"project": "x", "environments": {"dev": {"policy": "autonomous", "branch": "dev", "services": []}}})
        check(r["status"] == "missing" and "legacy" in r["detail"] and "integrationBranch" in r["fix"],
              "integration branch: the legacy dev environment branch is missing until integrationBranch is recorded")
        r = row({"project": "x", "integrationBranch": "main", "environments": {"dev": {"policy": "autonomous", "branch": "dev", "services": []}}})
        check(r["status"] == "ok" and r["detail"].startswith("main, recorded as integrationBranch"),
              "integration branch: a recorded integrationBranch wins and is ok")
        r = row({"project": "x", "integrationBranch": "nope", "environments": {}})
        check(r["status"] == "missing" and "origin/nope not found" in r["detail"], "integration branch: a recorded branch origin lacks is missing")
        check(hm.integration_branch({"integrationBranch": "  "}) == (None, "invalid"), "integration branch: a blank integrationBranch is invalid, not a branch")
        git("-C", str(project), "push", "-q", "origin", "--delete", "dev")
        git("-C", str(project), "fetch", "-q", "--prune", "origin")
        git("-C", str(project), "remote", "set-head", "origin", "main")
        check("likely main" in row(None)["detail"], "integration branch: without origin/dev the guess is the remote default branch")
        (project / ".agents").mkdir()
        (project / ".agents" / "environments.json").write_text(json.dumps({"project": "x", "integrationBranch": "main", "environments": {}}))
        check(hm.integration_branch({"integrationBranch": 123})[1] == "invalid" and row({"integrationBranch": 123})["status"] == "fail",
              "integration branch: a non-string integrationBranch is invalid, never used as a branch name")
        banner = hm.integration_banner(project, None)
        check('<span class="ibb none" title="likely answer, not recorded">main?</span>' in banner and banner.count("ot recorded<") == 1,
              "integration banner: nothing recorded shows the drafted guess in the box, not the pill's words again")
        for bad in ("[1, 2]", '"str"'):
            (project / ".agents").mkdir(exist_ok=True)
            (project / ".agents" / "environments.json").write_text(bad)
            rows, _ = hm.collect_project(project)
            check(next(c for c in rows if c["title"] == "Environment registry")["status"] == "fail",
                  f"a registry whose top level is {bad} is an invalid-shape fail row, not a crash")
        (project / ".agents" / "environments.json").write_text(json.dumps({"project": "x", "integrationBranch": "main", "environments": {}}))
        rows, _ = hm.collect_project(project)
        reg_row = next(c for c in rows if c["title"] == "Environment registry")
        check(reg_row["status"] == "missing" and "environments skill" in reg_row["fix"],
              "a registry holding only integrationBranch is a missing environment list, not an invalid registry")
        check(next(c for c in rows if c["title"] == "Integration branch")["status"] == "ok", "collect_project mounts the integration branch row")
    # Environments: an empty secrets.env line is still missing, and the env panel shows a checklist per environment.
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "project"
        git = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True,
                                        env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))
        git("init", "-q", str(project))
        git("-C", str(project), "commit", "-q", "--allow-empty", "-m", "init")
        (project / ".agents").mkdir()
        names = ["HMT_FILLED", "HMT_EMPTY", "HMT_QUOTED", "HMT_EXPORTED", "HMT_COMMENT", "HMT_ABSENT"]
        for n in names:
            os.environ.pop(n, None)
        (project / ".agents" / "secrets.env").write_text(
            "HMT_FILLED=LeakSecretsFile6\nHMT_EMPTY=\nHMT_QUOTED=\"\"\nexport HMT_EXPORTED=''\nHMT_COMMENT= # fill me\n# HMT_ABSENT=x\n")
        shellish = Path(tmp) / "shellish"
        (shellish / ".agents").mkdir(parents=True)
        (shellish / ".agents" / "secrets.env").write_text('A=\nB=""\nC="" # fill me\nD=#hashstart\nE= # fill me\nF=real\nG="x y"\n')
        sh = hm.secret_names(shellish)
        check(sh == {"A": False, "B": False, "C": False, "D": True, "E": False, "F": True, "G": True},
              "secrets.env: set or empty as the shell sources it (\"\" # comment is empty, an unquoted #value is set)")
        known = hm.secret_names(project)
        check(known.get("HMT_FILLED") is True and not any(known.get(n) for n in names[1:]),
              "secrets.env: only a filled name counts as set; NAME=, \"\", export '', and a trailing comment are empty")
        state = lambda n: hm.secret_state({"secret": "env:" + n}, known)[1]
        check(state("HMT_FILLED") == "ok" and all(state(n) == "missing" for n in names[1:]),
              "secret_state: an empty secrets.env value is missing, not ok")
        reg = {"project": "x", "integrationBranch": "main", "defaultEnvironment": "staging", "environments": {
            "staging": {"policy": "confirm-writes", "url": "https://s.test", "branch": "staging",
                        "services": [{"name": "web", "type": "vercel", "deploy": ["d"], "verify": ["v"], "rollback": ["r"], "version": "x"}],
                        "accounts": [{"role": "admin", "login": "a@x.test", "password": {"secret": "env:HMT_EMPTY"}},
                                     {"role": "member", "login": "m@x.test", "password": {"secret": "env:HMT_FILLED"}}]},
            "production": {"policy": "confirm-writes", "services": [{"name": "web", "type": "vps", "deploy": ["d"]}]}}}
        rows = {c["title"]: c for c in hm.env_checks(reg, project)}
        for c in rows.values():
            c["tier"] = hm.tier_of(c)
        sec = rows.get("staging: secrets", {})
        check(sec.get("status") == "missing" and "empty in .agents/secrets.env: env:HMT_EMPTY" in sec.get("detail", "")
              and "HMT_FILLED" not in sec.get("detail", ""), "env checks: an empty secret is a missing row naming it as empty")
        check(rows.get("production: policy", {}).get("tier") == "core" and rows["production: policy"]["status"] == "fail",
              "env checks: a prod environment without confirm-each-step stays a core failure")
        check(all(rows.get(t, {}).get("tier") == "optional" and rows[t]["status"] == "missing"
                  for t in ("staging: secrets", "production: URL", "production: branch", "production: test accounts", "production: commands")),
              "env checks: other environment gaps are optional missing rows")
        check("verify" in rows.get("production: commands", {}).get("detail", "") and "rollback" in rows["production: commands"]["detail"],
              "env checks: the commands row names the missing commands")
        std = rows.get("Standard environments", {})
        check(std.get("status") == "missing" and std.get("detail", "").startswith("not in the registry: dev") and "staging" not in std["detail"],
              "env checks: a standard environment absent from the registry is a row; production fills the prod slot")
        ik = lambda n: {"secret": "env:" + n}
        ireg = {"project": "x", "integrationBranch": "main", "defaultEnvironment": "staging", "environments": {
            "staging": {"policy": "confirm-writes", "branch": "staging", "services": [],
                        "integrations": [{"name": "stripe", "mode": "live", "key": ik("K_SHARED")}, {"name": "brevo", "mode": "test", "key": ik("K_B")}]},
            "prod": {"policy": "confirm-each-step", "branch": "main", "services": [],
                     "integrations": [{"name": "stripe", "mode": "live", "key": ik("K_SHARED")}]}}}
        irows = {c["title"]: c for c in hm.env_checks(ireg, project)}
        sd, pd = irows.get("staging: service keys", {}).get("detail", ""), irows.get("prod: service keys", {}).get("detail", "")
        check("stripe uses a live key outside prod" in sd and "stripe key env:K_SHARED is shared with prod" in sd
              and "service brevo has no key for environment prod" in pd and "uses a live key" not in pd,
              "env checks: a live key outside prod, a shared key and a service with no key in an environment are warnings")
        ireg["environments"]["staging"]["integrations"] = [{"name": "stripe", "mode": "test", "key": ik("K_S")}]
        ireg["environments"]["prod"]["integrations"] = [{"name": "stripe", "mode": "live", "key": ik("K_P")}]
        check("staging: service keys" not in {c["title"] for c in hm.env_checks(ireg, project)},
              "env checks: separate test and live keys raise no service-key warning")
        panel = hm.env_panel(project, reg)
        check('class="ib"' in panel and '<code class="ibb">main</code>' in panel, "env panel: the integration branch is shown")
        check('data-slot="dev"' in panel and 'data-slot="prod"' not in panel and 'data-slot="staging"' not in panel,
              "env panel: a ghost card only for a standard environment not in the registry")
        check(re.search(r'data-s="missing"><svg[^>]*>.*?</svg><span class="cn mono">env:HMT_EMPTY</span>', panel) is not None
              and re.search(r'data-s="ok"><svg[^>]*>.*?</svg><span class="cn mono">env:HMT_FILLED</span>', panel) is not None,
              "env panel: each secret reference is a checklist row marked set or missing")
        check("LeakSecretsFile6" not in panel, "env panel: no secret value")
        bare = hm.env_panel(project, {"project": "x", "environments": {}})
        check(all(f'data-slot="{s}"' in bare for s in ("dev", "staging", "prod")) and ">Not recorded</span>" in bare,
              "env panel: no environment yet shows dev, staging and prod ghost cards and an unrecorded integration branch")
        # A worktree without its own secrets.env reads the main checkout's (worktree-flow links it from there).
        git("-C", str(project), "worktree", "add", "-q", str(Path(tmp) / "wt"))
        check(hm.secret_names(Path(tmp) / "wt").get("HMT_FILLED") is True, "secrets.env: a worktree falls back to the main checkout's file")
        (Path(tmp) / "home").mkdir()
        page = run(Path(tmp) / "home", project)[2]
        check('id="envs"' in page and 'class="ib"' in page and 'class="cl"' in page, "the page mounts the env panel with the checklist")

    # One definition of prod for the slot and the policy rule; settled and smoke-only environments add no noise.
    local = {"local": {"branch": "main", "policy": "autonomous", "url": "http://localhost:3000", "testing": {"scope": "full"},
                       "services": [{"name": "web", "type": "local", "deploy": ["d"], "verify": ["v"]}], "accounts": [{"role": "a", "login": "a"}]}}
    lrows = {c["title"]: c for c in hm.env_checks({"integrationBranch": "main", "environments": local}, None)}
    check("local: policy" not in lrows and hm.standard_slots(hm.env_map({"environments": local}))["dev"] == "local",
          "env checks: a local environment on main fills the dev slot and is not prod")
    docs = {"docs": {"branch": "main", "policy": "confirm-writes", "url": "https://d.test", "testing": {"scope": "smoke-only"},
                     "services": [{"name": "site", "type": "vercel", "deploy": ["d"], "verify": ["v"], "rollback": ["r"], "version": "v"}]}}
    reg = {"integrationBranch": "main", "absentEnvironments": ["dev", "staging"], "environments": docs}
    drows = {c["title"]: c for c in hm.env_checks(reg, None)}
    check(hm.standard_slots(hm.env_map(reg))["prod"] == "docs" and drows.get("docs: policy", {}).get("status") == "fail",
          "env checks: an environment on main that is_prod picks also fills the prod slot")
    check("Standard environments" not in drows and "docs: test accounts" not in drows,
          "env checks: absentEnvironments settles a slot, and smoke-only testing does not require test accounts")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True)
        panel = hm.env_panel(tmp, reg)
        check(panel.count("Not in registry") == 0 and panel.count("Not used") == 2 and "ghost quiet" in panel,
              "env panel: a settled standard environment is a quiet 'not used' card, not a ghost asking for it")
    items = [hm.item("a", "A", "ok"), hm.item("b", "B", "missing"), hm.item("c", "C", "fail"), hm.item("d", "D", "missing")]
    check(">1 missing, 1 wrong<" not in hm.progress(items) and ">2 missing, 1 wrong<" in hm.progress(items),
          "env progress: missing and wrong items are counted apart")
    tpl = (HERE.parent / "assets" / "template.html").read_text()
    check(".todo li{counter-increment:t;display:grid;grid-template-columns:28px minmax(0,1fr)" in tpl,
          "template: the Fix first rows can shrink, so a long fix command scrolls instead of being clipped")
    check(".row{display:grid;grid-template-columns:104px 260px minmax(0,1fr);" in tpl and ".row{grid-template-columns:minmax(0,1fr);" in tpl
          and ".fix code{flex:1;min-width:0;" in tpl,
          "template: a section row's detail column can shrink, so a long fix scrolls inside its box and Copy stays visible")
    fx = hm.fix_html("/plugin enable a@b, then /plugin uninstall c@d; in the setup PR/MR, rename the key")
    check(fx.count('<div class="fix"><code>') == 2 and "<code>/plugin enable a@b</code>" in fx and "<code>/plugin uninstall c@d</code>" in fx
          and '<div class="hint">in the setup PR/MR, rename the key</div>' in fx,
          "fix_html: each command is its own copyable line and prose after '; ' is a hint, never inside the $ block")
    with tempfile.TemporaryDirectory() as tmp:
        bak = Path(tmp) / "b"
        bak.write_text(json.dumps({"env": {"API_TOKEN": "x"}, "mcpServers": {"s": {"env": {"MCP_TOKEN": "x"}}}}))
        check(hm.backup_holds(bak, "API_TOKEN") and not hm.backup_holds(bak, "MCP_TOKEN") and hm.backup_holds(bak, "MCP_TOKEN", mcp=True)
              and not hm.backup_holds(bak, "API_TOKEN", mcp=True), "backup_holds: settings keys in env, MCP keys only in mcpServers.*.env")
    check(hm.fix_html("remove X from y; rotate it") == '<div class="hint">remove X from y; rotate it</div>', "fix_html: a prose fix stays one hint")
    check(re.search(r"\.card>\.hd h2\{[^}]*white-space:nowrap;flex-shrink:0", tpl) is not None
          and re.search(r"\.card>\.hd \.desc\{[^}]*min-width:0", tpl) is not None,
          "template: a card title never wraps (the long description shrinks instead), at every width")

    prompt_text = hm.setup_prompt()
    check("which branch PRs go into" in prompt_text and "never assume dev or main" in prompt_text and "staging, prod" in prompt_text,
          "setup prompt: always asks the integration branch and which environments exist")
    check("one message" in prompt_text and "one step at a time" not in prompt_text and "once for that step" not in prompt_text
          and "core 100%" in prompt_text and "waiting on you" in prompt_text.lower() and "stop after the report" in prompt_text,
          "setup prompt: one question batch up front, no stop after the report, done only at core 100% plus a waiting-on-you list")

    # Project files that project-init already wrote, in its open PR or already merged on origin, are not reported missing;
    # a branch alone, with no PR/MR that gh confirms, does not hide the gap.
    def gitrepo(tmp):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        git = lambda *a: subprocess.run(["git", *a], check=True, capture_output=True, env=env)
        origin, project = Path(tmp) / "origin.git", Path(tmp) / "project"
        git("init", "-q", "--bare", "-b", "main", str(origin))
        git("clone", "-q", str(origin), str(project))
        git("-C", str(project), "commit", "-q", "--allow-empty", "-m", "init")
        git("-C", str(project), "push", "-q", "origin", "HEAD:main")
        git("-C", str(project), "remote", "set-head", "origin", "main")
        return git, project

    def setup_branch(git, project, branch, registry_text, base="main"):
        """project-init's branch: AGENTS.md with the block, the registry, .gitignore; pushed, then back on base."""
        git("-C", str(project), "switch", "-q", "-c", branch)
        (project / "AGENTS.md").write_text("# P\n<!-- project-init:start -->\n- Tracker: none\n<!-- project-init:end -->\n")
        (project / ".agents").mkdir(exist_ok=True)
        (project / ".agents" / "environments.json").write_text(registry_text)
        (project / ".gitignore").write_text(".agents/secrets.env\n")
        git("-C", str(project), "add", "-A")
        git("-C", str(project), "commit", "-q", "-m", "project-init")
        git("-C", str(project), "push", "-q", "origin", branch)
        git("-C", str(project), "switch", "-q", base)

    def with_gh(bin_, prs, fn):
        """Run fn() with a fake gh on PATH whose `pr list` prints prs."""
        bin_.mkdir(exist_ok=True)
        (bin_ / "gh").write_text("#!/bin/sh\n[ \"$1 $2\" = \"pr list\" ] || exit 1\necho '" + json.dumps(prs) + "'\n")
        (bin_ / "gh").chmod(0o755)
        saved = os.environ["PATH"]
        os.environ["PATH"] = str(bin_) + os.pathsep + saved
        try:
            return fn()
        finally:
            os.environ["PATH"] = saved

    reg_text = json.dumps({"project": "p", "integrationBranch": "main",
                           "environments": {"staging": {"branch": "main", "policy": "confirm-writes", "url": "https://s.test"}}})
    pr42 = [{"number": 42, "url": "https://example.test/pr/42", "headRefName": "chore/project-init",
             "files": [{"path": "AGENTS.md"}, {"path": ".agents/environments.json"}, {"path": ".gitignore"},
                       {"path": ".claude/skills/hx-flow-trace/SKILL.md"}]}]
    project_titles = ("Project AGENTS.md", "Environment registry")
    with tempfile.TemporaryDirectory() as tmp:
        git, project = gitrepo(tmp)
        bin_ = Path(tmp) / "bin"
        rows = lambda probe=False: {c["title"]: c for c in hm.collect_project(project, probe)[0]}
        bare = rows()
        a = bare.get("Project AGENTS.md", {})
        check(a.get("status") == "missing" and "project facts from project-init; the plugin's global rules load separately" in a.get("detail", "")
              and "no project AGENTS.md" not in a.get("detail", ""),
              "AGENTS.md row: says it holds the project facts and that the plugin's global rules load separately")
        setup_branch(git, project, "chore/project-init", reg_text)
        nogh = rows()
        check(all(nogh[t]["status"] == "missing" and "branch origin/chore/project-init has it" in nogh[t]["detail"] for t in project_titles)
              and nogh["Integration branch"]["status"] == "missing",
              "branch without a PR/MR gh confirms (no gh): the rows stay gaps in Fix first, with the branch as a hint")
        empty = with_gh(bin_, [], lambda: rows(probe=True))
        check(all(empty[t]["status"] == "missing" for t in project_titles), "gh lists no PR for that branch: the rows stay missing")
        gh = with_gh(bin_, pr42, lambda: rows(probe=True))
        check(all(gh[t]["status"] == "pending" and "PR #42" in gh[t]["detail"] and "merge it to finish" in gh[t]["detail"] for t in project_titles),
              "open PR seen by gh: AGENTS.md and the registry are pending with the PR number")
        check(gh["Integration branch"]["status"] == "pending" and gh["Integration branch"]["detail"].startswith("main, recorded in PR #42"),
              "pending registry: the integration row names the recorded branch and the PR")
        banner = hm.integration_banner(project, None, gh["Integration branch"])
        check('data-s="pending"' in banner and "Pending merge" in banner and '<code class="ibb">main</code>' in banner
              and 'aria-label="waiting on merge"' in banner,
              "pending registry: the integration banner agrees with the row, shows the branch and announces waiting on merge")
        checks_ = list(gh.values())
        for c in checks_:
            c["tier"] = hm.tier_of(c)
        check(not any(c["status"] == "pending" for c in hm.group_actions(checks_)), "pending rows are not Fix first gaps")
        check(hm.readiness([hm.check("Project", "a", "ok"), hm.check("Project", "b", "pending")]) == 50,
              "readiness: a pending row counts as not done")
        tb_rows = [hm.check("Project", "a", "ok"), hm.check("Project", "b", "pending")]
        for c in tb_rows:
            c["tier"] = "core"
        tb = hm.tier_block("core", tb_rows, {"Project": tb_rows}, [])
        check("All set" not in tb and "1 waiting on merge" in tb and 'class="pending"' in tb,
              "tier panel: a pending row shows waiting on merge with its own bar segment, never All set below 100%")

        # The project kept its own flow-trace: ours forked as hx-flow-trace settles the clash, wherever the fork is.
        saved_claude = hm.CLAUDE
        hm.CLAUDE = Path(tmp) / "home" / ".claude"
        try:
            theirs = project / ".claude" / "skills" / "flow-trace"
            theirs.mkdir(parents=True)
            (theirs / "SKILL.md").write_text("---\nname: flow-trace\ndescription: theirs\n---\nother text\n")
            git("-C", str(project), "add", ".claude")
            git("-C", str(project), "commit", "-q", "-m", "their skill")
            git("-C", str(project), "push", "-q", "origin", "HEAD:main")
            clash = lambda probe=False: {c["title"]: c for c in hm.collect_skills(project, hm.Refs(project, probe))[0]
                                         if c["title"].startswith("flow-trace: ")}
            check(clash().get("flow-trace: name clash", {}).get("status") == "warn", "clash: a different project skill with our name is a warn")
            git("-C", str(project), "switch", "-q", "chore/project-init")
            (project / ".claude" / "skills" / "hx-flow-trace").mkdir(parents=True)
            (project / ".claude" / "skills" / "hx-flow-trace" / "SKILL.md").write_text("fork\n")
            git("-C", str(project), "add", ".claude")
            git("-C", str(project), "commit", "-q", "-m", "fork")
            git("-C", str(project), "push", "-q", "origin", "chore/project-init")
            git("-C", str(project), "switch", "-q", "main")
            in_pr = with_gh(bin_, pr42, lambda: clash(probe=True))
            check(in_pr.get("flow-trace: name clash settled", {}).get("status") == "pending" and "PR #42" in in_pr["flow-trace: name clash settled"]["detail"],
                  "clash: the hx- fork in the open setup PR is pending, not a core warn")
            (project / ".claude" / "skills" / "hx-flow-trace").mkdir(parents=True)
            (project / ".claude" / "skills" / "hx-flow-trace" / "SKILL.md").write_text("fork\n")
            here = clash()
            check("flow-trace: name clash" not in here and here.get("flow-trace: name clash settled", {}).get("status") == "info",
                  "clash: ours forked as hx-flow-trace next to theirs is the user's recorded choice, not a core gap")
            shutil.rmtree(project / ".claude" / "skills" / "hx-flow-trace")
            git("-C", str(project), "switch", "-q", "-c", "chore/switch")
            git("-C", str(project), "rm", "-q", "-r", ".claude/skills/flow-trace")
            git("-C", str(project), "commit", "-q", "-m", "switch to theirs")
            git("-C", str(project), "push", "-q", "origin", "HEAD:main")
            git("-C", str(project), "switch", "-q", "main")
            git("-C", str(project), "fetch", "-q", "origin")
            sw = clash()
            check(sw.get("flow-trace: name clash settled", {}).get("status") == "info" and "pull to get it" in sw["flow-trace: name clash settled"]["detail"],
                  "clash: the project's copy deleted on origin/main (switch to ours) says pull to get it")
        finally:
            hm.CLAUDE = saved_claude

        git("-C", str(project), "push", "-q", "-f", "origin", "chore/project-init:main")
        git("-C", str(project), "fetch", "-q", "origin")
        merged = rows()
        check(all(merged[t]["status"] == "info" and "on origin/main, pull to get it" in merged[t]["detail"] for t in project_titles),
              "merged but not pulled: AGENTS.md and the registry say on origin/main, pull to get it")
        check(merged["Integration branch"]["status"] == "ok" and "Secrets gitignored" not in merged,
              "merged but not pulled: the registry is read as origin/main has it")

    # Mid-setup: the legacy plugin is uninstalled and the enabledPlugins key rename sits in the open setup PR. The stale
    # key row is pending (merge it), not a gap, and nothing says the gates run twice.
    with tempfile.TemporaryDirectory() as tmp:
        git, project = gitrepo(tmp)
        bin_ = Path(tmp) / "bin"
        settings_rel = project / ".claude" / "settings.json"
        settings_rel.parent.mkdir()
        settings_rel.write_text(json.dumps({"enabledPlugins": {"agent-skills@quocld": True}}))
        git("-C", str(project), "add", ".claude")
        git("-C", str(project), "commit", "-q", "-m", "old key")
        git("-C", str(project), "push", "-q", "origin", "HEAD:main")
        git("-C", str(project), "switch", "-q", "-c", "chore/setup")
        settings_rel.write_text(json.dumps({"enabledPlugins": {"hephaestus@quocld": True}}))
        git("-C", str(project), "commit", "-q", "-am", "rename key")
        git("-C", str(project), "push", "-q", "origin", "chore/setup")
        git("-C", str(project), "switch", "-q", "main")
        home_claude = Path(tmp) / "home" / ".claude"
        (home_claude / "plugins").mkdir(parents=True)
        (home_claude / "plugins" / "installed_plugins.json").write_text(json.dumps(
            {"plugins": {"hephaestus@quocld": [{"scope": "user", "installPath": str(HERE.parents[2])}]}}))
        (home_claude / "settings.json").write_text(json.dumps({"enabledPlugins": {"hephaestus@quocld": True}}))
        saved_claude = hm.CLAUDE
        hm.CLAUDE = home_claude
        try:
            hm.set_plugin(project)
            stale = lambda probe=False: next((c for c in hm.collect_global(project, hm.Refs(project, probe))
                                              if c["title"] == "Stale enabledPlugins key agent-skills@quocld"), {})
            check(hm.PLUGIN_ID == "hephaestus@quocld" and stale().get("status") == "warn",
                  "stale legacy key without a PR gh confirms: a warn row, the current id runs")
            pr = [{"number": 7, "url": "https://example.test/pr/7", "headRefName": "chore/setup", "files": [{"path": ".claude/settings.json"}]}]
            in_pr = with_gh(bin_, pr, lambda: stale(probe=True))
            check(in_pr.get("status") == "pending" and "PR #7" in in_pr.get("detail", ""),
                  "stale legacy key renamed in the open setup PR: pending, not a gap")
            check(not any("runs twice" in c["detail"] for c in hm.collect_hooks(False, project)),
                  "stale legacy key: no gate counted as running twice")
        finally:
            hm.CLAUDE = saved_claude
            hm.set_plugin(None)

    # The merge target is not guessed from the missing registry: a stale origin/dev, or no origin/HEAD at all, still
    # finds the copy merged on origin/main, with gh and without.
    for case in ("stale dev", "no origin/HEAD"):
        with tempfile.TemporaryDirectory() as tmp:
            git, project = gitrepo(tmp)
            if case == "stale dev":
                git("-C", str(project), "push", "-q", "origin", "HEAD:dev")
            setup_branch(git, project, "chore/project-init", reg_text)
            git("-C", str(project), "push", "-q", "origin", "chore/project-init:main")
            git("-C", str(project), "push", "-q", "origin", "--delete", "chore/project-init")
            git("-C", str(project), "fetch", "-q", "--prune", "origin")
            if case == "no origin/HEAD":
                git("-C", str(project), "remote", "set-head", "origin", "--delete")
            for label, got in (("no gh", lambda: hm.collect_project(project, False)[0]),
                               ("gh, no PRs", lambda: with_gh(Path(tmp) / "bin", [], lambda: hm.collect_project(project, True)[0]))):
                r = {c["title"]: c for c in got()}
                check(all(r[t]["status"] == "info" and "on origin/main, pull to get it" in r[t]["detail"] for t in project_titles)
                      and r["Integration branch"]["status"] == "ok",
                      f"{case}, {label}: the copy merged on origin/main says pull to get it, and its integration branch is used")

    # A registry merged on origin that is not valid JSON is a fail row, not a reassuring "pull to get it".
    with tempfile.TemporaryDirectory() as tmp:
        git, project = gitrepo(tmp)
        setup_branch(git, project, "chore/project-init", "{bad")
        git("-C", str(project), "push", "-q", "origin", "chore/project-init:main")
        git("-C", str(project), "fetch", "-q", "origin")
        r = {c["title"]: c for c in hm.collect_project(project, False)[0]}
        check(r["Environment registry"]["status"] == "fail" and "not valid JSON" in r["Environment registry"]["detail"]
              and "origin/main" in r["Environment registry"]["detail"],
              "malformed registry on origin: a fail row naming origin/main, not info")
    tpl = (HERE.parent / "assets" / "template.html").read_text()
    check(".pill.pending{" in tpl and ".dot.pending{" in tpl and ".mk.pending{" in tpl and ".tbar i.pending{" in tpl
          and hm.LABEL.get("pending") == "Pending", "pending status: the page styles its pill, dot, mark and bar segment")
    check("and stop" not in hm.setup_prompt() and "install.md" in hm.setup_prompt(),
          "setup prompt: a missing skill sends the agent to the install guide and on, never to a stop")


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
