#!/usr/bin/env python3
"""Check cross-skill references in tracked Markdown, Python, and shell files, so a renumbered section or a renamed skill fails CI.

Checked forms, where `x` is a backticked name:
  `x` section N, `x` skill section N, `x`'s section N, `x` sections N and M, `x` sections N-M
      -> skills/x/SKILL.md has a "## N." heading (any depth of "#", suffixes like "1b" included).
  `x` section N step M, `x` section N steps M to K
      -> section N of x has a top-level numbered item for every step number.
  `x` step N, `x` steps N to M
      -> x has a "## N." heading; only a skill with no numbered heading falls back to a top-level numbered item "N.".
  x section N, the x skill (section N), x step N, with x unbackticked
      -> the same checks, but only when x is an existing skill folder name (script messages print bare names).
  the `x` skill, `x` skill, per `x`, `x` section N
      -> skills/x/ (or .claude/skills/x/) exists, unless the words just before it mark an outside skill ("its", "official", "built-in", "plugin"),
         or the name is followed by "(section N" (a command such as `pick` (section 1)).
Inside Markdown code fences only numbered references are checked (a fenced template is still shipped text), never unknown names.
"its section N" and other references without a skill name are out of scope.

Usage: python3 .github/scripts/check_skill_refs.py [repo-root]    prints file:line per broken reference, exit 1 on any.
       python3 .github/scripts/check_skill_refs.py --self-test     runs the embedded cases.
Python 3.9, stdlib only.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

NUM = r"\d+[a-z]?"
# A list of numbers: "3", "3 and 4", "1, 2, or 3", "1-2", "0 to 5", "2 through 4".
NUM_LIST = NUM + r"(?:\s*(?:,\s*(?:and\s+|or\s+)?|\s(?:and|or|to|through)\s|-|–)\s*" + NUM + r")*"
NAME = r"[a-z0-9][a-z0-9-]*"

# `x` [skill]['s][,] [(]section(s)|step(s) LIST [[,] step M]
SECTION_REF = re.compile(
    r"`(?P<name>" + NAME + r")`(?: skill)?(?:'s)?,? \(?(?P<kind>sections?|steps?) (?P<nums>" + NUM_LIST + r")"
    r"(?:,? steps? (?P<step>" + NUM_LIST + r"))?(?![\w-])"
)


def bare_ref(names):
    """The same shape as SECTION_REF for unbackticked names, limited to existing skill folders."""
    alt = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    return re.compile(
        r"(?<![\w`-])(?P<name>" + alt + r")(?: skill)?(?:'s)?,? \(?(?P<kind>sections?|steps?) (?P<nums>" + NUM_LIST + r")"
        r"(?:,? steps? (?P<step>" + NUM_LIST + r"))?(?![\w-])"
    )
# Other places a backticked name is used as a skill: "`x` skill" (not "`x` skills/"), "per `x`".
SKILL_WORD = re.compile(r"`(?P<name>" + NAME + r")`(?:'s)? skill\b(?!s?/)")
PER_NAME = re.compile(r"\b[Pp]er `(?P<name>" + NAME + r")`(?!/)")
# Words just before a name that say the skill lives outside this repo ("load its `logs-query` skill").
OUTSIDE = re.compile(r"\b(?:its|official|built-in|builtin|plugin's|plugin|external|upstream)\s+$", re.I)

HEADING = re.compile(r"^#{2,6} (" + NUM + r")\.(?:\s|$)")
TOP_ITEM = re.compile(r"^(" + NUM + r")\. ")
FENCE = re.compile(r"^\s*(```|~~~)")


def expand(nums):
    """'3 and 4' -> ['3', '4']; '0 to 5' and '1-2' -> both endpoints and every plain integer between them."""
    out = []
    parts = re.split(r"(\s*(?:,\s*(?:and\s+|or\s+)?|\s(?:and|or|to|through)\s|-|–)\s*)", nums)
    values, seps = parts[0::2], parts[1::2]
    for i, v in enumerate(values):
        out.append(v)
        if i < len(seps) and re.search(r"to|through|-|–", seps[i]):
            nxt = values[i + 1]
            if v.isdigit() and nxt.isdigit():
                out.extend(str(k) for k in range(int(v) + 1, int(nxt)))
    return out


class Skill:
    def __init__(self, text):
        self.sections = set()
        self.steps = {}  # section number (or None before the first numbered heading) -> set of top-level item numbers
        current = None
        in_fence = False
        for line in text.splitlines():
            if FENCE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            m = HEADING.match(line)
            if m:
                current = m.group(1)
                self.sections.add(current)
                continue
            if line.startswith("## "):
                current = None
                continue
            m = TOP_ITEM.match(line)
            if m:
                self.steps.setdefault(current, set()).add(m.group(1))

    def has_step(self, n):
        """A skill with numbered headings is addressed by them; loose list items count only when it has none."""
        if self.sections:
            return n in self.sections
        return any(n in s for s in self.steps.values())


def load_skills(root):
    """Plugin skills (skills/) and this repo's own skills (.claude/skills/), which are referenced the same way.
    A name in both resolves to skills/."""
    skills = {}
    for base in (root / ".claude" / "skills", root / "skills"):
        if base.is_dir():
            for d in sorted(base.iterdir()):
                if d.is_dir():
                    f = d / "SKILL.md"
                    skills[d.name] = Skill(f.read_text(encoding="utf-8")) if f.is_file() else None
    return skills


EXTS = (".md", ".py", ".sh")
SELF = Path(".github") / "scripts" / "check_skill_refs.py"


def markdown_files(root):
    """Tracked .md, .py, and .sh files when git can list them, otherwise every such file outside hidden, vendored, and build folders.

    This script is left out, since its docstring and self-test cases hold deliberately broken references."""
    files = []
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--"] + ["*" + e for e in EXTS],
                             capture_output=True, check=True).stdout.decode("utf-8")
        files = [root / p for p in out.split("\0") if p]
    except (OSError, subprocess.CalledProcessError):
        pass
    if not files:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("node_modules", "site", "__pycache__")]
            files.extend(Path(dirpath) / f for f in filenames if f.endswith(EXTS))
    return sorted(f for f in files if f.relative_to(root) != SELF)


COUNT = [0]  # numbered references seen, for the summary line


_BARE = {}


def check_line(line, skills, names=True):
    """Return a list of problem strings for one line; names=False (inside a code fence) checks only numbered references."""
    problems = []
    seen_names = set()
    key = tuple(sorted(skills))
    if key not in _BARE:
        _BARE[key] = bare_ref(skills) if skills else None

    def unknown(name, start):
        if not names or name in skills or name in seen_names:
            return
        if OUTSIDE.search(line[:start]):
            return
        seen_names.add(name)
        problems.append(f"`{name}` is used as a skill but skills/{name}/ does not exist")

    def resolve(m):
        COUNT[0] += 1
        name, kind, step = m.group("name"), m.group("kind"), m.group("step")
        if name not in skills:
            # "`pick` (section 1": a command's own section, not a skill reference.
            if not line[m.end("name") + 1:].lstrip().startswith("("):
                unknown(name, m.start())
            return
        sk = skills[name]
        if sk is None:
            problems.append(f"`{name}` has no SKILL.md")
            return
        for n in expand(m.group("nums")):
            if kind.startswith("section"):
                if n not in sk.sections:
                    problems.append(f"`{name}` section {n} does not exist (has {', '.join(sorted(sk.sections, key=_key)) or 'none'})")
                    continue
                have = sk.steps.get(n, set())
                missing = [s for s in (expand(step) if step else []) if s not in have]
                if missing:
                    problems.append(f"`{name}` section {n} step {', '.join(missing)} does not exist "
                                    f"(section {n} has steps {', '.join(sorted(have, key=_key)) or 'none'})")
            elif not sk.has_step(n):
                where = f"no '## {n}.' heading" if sk.sections else f"no '## {n}.' heading or numbered item '{n}.'"
                problems.append(f"`{name}` step {n} does not exist ({where})")

    for m in SECTION_REF.finditer(line):
        resolve(m)
    if _BARE[key] is not None:
        for m in _BARE[key].finditer(line):
            resolve(m)
    for rx in (SKILL_WORD, PER_NAME):
        for m in rx.finditer(line):
            unknown(m.group("name"), m.start())
    return problems


def _key(n):
    m = re.match(r"(\d+)(.*)", n)
    return (int(m.group(1)), m.group(2)) if m else (1 << 30, n)


def check(root):
    root = Path(root).resolve()
    skills = load_skills(root)
    if not skills:
        print(f"no skills/ folder under {root}", file=sys.stderr)
        return 2, []
    findings = []
    for f in markdown_files(root):
        if not f.is_file():
            continue
        is_md = f.suffix == ".md"
        in_fence = False
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if is_md and FENCE.match(line):
                in_fence = not in_fence
                continue
            for p in check_line(line, skills, names=not in_fence):
                findings.append(f"{f.relative_to(root)}:{i}: {p}")
    return (1 if findings else 0), findings


SELF_TEST_SKILLS = {
    "alpha": "# alpha\n\n## 0. Start\n\n## 1. Setup\n\n1. one\n2. two\n   3. nested, not a step\n\n## 1b. Extra\n\n## 2. Done\n"
             "\n## Notes\n\n5. loose item under an unnumbered heading\n",
    "delta": "# delta\n\n## Steps\n\n1. first\n2. second\n",
    "beta": "# beta\n\n## 1. Only\n\n```\n## 9. inside a fence\n```\n",
}
# (line, expected number of problems)
SELF_TEST_CASES = [
    ("See `alpha` section 1.", 0),
    ("See `alpha` skill section 2.", 0),
    ("See `alpha`'s section 0.", 0),
    ("See `alpha` sections 1 and 2.", 0),
    ("Run `alpha` (sections 1-2) first.", 0),
    ("See `alpha` section 3.", 1),
    ("See `alpha` sections 2 and 4.", 1),
    ("See `alpha` section 1 step 2.", 0),
    ("See `alpha` section 1 step 3.", 1),
    ("See `alpha` section 2 step 1.", 1),
    ("See `alpha` step 1b.", 0),
    ("See `alpha` steps 0 to 2.", 0),
    ("See `alpha` step 7.", 1),
    ("See `beta` section 9.", 1),
    ("Load the `gamma` skill.", 1),
    ("Load the `gamma` skill and the `gamma` skill again.", 1),
    ("Load its `gamma` skill.", 0),
    ("Do not use the built-in `gamma` skill.", 0),
    ("States per `alpha`.", 0),
    ("States per `gamma`.", 1),
    ("See `gamma` section 2.", 1),
    ("Run `git status` and `npm test` per `AGENTS.md`.", 0),
    ("Copy `alpha` skills/ into place.", 0),
    ("Its section 4 is out of scope.", 0),
    ("See `alpha` step 5.", 1),
    ("See `delta` step 2.", 0),
    ("See `delta` step 3.", 1),
    ("See `alpha` section 1 steps 1 and 2.", 0),
    ("See `alpha` section 1 steps 3 to 9.", 1),
    ("Run `pick` (section 1) first.", 0),
    ("Read alpha section 3 next.", 1),
    ("Read alpha section 2 and the alpha skill (section 1).", 0),
    ("Read alpha section 2, not alpha-x section 9 or gamma section 9.", 0),
]


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, text in SELF_TEST_SKILLS.items():
            (root / "skills" / name).mkdir(parents=True)
            (root / "skills" / name / "SKILL.md").write_text(text, encoding="utf-8")
        skills = load_skills(root)
        failed = 0
        # A repo-only skill under .claude/skills resolves like a plugin skill.
        (root / ".claude" / "skills" / "local").mkdir(parents=True)
        (root / ".claude" / "skills" / "local" / "SKILL.md").write_text("# local\n\n## 1. Do\n", encoding="utf-8")
        local = load_skills(root)
        ok = "local" in local and not check_line("per `local` section 1", local)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} .claude/skills: per `local` section 1 resolves")
        for line, want in SELF_TEST_CASES:
            got = check_line(line, skills)
            ok = len(got) == want
            failed += not ok
            print(f"{'ok  ' if ok else 'FAIL'} want {want} got {len(got)}  {line}" + ("" if ok else f"  {got}"))
        # End to end: file:line per broken ref and exit 1; inside a fence numbered refs are checked but unknown names
        # are not; .py files are scanned too.
        (root / "doc.md").write_text("fine `alpha` section 1\n```\n`alpha` section 8\nthe `gamma` skill\n```\n"
                                     "bad `alpha` section 5\n", encoding="utf-8")
        (root / "tool.py").write_text("print('see alpha section 0')\nprint('see alpha section 7')\n", encoding="utf-8")
        rc, findings = check(root)
        ok = (rc == 1 and len(findings) == 3 and findings[0].startswith("doc.md:3:")
              and findings[1].startswith("doc.md:6:") and findings[2].startswith("tool.py:2:"))
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} end to end: {findings}")
    print("self-test " + ("passed" if not failed else f"failed ({failed})"))
    return 1 if failed else 0


def main(argv):
    if argv[1:2] == ["--self-test"]:
        return self_test()
    if argv[1:2] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    root = argv[1] if len(argv) > 1 else Path(__file__).resolve().parents[2]
    rc, findings = check(root)
    for f in findings:
        print(f)
    if rc == 0:
        print(f"skill references: all {COUNT[0]} numbered references and every skill name resolve")
    elif rc == 1:
        print(f"skill references: {len(findings)} broken", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
