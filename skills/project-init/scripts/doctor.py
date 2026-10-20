#!/usr/bin/env python3
"""project-init doctor: check every tool the skills call and the drift of the project's AGENTS.md block; print one table.

Read-only for the project.
It never writes a project file, never prints a secret value or a version command's output beyond a SHA prefix, and never
runs one of the project's own build, test, install, migrate or server commands: block commands are resolved, not run.
The one exception is the logger contract row, and only with --logger-test or --logger-entry: it runs that logger's own
test, or logs one probe line, with the Better Stack variables unset so nothing ships.
A `version` on a confirm-each-step environment is never run: its row is SKIP with the command to run after asking.

Tool probes it runs unless --no-probe (each read-only for the project; git ones fail instead of prompting):
  bash hooks/test.sh (the plugin's own hook test, in throwaway repos); gh/glab auth status, vercel whoami, op whoami;
  gh pr list (open PRs that add a missing AGENTS.md or registry); git ls-remote origin; git fetch origin --prune (updates remote-tracking refs only), when docs/status is opted in;
  claude mcp list (starts the configured MCP servers to health-check them); npx -y --prefer-offline chrome-devtools-axi
  --help and npx -y ajv-cli@5.0.0 (may download into the npx cache); the registry's non-asks-first `version` commands.
Without probes those rows are SKIP with the command to run.

Machine-level rows (plugin, hooks, CLIs, logins, MCP, markers, TODOs, registry secrets) come from the harness-map
collectors, so each check has one owner; this script owns the project-block and registry probes.

Status: OK, MISSING, FAILING, DRIFT, PENDING (in an open PR/MR the user merges), SKIP (precondition absent, asks first, or not probed).
Exit 0 when no row is MISSING, FAILING or DRIFT, 1 otherwise, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]
sys.path.insert(0, str(SKILLS / "harness-map" / "scripts"))
try:
    import harness_map as hm   # noqa: E402  (the shared collectors)
    from page import run, strip_userinfo   # noqa: E402
except ImportError as e:   # project-init ships next to harness-map in the plugin
    sys.exit(f"doctor needs the harness-map skill next to project-init ({SKILLS / 'harness-map'}): {e}")

STATUS = {"ok": "OK", "missing": "MISSING", "fail": "FAILING", "warn": "DRIFT", "pending": "PENDING", "skip": "SKIP", "info": "SKIP"}
BAD = {"MISSING", "FAILING", "DRIFT"}
MANAGERS = {"pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock", "npm": "package-lock.json", "bun": "bun.lockb"}
BUILTINS = {"install", "i", "ci", "add", "remove", "rm", "uninstall", "update", "up", "upgrade", "exec", "dlx", "x",
            "create", "init", "why", "list", "ls", "outdated", "audit", "link", "unlink", "publish", "pack", "store",
            "config", "env", "prune", "rebuild", "import", "fetch", "patch", "licenses", "dedupe", "info", "view", "help"}
DB_TYPES = {"supabase", "postgres", "postgresql", "mysql", "database", "db", "rds"}
LITERAL = re.compile(r"(?i)(token|secret|password|passwd|api[_-]?key)\s*[=:]\s*[^\s$\"'{]")
BETTER_STACK_ENV = ("BETTER_STACK_SOURCE_TOKEN", "BETTER_STACK_INGESTING_HOST")


def row(check, status, detail="", fix=""):
    return {"check": check, "status": status, "detail": detail, "fix": fix}


def from_hm(c, title=None):
    return row(title or c["title"], STATUS[c["status"]], c["detail"], c["fix"])


def shown(cmd):
    """A registry command as it may be printed: never one that looks like it carries a literal secret."""
    if LITERAL.search(cmd) or any(strip_userinfo(w)[1] for w in re.findall(r"[a-z][a-z0-9+.-]*://\S+", cmd, re.I)):
        return "<command not shown: it looks like it holds a literal secret; fix that in the registry first>"
    return cmd


# ---------------------------------------------------------------- shared collectors (owner: harness-map)

TOOL_ROWS_ALWAYS = {"gh auth", "glab auth", "vercel login", "op sign-in", "docker compose"}
PROJECT_ROWS_DROPPED = {"Repository", "Project checks (verify-loop)", "Playwright config"}


def machine_rows(project, registry, probe, manager):
    hm.PLUGIN_ID, hm.PLUGIN_DIR = hm.agent_skills_plugin(project)
    # The platform's own CLI login only: a GitLab project needs glab, not gh (glab rows appear only for GitLab).
    gitlab = "gitlab" in run(["git", "-C", str(project), "remote", "get-url", "origin"])[1].lower()
    out = [from_hm(c) for c in hm.collect_global()]
    out += [from_hm(c) for c in hm.collect_hooks(probe, project) if c["status"] != "info"]
    reg_text = json.dumps(registry or {}).lower()
    for c in hm.collect_tools(probe, registry, project)[0]:
        kind = hm.TOOL_KIND.get(c["title"])
        wanted = (c["title"] in TOOL_ROWS_ALWAYS or kind == "required"
                  or (c["title"] in ("glab", "op", "vercel", "supabase") and c["status"] != "info")
                  or (c["title"] == "pnpm" and manager == "pnpm")
                  or (c["title"] == "docker" and ("compose" in reg_text or "docker" in reg_text)))
        if gitlab and c["title"] == "gh auth":
            continue
        if gitlab and c["title"] == "gh" and c["status"] != "ok":
            out.append(row("gh", "SKIP", "not on PATH; this GitLab project uses glab"))
        elif wanted:
            out.append(from_hm(c))
    if manager and manager != "pnpm":
        found = shutil.which(manager)
        out.append(row(manager, "OK" if found else "MISSING", "package manager of this repo (lockfile)",
                       "" if found else f"install {manager} (corepack enable {manager}, or brew install {manager})"))
    for c in hm.collect_plugins(project, registry, probe, deep=True)[0]:
        if c["title"] == "Browser tool for e2e-verify" and c["status"] == "warn" and probe:
            out.append(row(c["title"], "OK", c["detail"]))   # the npx fallback ran; Playwright MCP is optional here
        elif c["title"] in ("Better Stack MCP", "Browser tool for e2e-verify"):
            out.append(from_hm(c))
    return out


def project_rows(pc):
    return [from_hm(c) for c in pc if c["title"] not in PROJECT_ROWS_DROPPED]


# ---------------------------------------------------------------- the block

def block_text(project):
    f = Path(project) / "AGENTS.md"
    m = re.search(r"<!-- project-init:start -->(.*?)<!-- project-init:end -->", f.read_text(errors="ignore") if f.exists() else "", re.S)
    return m.group(1) if m else None


def block_line(block, label):
    return next((ln for ln in block.splitlines() if re.match(rf"^\s*-\s*{label}\b", ln, re.I)), "")


def repo_paths(block):
    seen = []
    for tok in re.findall(r"`([^`\s]+)`", block):
        t = tok.rstrip(".,;:")
        if not t or t.startswith(("http", "@", "op://", "env:", "-", "<", "$", "~", "/")) or any(ch in t for ch in "<>*={}"):
            continue
        if ("/" in t or re.search(r"\.[A-Za-z][A-Za-z0-9]{0,9}$", t)) and t not in seen:
            seen.append(t)
    return seen


def renamed_to(project, path):
    so = run(["git", "-C", str(project), "log", "-1", "--format=", "--name-status", "-M", "--full-diff", "--", path.rstrip("/")])[1]
    for ln in so.splitlines():
        parts = ln.split("\t")
        if len(parts) == 3 and parts[0].startswith("R") and parts[1].startswith(path.rstrip("/")):
            return parts[2] if parts[1] == path.rstrip("/") else parts[2].rsplit("/", 1)[0] + "/"
    return None


def check_paths(project, block):
    out, ok = [], 0
    for p in repo_paths(block):
        if (Path(project) / p).exists():
            ok += 1
            continue
        if run(["git", "-C", str(project), "check-ignore", "-q", p])[0] == 0:
            ok += 1   # a gitignored path, such as a storage state folder, need not exist in a fresh clone
            continue
        new = renamed_to(project, p)
        out.append(row(f"Block path {p}", "DRIFT", "named in the block but missing" + (f"; renamed to {new}" if new else ""),
                       f"update the block: {p} -> {new}" if new else "find where it moved, or ask the user, then update the block"))
    if not out:
        out.append(row("Block paths exist", "OK", f"{ok} path(s) named in the block exist or are gitignored"))
    return out


def package_dirs(project):
    root = Path(project)
    found = []
    for depth in ("", "*/", "*/*/", "*/*/*/"):
        found += [f.parent for f in root.glob(depth + "package.json") if "node_modules" not in f.parts]
    return found


def scripts_of(d):
    data = hm.load_json(Path(d) / "package.json")
    return data.get("scripts") if isinstance(data, dict) and isinstance(data.get("scripts"), dict) else {}


def probe_manager(project, cwd, argv):
    """Cheap probe of `<manager> ...`: the script exists in the right package.json; never run."""
    mgr, rest = argv[0], argv[1:]
    filters, recursive, words, i = [], False, [], 0
    while i < len(rest):
        a = rest[i]
        if a in ("--filter", "-F") and i + 1 < len(rest):
            filters.append(rest[i + 1]); i += 2; continue
        if a.startswith("--filter="):
            filters.append(a.split("=", 1)[1]); i += 1; continue
        if a in ("-C", "--dir", "--prefix", "--cwd") and i + 1 < len(rest):
            cwd = cwd / rest[i + 1]; i += 2; continue
        if a in ("-r", "--recursive", "-ws", "--workspaces"):
            recursive = True
        elif not a.startswith("-"):
            words.append(a)
        i += 1
    if not words:
        return None
    sub = words[0]
    if mgr == "yarn" and sub == "workspace" and len(words) >= 3:
        filters, script = [words[1]], words[2]
    elif sub in ("run", "run-script"):
        if len(words) < 2:
            return None
        script = words[1]
    elif sub in BUILTINS:
        if sub in ("install", "i", "ci") and not any((Path(project) / lf).exists() for lf in MANAGERS.values()):
            return "DRIFT", f"`{mgr} {sub}` but no lockfile at the repo root", "commit the lockfile, or fix the block's install command"
        return None
    elif mgr == "npm" and sub not in ("test", "start", "stop", "restart", "t"):
        return None   # any other bare npm word is an npm command, not a script
    else:
        script = {"t": "test"}.get(sub, sub)
    if filters or recursive:
        dirs = package_dirs(project)
        if filters:
            names = {d: (hm.load_json(d / "package.json") or {}).get("name", "") for d in dirs}
            dirs = [d for d in dirs if any(fnmatch.fnmatch(str(names[d]), f.rstrip(".")) or
                                           (Path(project) / f.lstrip("./")).resolve() == d.resolve() for f in filters)]
            if not dirs:
                return "DRIFT", f"no package matches --filter {' '.join(filters)}", "update the block with the package's current name"
        if any(script in scripts_of(d) for d in dirs):
            return None
        return "DRIFT", f"no package selected by `{' '.join(argv)}` has a `{script}` script", "update the block with the script's current name"
    if script in scripts_of(cwd) or (mgr != "npm" and (cwd / "node_modules" / ".bin" / script).exists()):
        return None
    rel = os.path.relpath(cwd, project)
    return "DRIFT", f"no `{script}` script in {'' if rel == '.' else rel + '/'}package.json", \
        "find the script's new name in package.json (same body), then update the block"


def probe_command(project, cmd):
    """(status, detail, fix) for one block command, checked without running it."""
    root, cwd = Path(project), Path(project)
    for part in [p.strip() for p in re.split(r"&&|\|\||;|\|", cmd) if p.strip()]:
        try:
            argv = shlex.split(part)
        except ValueError:
            return "DRIFT", "cannot be parsed as a shell command", "fix the quoting in the block"
        while argv and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]):
            argv.pop(0)
        if not argv:
            continue
        if argv[0] == "cd":
            cwd = cwd / (argv[1] if len(argv) > 1 else ".")
            if not cwd.is_dir():
                return "DRIFT", f"folder {os.path.relpath(cwd, root)} does not exist", "update the block"
            continue
        if argv[0] == "env":
            argv = [a for a in argv[1:] if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", a) and not a.startswith("-")]
            if not argv:
                continue
        if "/" in argv[0]:
            exe = cwd / argv[0]   # a relative or absolute path, resolved where the command would run
            if not (exe.is_file() and os.access(str(exe), os.X_OK)):
                return "DRIFT", f"{argv[0]} does not exist or is not executable in {os.path.relpath(cwd, root)}", \
                    "update the block with the script's current path"
            continue
        if not shutil.which(argv[0]):
            return "MISSING", f"{argv[0]} is not on PATH", f"install {argv[0]}"
        if argv[0] in MANAGERS:
            problem = probe_manager(root, cwd, argv)
            if problem:
                return problem
        elif argv[0] == "make":
            code = run(["make", "-n", *argv[1:]], cwd=str(cwd), timeout=20)[0]
            if code != 0:
                return "DRIFT", f"`make -n {' '.join(argv[1:])}` exits {code}", "update the block with the current make target"
    return "OK", "", ""


def check_commands(project, block):
    line = block_line(block, "Commands")
    cmds = re.findall(r"`([^`]+)`", line)
    if not cmds:
        return [row("Block commands resolve", "SKIP", "the block has no Commands line")]
    out = []
    for c in cmds:
        st, detail, fix = probe_command(project, c)
        if st != "OK":
            out.append(row(f"Block command `{c}`", st, detail, fix))
    return out or [row("Block commands resolve", "OK", f"{len(cmds)} command(s) resolve (probed, not run)")]


# ---------------------------------------------------------------- registry

def services(registry):
    for env_name, e in hm.env_map(registry).items():
        for s in e.get("services", []):
            yield env_name, e, s


def check_registry_schema(project, probe):
    reg, schema = ".agents/environments.json", ".agents/environments.schema.json"
    cmd = f"npx -y ajv-cli@5.0.0 validate --spec=draft2020 -s {schema} -d {reg}"
    if not (Path(project) / schema).exists():
        return row("Registry valid", "DRIFT", f"{schema} is missing next to the registry",
                   "copy the environments skill's templates/environments.schema.json there (its create section)")
    if not probe:
        return row("Registry valid", "SKIP", "not probed (--no-probe)", cmd)
    if not shutil.which("npx"):
        return row("Registry valid", "MISSING", "npx is not on PATH, so the schema cannot be checked", "brew install node")
    code = run(["npx", "-y", "ajv-cli@5.0.0", "validate", "--spec=draft2020", "-s", schema, "-d", reg], cwd=str(project), timeout=180)[0]
    # ajv's error text can quote registry values, so only the verdict is printed.
    return row("Registry valid", "OK" if code == 0 else "FAILING", "matches its schema" if code == 0 else f"schema validation exits {code}",
               "" if code == 0 else cmd)


def check_ssh(registry):
    aliases = sorted({_s for _, _, s in services(registry) for _s in [s.get("access", {}).get("ssh")] if isinstance(_s, str) and _s})
    if not aliases:
        return [row("SSH aliases", "SKIP", "no access.ssh in the registry")]
    if not shutil.which("ssh"):
        return [row("SSH aliases", "MISSING", "ssh is not on PATH", "install OpenSSH")]
    out = []
    for a in aliases:
        code, so, _ = run(["ssh", "-G", a], timeout=10)
        host = next((ln.split(None, 1)[1] for ln in so.splitlines() if ln.startswith("hostname ")), "")
        # ssh -G exits 0 and echoes the alias back when no Host entry matches.
        ok = code == 0 and host and host.lower() != a.lower()
        out.append(row(f"SSH alias {a}", "OK" if ok else "MISSING", "has a Host entry" if ok else "no Host entry matches it",
                       "" if ok else f"add `Host {a}` to ~/.ssh/config (ask the user for the host name and user)"))
    return out


def version_cmd(project, cmd):
    """argv that runs a registry `version` with .agents/secrets.env loaded in the same shell (environments section 9).
    The file is the one harness-map reads (hm.secrets_file): the worktree's own, else the main checkout's."""
    sec = hm.secrets_file(project)
    if sec and sec.exists() and "op://" in sec.read_text(errors="ignore") and shutil.which("op"):
        return ["op", "run", "--env-file", str(sec), "--", "bash", "-c", cmd]
    prefix = f"set -a; . {shlex.quote(str(sec))}; set +a; " if sec and sec.exists() else ""
    return ["bash", "-c", prefix + cmd]


def check_versions(project, registry, probe):
    out = []
    for env_name, e, s in services(registry):
        cmd = s.get("version")
        if not isinstance(cmd, str) or not cmd.strip():
            continue   # a missing version command is the harness-map "version command" row
        title = f"Version {env_name}/{s['name']}"
        allowed = e.get("allowedWithoutAsking") if isinstance(e.get("allowedWithoutAsking"), list) else []
        if e.get("policy") == "confirm-each-step" and "version" not in allowed:
            out.append(row(title, "SKIP", "confirm-each-step: asks first", f"ask the user, then run: {shown(cmd)}"))
            continue
        if not probe:
            out.append(row(title, "SKIP", "not probed (--no-probe)", shown(cmd)))
            continue
        code, so, _ = run(version_cmd(project, cmd), cwd=str(project), timeout=30)
        lines = [ln.strip() for ln in so.splitlines() if ln.strip()]
        value = lines[0] if len(lines) == 1 else ""
        db = s.get("type", "").lower() in DB_TYPES
        if code == 0 and re.fullmatch(r"[0-9a-f]{40}", value):
            out.append(row(title, "OK", f"runs {value[:12]}"))
        elif code == 0 and db and value and value.lower() not in ("unknown", "null"):
            out.append(row(title, "OK", "prints the latest applied migration"))
        else:
            # The output is never printed: a failing command can echo a connection string.
            why = f"exits {code}" if code else ("prints more than one line" if len(lines) > 1 else "prints no 40-character SHA")
            out.append(row(title, "FAILING", why, "fix the version endpoint (environments references/version-endpoint.md), "
                                                 "or a secret that does not resolve; then run: " + shown(cmd)))
    return out or [row("Version endpoints", "SKIP", "no service in the registry has a version command")]


def check_log_sources(registry):
    missing = []
    for env_name, e, s in services(registry):
        if "//localhost" in e.get("url", "") or s.get("type") == "local" or isinstance(s.get("logs"), str):
            continue   # a string `logs` is the harness-map "logs field" rename row
        logs = s.get("logs") if isinstance(s.get("logs"), dict) else {}
        if not logs.get("source"):
            missing.append(f"{env_name}/{s['name']}")
    if missing:
        return row("Log sources registered", "MISSING", "no logs.source for " + ", ".join(missing),
                   "record each service's Better Stack source per `betterstack-logs` section 3, through the registry-change rule")
    return row("Log sources registered", "OK", "every deployed service names its Better Stack source")


# ---------------------------------------------------------------- logger, feature status, project checks

def required_log_keys():
    """The fields `logging-standard` section 1 requires on every line, read from its table (one owner)."""
    f = SKILLS / "logging-standard" / "SKILL.md"
    text = f.read_text() if f.exists() else ""
    return [m.group(1) for m in re.finditer(r"^\|\s*`([a-z_]+)`\s*\|[^|]*\|\s*always\s*\|", text, re.M)]


def check_logger(project, block, a, probe):
    line = block_line(block, "Logging") if block else ""
    if not line:
        return row("Logger contract", "SKIP", "the block names no logger")
    how = "rerun with --logger-test '<the logger's own test command>' or --logger-entry <built logger entry>"
    if not probe:
        return row("Logger contract", "SKIP", "not probed (--no-probe)", how)
    if not (a.logger_test or a.logger_entry):
        # The block names a logger, so an unchecked contract is drift, not a pass.
        return row("Logger contract", "DRIFT", "the block names a logger but its contract was not checked", how)
    env = {k: v for k, v in os.environ.items() if k not in BETTER_STACK_ENV}
    if a.logger_test:
        p = subprocess.run(["bash", "-c", a.logger_test], cwd=str(project), env=env, capture_output=True, text=True, timeout=300)
        return row("Logger contract", "OK" if p.returncode == 0 else "FAILING", f"the logger's own test exits {p.returncode}",
                   "" if p.returncode == 0 else "fix the logger against `logging-standard` section 1")
    keys = required_log_keys()
    if not keys:
        return row("Logger contract", "SKIP", "cannot read the required keys from `logging-standard` section 1", how)
    entry = (Path(project) / a.logger_entry).resolve()
    js = ("import(require('url').pathToFileURL(process.argv[1]).href).then((m) => "
          "(m.createLogger || (m.default && m.default.createLogger))({ service: 'doctor' }).info('probe'))")
    try:
        p = subprocess.run(["node", "-e", js, str(entry)], cwd=str(project), env=dict(env, NODE_ENV="production"),
                           capture_output=True, text=True, timeout=30)
        first = next((ln for ln in p.stdout.splitlines() if ln.strip()), "")
        obj = json.loads(first)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        obj = None
    if not isinstance(obj, dict):
        return row("Logger contract", "FAILING", "the probe crashed, printed nothing, or printed a non-JSON line",
                   "fix the logger against `logging-standard` section 1")
    lacking = [k for k in keys if k not in obj]
    return row("Logger contract", "OK" if not lacking else "FAILING",
               "the probe line has every required key" if not lacking else "missing keys: " + " ".join(lacking),
               "" if not lacking else "fix the logger against `logging-standard` section 1")


def check_feature_status(project, int_branch, probe):
    status_py = SKILLS / "feature-status" / "scripts" / "status.py"
    if not int_branch:
        return [row("Feature status", "SKIP", "no integration branch recorded to read docs/status from (the Integration branch row)")]
    so = run(["git", "-C", str(project), "ls-tree", "-d", f"origin/{int_branch}", "docs/status"])[1]
    if not so.strip():
        return [row("Feature status", "SKIP", f"origin/{int_branch} has no docs/status (not opted in)")]
    if not status_py.exists():
        return [row("Feature status", "SKIP", "the feature-status skill is not next to project-init")]
    if probe:
        run(["git", "-C", str(project), "fetch", "origin", "--prune"], timeout=60, env=hm.git_batch_env())
    code, so, se = run([sys.executable, str(status_py), "check", "--ref", f"origin/{int_branch}"], cwd=str(project), timeout=60)
    out = [row("Feature status files valid", "OK" if code == 0 else "FAILING",
               f"origin/{int_branch}" + ("" if probe else " (not fetched: --no-probe)") +
               ("" if code == 0 else ": " + "; ".join((so + se).strip().splitlines()[:3])),
               "" if code == 0 else "fix them through the feature-status skill")]
    if not probe:
        return out + [row("Leftover feature claims", "SKIP", "not probed (--no-probe)",
                          "git ls-remote --heads origin 'refs/heads/claim/*'")]
    so = run(["git", "-C", str(project), "ls-remote", "--heads", "origin", "refs/heads/claim/*"], timeout=20, env=hm.git_batch_env())[1]
    ids = [ln.rsplit("refs/heads/claim/", 1)[1] for ln in so.splitlines() if "refs/heads/claim/" in ln]
    leftover = []
    for i in ids:
        # --dry-run exits 0 only when this pick is merged, dropped or deferred, so a live re-pick is not flagged.
        if run([sys.executable, str(status_py), "release", i, "--int", int_branch, "--dry-run"], cwd=str(project), timeout=60)[0] == 0:
            leftover.append(i)
    for i in leftover:
        out.append(row(f"Leftover claim/{i}", "DRIFT", "its pick is merged, dropped or deferred",
                       f"python3 {status_py} release {i} --int {int_branch}"))
    if not leftover:
        out.append(row("Leftover feature claims", "OK", f"{len(ids)} claim branch(es), none left over"))
    return out


def check_project_checks(project):
    if not (Path(project) / ".agents" / "checks").is_dir():
        return row("Project checks valid", "SKIP", "no .agents/checks/")
    checks_py = SKILLS / "verify-loop" / "scripts" / "checks.py"
    if not checks_py.exists():
        return row("Project checks valid", "SKIP", "the verify-loop skill is not next to project-init")
    code, so, se = run([sys.executable, str(checks_py), "list"], cwd=str(project), timeout=30)
    return row("Project checks valid", "OK" if code == 0 else "FAILING",
               f"{len([ln for ln in so.splitlines() if ln.strip()])} check(s)" if code == 0 else "; ".join((se or so).strip().splitlines()[-3:]),
               "" if code == 0 else f"python3 {checks_py} list, then fix the files it names (verify-loop section 4)")


# ---------------------------------------------------------------- main

def doctor(project, a):
    probe = not a.no_probe
    pc, registry = hm.collect_project(project, probe, deep=True)
    lock = next((m for m, lf in MANAGERS.items() if (Path(project) / lf).exists()), None)
    rows = machine_rows(project, registry, probe, lock)
    rows += project_rows(pc)
    if isinstance(registry, dict):
        rows += [check_registry_schema(project, probe)] + check_ssh(registry) + check_versions(project, registry, probe)
        rows.append(check_log_sources(registry))
    else:
        rows.append(row("Registry probes", "SKIP", "no valid .agents/environments.json (schema, SSH, version, log sources)"))
    block = block_text(project)
    rows.append(check_logger(project, block, a, probe))
    int_branch, _ = hm.integration_branch(registry)
    rows += check_feature_status(project, int_branch, probe)
    if block is None:
        rows.append(row("Block paths and commands", "SKIP", "AGENTS.md has no project-init block"))
    else:
        rows += check_paths(project, block) + check_commands(project, block)
    rows.append(check_project_checks(project))
    return rows


def cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="the project's git repo (default: the current directory)")
    ap.add_argument("--no-probe", action="store_true",
                    help="offline: skip every tool probe listed below and the version commands (rows become SKIP)")
    ap.add_argument("--logger-test", metavar="CMD", help="the logger's own test command (only that test file), run with Better Stack env unset")
    ap.add_argument("--logger-entry", metavar="FILE", help="the built logger module; logs one probe line with Better Stack env unset")
    ap.add_argument("--json", action="store_true", help="print the rows as JSON instead of a Markdown table")
    a = ap.parse_args(argv)
    project = hm.git_root(a.project)
    if not project:
        ap.error(f"--project {a.project} is not inside a git repo")
    rows = doctor(Path(project), a)
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        print(f"project-init doctor: {project}\n")
        print("| Check | Status | Detail | Fix |\n| --- | --- | --- | --- |")
        for r in rows:
            print(f"| {cell(r['check'])} | {r['status']} | {cell(r['detail'])} | {cell(r['fix'])} |")
        n = {s: sum(1 for r in rows if r["status"] == s) for s in ("OK", "MISSING", "FAILING", "DRIFT", "PENDING", "SKIP")}
        print("\n" + "  ".join(f"{k} {v}" for k, v in n.items()))
    return 1 if any(r["status"] in BAD for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
