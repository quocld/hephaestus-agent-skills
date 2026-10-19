#!/usr/bin/env python3
"""Regression tests for harness_map.py: no secret value reaches the page or stdout, malformed inputs do not crash,
and the scripts compile on the oldest python3 a fresh Mac ships (3.9). Builds throwaway HOME and project folders;
never touches the real ~/.claude. Usage: python3 test_harness_map.py  (exit 1 on any failure)
"""
import json
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
}
FAILS = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def run(home, project, extra=()):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("JIRA_", "CLAUDE_"))}
    env["HOME"] = str(home)
    out = home / "page.html"
    if out.exists():
        out.unlink()
    p = subprocess.run([sys.executable, str(SCRIPT), "--no-probe", "--project", str(project), "--out", str(out), *extra],
                       capture_output=True, text=True, env=env, timeout=120)
    page = out.read_text() if out.exists() else ""
    return p.returncode, p.stdout + p.stderr, page


def leaky_machine(root):
    home, project = root / "home", root / "project"
    claude = home / ".claude"
    (claude / "plugins").mkdir(parents=True)
    hook_cmd = "SLACK_TOKEN=" + LEAKS["inline env in a hook command"] + " python3 /opt/hooks/notify.py"
    (claude / "settings.json").write_text(json.dumps({
        "env": {"SLACK_TOKEN": LEAKS["settings env literal"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": hook_cmd}]}]},
    }))
    (home / ".claude.json").write_text(json.dumps({"mcpServers": {"x": {"env": {"API_KEY": LEAKS["MCP server env literal"]}}}}))
    url = "https://gitlab+deploy-token-1:" + LEAKS["marketplace URL credentials"] + "@git.example.com/x.git"
    (claude / "plugins" / "known_marketplaces.json").write_text(json.dumps({"team": {"source": {"source": "git", "url": url}}}))
    (project / ".agents").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    subprocess.run(["git", "-C", str(project), "remote", "add", "origin",
                    "https://user:" + LEAKS["git remote credentials"] + "@github.com/acme/app.git"], check=True)
    (project / ".gitignore").write_text(".agents/secrets.env\n")
    (project / ".agents" / "secrets.env").write_text("STAGING_DB_URL=" + LEAKS["secrets.env value"] + "\n")
    (project / ".agents" / "environments.json").write_text(json.dumps({"project": "acme", "defaultEnvironment": "dev", "environments": {
        "staging": {"policy": "confirm-writes", "url": "https://staging.acme.test", "services": [
            {"name": "web", "type": "vps", "access": {"dbUrl": {"secret": "env:STAGING_DB_URL"}}}],
            "accounts": [{"role": "admin", "login": "a@acme.test", "password": LEAKS["registry literal password"]},
                         {"role": "member", "login": "m@acme.test", "password": {"secret": LEAKS["registry literal secret object"]}}]}}}))
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


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        home, project = leaky_machine(root)
        code, out, page = run(home, project)
        check(code == 0 and bool(page), "leaky machine: the page is written")
        for what, value in LEAKS.items():
            check(value not in page, f"{what}: value not in the page")
            check(value not in out, f"{what}: value not in stdout")
        code, out, _ = run(home, project, ["--prompt"])
        check(all(v not in out for v in LEAKS.values()), "setup prompt holds no secret value")
        check(not any(p in out for p in (str(home), "/Users/", "Desktop")), "setup prompt holds no machine path")

        for name, registry in MALFORMED.items():
            (project / ".agents" / "environments.json").write_text(json.dumps(registry))
            code, out, page = run(home, project)
            check(code == 0 and bool(page), f"malformed registry ({name}): no crash")

        (home / ".claude" / "settings.json").write_text(json.dumps({"hooks": None}))
        (home / ".claude" / "settings.local.json").write_text(json.dumps({"hooks": None}))
        (home / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({"plugins": {"a@b": {"installPath": "/nope"}}}))
        code, out, page = run(home, project)
        check(code == 0 and bool(page), "hooks null and a dict plugin index: no crash")

    old = shutil.which("python3.9") or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else None)
    if old:
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
