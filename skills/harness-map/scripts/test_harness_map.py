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

    prompt_text = hm.setup_prompt()
    check("which branch PRs go into" in prompt_text and "never assume dev or main" in prompt_text and "staging, prod" in prompt_text,
          "setup prompt: always asks the integration branch and which environments exist")

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
