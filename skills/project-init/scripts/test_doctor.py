#!/usr/bin/env python3
"""Regression tests for doctor.py: it never runs an asks-first or build command, never prints a secret or a version
command's output, reads block drift right, and compiles on the oldest python3 a fresh Mac ships (3.9).
Builds throwaway HOME and project folders; never touches the real ~/.claude. Usage: python3 test_doctor.py (exit 1 on failure)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "doctor.py"
SHA = "0123456789abcdef0123456789abcdef01234567"
# Stand-ins for secrets and command output that must never reach the terminal.
LEAK_SECRET = "LeakDoctorSecret1"
LEAK_OUTPUT = "LeakDoctorOutput2"
FAILS = []


def check(ok, what):
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILS.append(what)


def git(project, *args):
    subprocess.run(["git", "-C", str(project), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t"))


BLOCK = """# Project

<!-- project-init:start -->
## Agent setup

- Commands (repo root): install `pnpm install --frozen-lockfile`; lint `pnpm lint`; e2e `pnpm e2e`; web test `pnpm --filter web test`; build `make build`; gone `make nope`.
- Sources of truth: decision log `docs/decisions.md` > `docs/old.md` > `packages/missing/`.
- E2E: storage states in `e2e/.auth/` (gitignored).
- Logging: logger `packages/logger/` (`logging-standard`).
<!-- project-init:end -->
"""


def fixture(root):
    home, project, marker = root / "home", root / "project", root / "ran-prod"
    (home / ".claude").mkdir(parents=True)
    project.mkdir()
    git(project, "init", "-q")
    (project / "docs").mkdir()
    (project / "docs" / "decisions.md").write_text("x\n")
    (project / "docs" / "old.md").write_text("old\n")
    (project / "pnpm-lock.yaml").write_text("lockfileVersion: 9\n")
    (project / "package.json").write_text(json.dumps({"name": "root", "scripts": {"lint": "eslint ."}}))
    (project / "apps" / "web").mkdir(parents=True)
    (project / "apps" / "web" / "package.json").write_text(json.dumps({"name": "web", "scripts": {"test": "vitest"}}))
    (project / "packages" / "logger").mkdir(parents=True)
    (project / "packages" / "logger" / "index.js").write_text("")
    (project / "Makefile").write_text("build:\n\t@echo build\n")
    (project / ".gitignore").write_text("e2e/.auth/\n.agents/secrets.env\n")
    git(project, "add", "-A")
    git(project, "commit", "-qm", "init")
    git(project, "mv", "docs/old.md", "docs/new.md")
    git(project, "commit", "-qm", "rename")
    (project / "AGENTS.md").write_text(BLOCK)
    (project / "CLAUDE.md").write_text("@AGENTS.md\n")
    (project / ".agents").mkdir()
    (project / ".agents" / "secrets.env").write_text(f"STAGING_TOKEN={LEAK_SECRET}\n")
    web = {"name": "web", "type": "vercel", "access": {"ssh": "doctor-test-no-such-alias-7f3"},
           "version": f'test -n "$STAGING_TOKEN" && echo {SHA}'}
    registry = {"environments": {
        "dev": {"url": "http://localhost:3000", "branch": "dev", "policy": "autonomous",
                "services": [{"name": "web", "type": "local"}]},
        "staging": {"url": "https://staging.example.test", "branch": "staging", "policy": "confirm-writes",
                    "services": [web,
                                 {"name": "db", "type": "supabase", "version": "echo 20240101000000",
                                  "logs": {"provider": "betterstack", "source": "x-staging"}},
                                 {"name": "worker", "type": "vps", "version": "echo \"$STAGING_TOKEN\"; printf '%s%s' " + LEAK_OUTPUT[:4] + " " + LEAK_OUTPUT[4:] + "; exit 3",
                                  "logs": {"provider": "betterstack", "source": "x-staging"}}]},
        "prod": {"url": "https://example.test", "branch": "main", "policy": "confirm-each-step", "allowedWithoutAsking": [],
                 "services": [{"name": "web", "type": "vps", "version": f"touch {marker} && echo {SHA}",
                               "logs": {"provider": "betterstack", "source": "x-prod"}}]}}}
    (project / ".agents" / "environments.json").write_text(json.dumps(registry))
    return home, project, marker, registry


def main():
    p = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    check(p.returncode == 0 and "--no-probe" in p.stdout and "Read-only" in p.stdout, "--help documents the probes and the read-only rule")

    sys.path.insert(0, str(HERE))
    import doctor

    with tempfile.TemporaryDirectory() as tmp:
        home, project, marker, registry = fixture(Path(tmp))
        env = {k: v for k, v in os.environ.items() if not k.startswith(("CLAUDE_", "STAGING_"))}
        env["HOME"] = str(home)
        before = subprocess.run(["git", "-C", str(project), "status", "--porcelain"], capture_output=True, text=True).stdout
        p = subprocess.run([sys.executable, str(SCRIPT), "--no-probe", "--project", str(project)], capture_output=True, text=True,
                           env=env, timeout=180)
        out = p.stdout + p.stderr
        after = subprocess.run(["git", "-C", str(project), "status", "--porcelain"], capture_output=True, text=True).stdout
        check(p.returncode == 1 and "| Check | Status | Detail | Fix |" in out, "end to end: prints the table and exits 1 on drift")
        check(before == after, "end to end: the project is left unchanged")
        check(not marker.exists(), "end to end: a confirm-each-step version command is never run")
        check(LEAK_SECRET not in out and LEAK_OUTPUT not in out, "end to end: no secret value or command output printed")
        check("| Version prod/web | SKIP | confirm-each-step: asks first | ask the user, then run: touch" in out,
              "end to end: the asks-first row is SKIP with the command to run")
        check("| Version staging/web | SKIP | not probed (--no-probe)" in out, "end to end: --no-probe skips the version commands")
        check("| Browser tool for e2e-verify | OK" not in out, "end to end: an unprobed browser fallback is never OK")

        rows = {r["check"]: r for r in doctor.check_versions(project, registry, probe=True)}
        check(rows["Version staging/web"]["status"] == "OK", "versions: a SHA with secrets.env loaded is OK")
        check(rows["Version staging/db"]["status"] == "OK", "versions: a database prints its migration and is OK")
        check(rows["Version staging/worker"]["status"] == "FAILING" and LEAK_OUTPUT not in json.dumps(rows),
              "versions: a failing command is FAILING and its output is not shown")
        check(rows["Version prod/web"]["status"] == "SKIP" and not marker.exists(), "versions: probing never runs confirm-each-step")
        check(LEAK_SECRET not in json.dumps(rows), "versions: no secret value in the rows")

        block = doctor.block_text(project)
        paths = {r["check"]: r for r in doctor.check_paths(project, block)}
        check(set(paths) == {"Block path docs/old.md", "Block path packages/missing/"}, "paths: only the missing ones are flagged")
        check("renamed to docs/new.md" in paths["Block path docs/old.md"]["detail"], "paths: a rename names the new path")
        cmds = {r["check"]: r["status"] for r in doctor.check_commands(project, block)}
        check(cmds == {"Block command `pnpm e2e`": "DRIFT", "Block command `make nope`": "DRIFT"} if shutil.which("pnpm")
              else all(k in cmds for k in ("Block command `pnpm e2e`", "Block command `make nope`")),
              "commands: a missing script and a missing make target are flagged; the rest resolve")
        run_sh = project / "apps" / "web" / "run.sh"
        run_sh.write_text("#!/bin/sh\n")
        run_sh.chmod(0o755)
        check(doctor.probe_command(project, "cd apps/web && ./run.sh")[0] == "OK",
              "commands: a relative script after cd resolves against that folder, not the doctor's cwd")
        check(doctor.probe_command(project, "./apps/web/gone.sh")[0] == "DRIFT", "commands: a missing relative script is DRIFT")

        no_flags = type("A", (), {"logger_test": None, "logger_entry": None})
        check(doctor.check_logger(project, block, no_flags, True)["status"] == "DRIFT",
              "logger: a block logger probed without --logger-test or --logger-entry is DRIFT, not a pass")
        check(doctor.check_logger(project, block, no_flags, False)["status"] == "SKIP", "logger: --no-probe leaves it SKIP")

        hm = doctor.hm
        check(not hm.secrets_use_op(project), "op: a secrets.env without op:// does not need op")
        (project / ".agents" / "secrets.env").write_text(f"STAGING_TOKEN={LEAK_SECRET}\nAPI_KEY=op://vault/item/field\n")
        check(hm.secrets_use_op(project), "op: an op:// reference in secrets.env needs the op sign-in check")
        (project / ".agents" / "secrets.env").write_text(f"STAGING_TOKEN={LEAK_SECRET}\n")

        check(hm.betterstack_connection(False)["status"] == "skip", "Better Stack: not probed is SKIP, never OK")
        fake_bin = Path(tmp) / "bin"
        fake_bin.mkdir()
        claude = fake_bin / "claude"
        old_path = os.environ["PATH"]
        os.environ["PATH"] = f"{fake_bin}{os.pathsep}{old_path}"
        try:
            for what, line, want in (("connected", "betterstack: https://mcp.betterstack.com (HTTP) - Connected", "ok"),
                                     ("needs sign-in", "betterstack: https://mcp.betterstack.com (HTTP) - Needs authentication", "fail"),
                                     ("failed", "betterstack: https://mcp.betterstack.com (HTTP) - Failed to connect", "fail"),
                                     ("not listed", "other: x - Connected", "fail")):
                claude.write_text(f"#!/bin/sh\necho '{line}'\n")
                claude.chmod(0o755)
                check(hm.betterstack_connection(True)["status"] == want, f"Better Stack: {what} is {want}")
        finally:
            os.environ["PATH"] = old_path

        real = hm.collect_tools
        hm.collect_tools = lambda probe, reg, proj: ([hm.check("Tools", "gh", "missing", "not on PATH", "brew install gh"),
                                                      hm.check("Tools", "gh auth", "fail", "not logged in", "! gh auth login")], [])
        try:
            gh_rows = lambda: {r["check"]: r["status"] for r in doctor.machine_rows(project, registry, False, "pnpm")}
            check(gh_rows().get("gh auth") == "FAILING", "gh: a GitHub or remote-less project keeps the gh login row")
            git(project, "remote", "add", "origin", "git@gitlab.com:team/app.git")
            rows_gl = gh_rows()
            check("gh auth" not in rows_gl and rows_gl.get("gh") == "SKIP", "gh: a GitLab project drops the gh login and skips a missing gh")
            git(project, "remote", "remove", "origin")
        finally:
            hm.collect_tools = real

        ssh = doctor.check_ssh(registry)
        check([r["status"] for r in ssh] == ["MISSING"] if shutil.which("ssh") else True, "ssh: an alias with no Host entry is MISSING")
        logs = doctor.check_log_sources(registry)
        check(logs["status"] == "MISSING" and logs["detail"].endswith("staging/web"), "log sources: a deployed service without logs.source")

        if shutil.which("node"):
            pkg = project / "packages" / "logger"
            pkg.mkdir(parents=True, exist_ok=True)
            line = "{message: m, timestamp: 't', level: 30, service: o.service, env: 'local', version: 'unknown'}"
            (pkg / "good.mjs").write_text("export function createLogger(o) { return { info(m) {"
                                          " if (process.env.BETTER_STACK_SOURCE_TOKEN) throw new Error('would ship');"
                                          f" console.log(JSON.stringify({line})); }} }}; }}\n")
            (pkg / "bad.mjs").write_text("export function createLogger(o) { return { info(m) { console.log(JSON.stringify({msg: m})); } }; }\n")
            os.environ["BETTER_STACK_SOURCE_TOKEN"] = "dummy"
            try:
                good = doctor.check_logger(project, block, type("A", (), {"logger_test": None, "logger_entry": "packages/logger/good.mjs"}), True)
                bad = doctor.check_logger(project, block, type("A", (), {"logger_test": None, "logger_entry": "packages/logger/bad.mjs"}), True)
            finally:
                del os.environ["BETTER_STACK_SOURCE_TOKEN"]
            check(good["status"] == "OK", "logger: the probe runs with Better Stack env unset and finds every required key")
            check(bad["status"] == "FAILING" and "message" in bad["detail"], "logger: a missing required key is FAILING")
        else:
            print("SKIP no node for the logger probe")

    with tempfile.TemporaryDirectory() as tmp:
        bare = Path(tmp) / "bare"
        bare.mkdir()
        git(bare, "init", "-q")
        p = subprocess.run([sys.executable, str(SCRIPT), "--no-probe", "--project", str(bare)], capture_output=True, text=True,
                           env=dict(os.environ, HOME=tmp), timeout=180)
        check("| Block paths and commands | SKIP | AGENTS.md has no project-init block" in p.stdout, "bare repo: block rows are SKIP")

    old = shutil.which("python3.9") or ("/usr/bin/python3" if Path("/usr/bin/python3").exists() else None)
    if old:
        for f in (SCRIPT, Path(__file__).resolve()):
            r = subprocess.run([old, "-m", "py_compile", str(f)], capture_output=True, text=True)
            check(r.returncode == 0, f"{f.name} compiles on {old}")
    else:
        print("SKIP no python3.9 or /usr/bin/python3 to check old-version syntax")

    print("all passed" if not FAILS else f"{len(FAILS)} FAILED")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
