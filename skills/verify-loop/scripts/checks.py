#!/usr/bin/env python3
"""Project checks: the rules a project keeps needing that no linter knows, one file each in .agents/checks/.

Usage (run anywhere inside the project's git repo):
  python3 checks.py list                validate every check and print id, kind, paths
  python3 checks.py match <base>        print the checks whose paths match the files changed since <base>
  python3 checks.py run <base>          run the matched script checks, then print the matched review rules
                                        for the reviewer prompt; exit 1 when a script check fails
  python3 checks.py new <id>            print a template to save as .agents/checks/<id>.md

Changed files = `git diff --name-only <base>...HEAD`, plus uncommitted and untracked files.
A check file is Markdown with a front block of `key: value` lines between `---` lines:
  id      same as the file name without .md, lowercase-with-dashes
  kind    script (runs a command) or review (a rule the fresh-review reviewer applies to the diff)
  paths   JSON list of globs relative to the repo root; `**` crosses folders, `*` does not
  run     script only: the command, run from the repo root; exit 0 = pass. It must be safe on any tree,
          since CI may run every script check on every change
  why     the incident or the repeated correction that created the check, with its date
The body below the front block is the rule in plain words; required for review checks.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

KEYS = {"id", "kind", "paths", "run", "why"}
TIMEOUT = 600
TEMPLATE = """---
id: {id}
kind: review
paths: ["db/migrations/**"]
why: <what went wrong, or what the user corrected twice, and when>
---
<The rule, stated so a reviewer can say pass or fail from the diff alone.
Example: reject any migration that drops a column unless the same change backfills or copies its data first.>
"""


def fail(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def git(*args):
    out = subprocess.run(["git", *args], capture_output=True, text=True)
    if out.returncode:
        fail(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def root():
    return Path(git("rev-parse", "--show-toplevel").strip())


def glob_re(pattern):
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def parse(path):
    """Return (check dict, problems)."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        return None, [f"{path.name}: no front block between --- lines"]
    check, problems = {"body": m.group(2).strip()}, []
    for line in m.group(1).splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or key not in KEYS:
            problems.append(f"{path.name}: unknown line {line!r}")
            continue
        check[key] = value
    if check.get("id") != path.stem or not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", path.stem):
        problems.append(f"{path.name}: id must equal the file name, lowercase-with-dashes")
    if check.get("kind") not in ("script", "review"):
        problems.append(f"{path.name}: kind must be script or review")
    try:
        paths = json.loads(check.get("paths", ""))
        assert isinstance(paths, list) and paths and all(isinstance(p, str) and p for p in paths)
        check["paths"] = paths
    except (ValueError, AssertionError):
        problems.append(f'{path.name}: paths must be a JSON list of globs, e.g. ["src/**/*.ts"]')
    if check.get("kind") == "script" and not check.get("run"):
        problems.append(f"{path.name}: a script check needs run")
    if check.get("kind") == "review" and not check["body"]:
        problems.append(f"{path.name}: a review check needs the rule in its body")
    if any(v.lstrip().startswith("<") for v in (check.get("why", ""), check["body"])):
        problems.append(f"{path.name}: still holds the template's <placeholder> text")
    if not check.get("why"):
        problems.append(f"{path.name}: why is required, so the check can be retired when its reason is gone")
    return check, problems


def load(repo):
    folder = repo / ".agents" / "checks"
    checks, problems = [], []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        check, p = parse(path)
        problems += p
        if check and not p:
            checks.append(check)
    if problems:
        fail("invalid checks:\n  " + "\n  ".join(problems))
    return checks


def changed(base):
    files = set(git("diff", "--name-only", f"{base}...HEAD").split())
    files |= set(git("diff", "--name-only", "HEAD").split())
    files |= set(git("ls-files", "--others", "--exclude-standard").split())
    return sorted(files)


def matched(checks, files):
    out = []
    for c in checks:
        regexes = [glob_re(p) for p in c["paths"]]
        hits = [f for f in files if any(r.match(f) for r in regexes)]
        if hits:
            out.append((c, hits))
    return out


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[1]
    if cmd == "new" and len(argv) == 3:
        print(TEMPLATE.format(id=argv[2]), end="")
        return 0
    repo = root()
    checks = load(repo)
    if cmd == "list":
        for c in checks:
            print(f"{c['id']}\t{c['kind']}\t{' '.join(c['paths'])}")
        print(f"{len(checks)} checks valid")
        return 0
    if cmd not in ("match", "run") or len(argv) != 3:
        fail("usage: checks.py list | match <base> | run <base> | new <id>")
    hits = matched(checks, changed(argv[2]))
    if cmd == "match":
        for c, files in hits:
            print(f"{c['id']}\t{c['kind']}\t{len(files)} file(s): {' '.join(files[:5])}")
        print(f"{len(hits)} of {len(checks)} checks match")
        return 0
    failed = 0
    for c, _ in hits:
        if c["kind"] != "script":
            continue
        try:
            r = subprocess.run(c["run"], shell=True, cwd=repo, capture_output=True, text=True, timeout=TIMEOUT)
            code, output = r.returncode, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            code, output = "timeout", f"no result after {TIMEOUT}s"
        print(f"{'PASS' if code == 0 else 'FAIL'} {c['id']} (exit {code})")
        if code != 0:
            failed += 1
            print("\n".join("    " + line for line in output.splitlines()[-30:]))
    reviews = [c for c, _ in hits if c["kind"] == "review"]
    print("\nProject checks for the reviewer:" if reviews else "\nProject checks for the reviewer: none")
    for c in reviews:
        print(f"- {c['id']} ({', '.join(c['paths'])}): {' '.join(c['body'].split())}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
