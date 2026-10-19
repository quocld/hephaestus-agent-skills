#!/usr/bin/env python3
"""Print the next release for the commits since the newest v* tag, as GitHub Actions outputs.

release=false when HEAD is already tagged or nothing changed. Otherwise the bump follows the commit subjects
(conventional commits): "!" after the type or a "BREAKING CHANGE:" footer line is major, any feat is minor, the rest is
patch. The first release starts at v1.0.0.
"""
import re
import subprocess


# A breaking change is a "!" after the type, or a footer line that starts with BREAKING CHANGE: (or BREAKING-CHANGE:).
# The words anywhere else in a message, such as a sentence that describes this rule, do not count.
BREAKING = re.compile(r"^BREAKING[ -]CHANGE:", re.M)


def git(*args):
    p = subprocess.run(["git", *args], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else ""


def main():
    last = git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*")
    if last and git("tag", "--points-at", "HEAD", "--list", "v[0-9]*"):
        print("release=false")
        return
    log = git("log", "--no-merges", "--format=%s%n%b%n--end--", f"{last}..HEAD" if last else "HEAD")
    commits = [c.strip() for c in log.split("--end--") if c.strip()]
    if last and not commits:
        print("release=false")
        return
    m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", last or "")
    major, minor, patch = (int(x) for x in m.groups()) if m else (0, 0, 0)
    subjects = [c.splitlines()[0] for c in commits]
    if not last:
        version = "v1.0.0"
    elif any(re.match(r"^\w+(\([^)]*\))?!:", s) for s in subjects) or any(BREAKING.search(c) for c in commits):
        version = f"v{major + 1}.0.0"
    elif any(re.match(r"^feat(\([^)]*\))?:", s) for s in subjects):
        version = f"v{major}.{minor + 1}.0"
    else:
        version = f"v{major}.{minor}.{patch + 1}"
    print("release=true")
    print(f"version={version}")
    print(f"previous={last}")


if __name__ == "__main__":
    main()
