#!/usr/bin/env python3
"""Check that the docs cover every skill and hook before a release, and that a built site is complete.

Usage: check_docs.py [--site DIR --version vX.Y.Z --sha SHA]

Sources (always): every skills/<name>/SKILL.md is in the README `## Skills` table, in some pillar's covered_by.skills
(skills/harness-map/assets/pillars.json) and has an entry under `skills` in skills/harness-map/assets/lifecycle.json; every hooks/*.py
is in the README `## Hooks` table and the hooks/README.md table.
Site (with --site): index.html, install/index.html and 404.html exist, skills/<name>/index.html exists and sitemap.xml lists it for every skill, and version.json holds
the given version and sha.
Prints one line per gap and exits 1 when there is any.
"""
import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]


def skills():
    return sorted(p.parent.name for p in (REPO / "skills").glob("*/SKILL.md"))


def hooks():
    return sorted(p.name for p in (REPO / "hooks").glob("*.py"))


def table_names(path, heading=None):
    """Backticked first-column names of the Markdown tables in `path`, only under `## <heading>` when given."""
    text = (REPO / path).read_text()
    if heading:
        m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
        text = m.group(1) if m else ""
    return set(re.findall(r"^\| `([^`]+)` \|", text, re.M))


def source_gaps():
    assets = REPO / "skills" / "harness-map" / "assets"
    pillars = json.loads((assets / "pillars.json").read_text())
    in_pillars = {s for p in pillars["pillars"] for s in p.get("covered_by", {}).get("skills", [])}
    in_lifecycle = set(json.loads((assets / "lifecycle.json").read_text())["skills"])
    readme_skills = table_names("README.md", "Skills")
    readme_hooks = table_names("README.md", "Hooks")
    hooks_readme = table_names("hooks/README.md")
    for s in skills():
        if s not in readme_skills:
            yield f"skill {s}: missing from the README skill table (## Skills)"
        if s not in in_pillars:
            yield f"skill {s}: in no pillar's covered_by.skills (skills/harness-map/assets/pillars.json)"
        if s not in in_lifecycle:
            yield f"skill {s}: no entry under skills in skills/harness-map/assets/lifecycle.json"
    for h in hooks():
        if h not in readme_hooks:
            yield f"hook {h}: missing from the README hooks table (## Hooks)"
        if h not in hooks_readme:
            yield f"hook {h}: missing from the hooks/README.md table"


def site_gaps(site, version, sha):
    sitemap = (site / "sitemap.xml").read_text() if (site / "sitemap.xml").is_file() else ""
    if not sitemap:
        yield "site: sitemap.xml missing"
    for page in ("index.html", "install/index.html", "404.html"):
        if not (site / page).is_file():
            yield f"site: {page} missing"
    for s in skills():
        if not (site / "skills" / s / "index.html").is_file():
            yield f"site: skills/{s}/index.html missing"
        if f"/skills/{s}/" not in sitemap:
            yield f"site: sitemap.xml does not list skills/{s}/"
    try:
        built = json.loads((site / "version.json").read_text())
    except (OSError, ValueError):
        yield "site: version.json missing or not JSON"
        return
    if built.get("version") != version:
        yield f"site: version.json says {built.get('version')}, expected {version}"
    if built.get("sha") != sha:
        yield f"site: version.json sha {built.get('sha')}, expected {sha}"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--site", type=Path, help="built docs site to check")
    ap.add_argument("--version", help="expected version.json version (with --site)")
    ap.add_argument("--sha", help="expected version.json sha (with --site)")
    a = ap.parse_args()
    if a.site and not (a.version and a.sha):
        ap.error("--site needs --version and --sha")
    gaps = list(source_gaps())
    if a.site:
        gaps += list(site_gaps(a.site, a.version, a.sha))
    for g in gaps:
        print(g)
    print(f"{len(gaps)} gap(s) across {len(skills())} skills and {len(hooks())} hooks")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
