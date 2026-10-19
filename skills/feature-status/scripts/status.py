#!/usr/bin/env python3
"""Track the status of every feature in a repo, one file per feature, safe for parallel git worktrees.

Each feature lives in docs/status/<ID>.md; the exact format, tokens and transition table are in
the feature-status skill's references/format.md and in `status.py <subcommand> --help`.
The claim on a feature is the remote branch claim/<ID>, created atomically by `pick` together with the
feature branch, so every clone and worktree sees it after a fetch.

Subcommands: pick, set, ac, stale, defer, note, release, check, board.
Writing subcommands (set, ac, stale, defer, note) edit the file in the current feature worktree only and never commit.
Every writing subcommand takes --dry-run, which prints a unified diff and changes nothing.
Exit codes: 0 ok, 1 refused or not found, 2 usage error.
Python 3 standard library only.
"""
import argparse
import datetime
import difflib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile

STATUS_DIR = "docs/status"
KEYS = ("id", "title", "state", "branch", "picked_by", "picked_at", "updated_at", "pr", "spec")
STATES = ("picked", "in-progress", "in-review", "merged", "blocked", "deferred", "dropped")
TRANSITIONS = {
    "picked": ("in-progress", "blocked", "deferred", "dropped"),
    "in-progress": ("in-review", "blocked", "deferred", "dropped"),
    "in-review": ("in-progress", "merged", "blocked", "dropped"),
    "blocked": ("in-progress", "deferred", "dropped"),
    "deferred": ("in-progress", "dropped"),
    "merged": (),
    "dropped": (),
}
ACTIVE = ("picked", "in-progress", "in-review", "blocked")
RELEASABLE = ("merged", "dropped", "deferred")
REOPENABLE = ("deferred", "blocked")  # leaving these for an active state needs the claim
ABANDONED = ("deferred", "dropped")
TIERS = ("UT", "IT", "E2E")
RESULTS = ("todo", "pass", "fail", "stale", "na")
TYPES = ("feat", "fix", "refactor", "chore", "docs", "test")
SECTIONS = ("Acceptance criteria", "Deferred", "Notes")
NOTE_MAX = 200
LIVE_WINDOW = 30 * 60  # seconds: a worktree touched this recently may belong to a live session
EVIDENCE_FORMAT = ('the e2e-verify report: a non-empty JSON object with "id": "<ID>" and "verdict": "PASS", '
                   "written to e2e/reports/<ID>-<ISO>.json by the e2e-verify skill")
RESERVED_IDS = ("readme",)  # docs/status/README.md is documentation, skipped by check and board

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TICKET_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*-[0-9]+$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
AC_ID_RE = re.compile(r"^AC[1-9][0-9]*$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FM_LINE_RE = re.compile(r"^([a-z_]+):(?: (.*))?$")
AC_LINE_RE = re.compile(
    r"^- (?P<id>AC[0-9A-Za-z]*): (?P<text>[^|]*?) \| UT (?P<UT>\S+) \| IT (?P<IT>\S+) \| E2E (?P<E2E>\S+)"
    r"(?: \| evidence: (?P<evidence>\S.*))?$")
DEFER_LINE_RE = re.compile(r"^- (?P<what>.+?) - (?P<why>.+) - owner: (?P<owner>\S.*)$")
NOTE_LINE_RE = re.compile(r"^- (?P<date>\d{4}-\d{2}-\d{2}) (?P<text>\S.*)$")

FORMAT_HELP = """\
File docs/status/<ID>.md:
  ---
  id: <ID>
  title: <one line>
  state: picked|in-progress|in-review|merged|blocked|deferred|dropped
  branch: <type>/<ID>[-<slug>]
  picked_by: <git user.email or user.name>
  picked_at: <YYYY-MM-DDTHH:MM:SSZ>
  updated_at: <YYYY-MM-DDTHH:MM:SSZ>
  pr: <url or empty>
  spec: <path or link, optional>
  ---

  ## Acceptance criteria

  - AC1: <text without |> | UT <r> | IT <r> | E2E <r>[ | evidence: <repo-relative path>]

  ## Deferred

  - <what, without " - "> - <why> - owner: <who>

  ## Notes

  - <YYYY-MM-DD> <one line, at most 200 characters>

  <r> is one of todo, pass, fail, stale, na.
Transitions: picked -> in-progress|blocked|deferred|dropped; in-progress -> in-review|blocked|deferred|dropped;
  in-review -> in-progress|merged|blocked|dropped; blocked -> in-progress|deferred|dropped;
  deferred -> in-progress|dropped; merged and dropped allow nothing via set.
  A merged, dropped or deferred feature starts a new cycle with pick (after release); a spec change or failed QA
  after merge is: release, pick <ID> --slug <new-slug>, then stale in the new worktree.
  Reopening deferred or blocked work needs the claim/<ID> on origin to name this branch.
Exit codes: 0 ok, 1 refused or not found, 2 usage error (bad argument shape or combination).
"""


class Refused(Exception):
    """A rule refused the operation; exit 1 with the message."""


class Usage(Refused):
    """The arguments are malformed or do not go together; exit 2 with the message."""


def info(msg):
    print(msg, file=sys.stderr)


def now_ts():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def today():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------- git helpers

def run(args, cwd=None, env=None, input_text=None, check=True, timeout=None):
    proc = subprocess.run(args, cwd=cwd, env=env, input=input_text, capture_output=True, text=True,
                          errors="replace", timeout=timeout)
    if check and proc.returncode != 0:
        raise Refused(f"`{' '.join(args)}` failed: {(proc.stderr or proc.stdout).strip()}")
    return proc


def git(*args, cwd=None, env=None, input_text=None, check=True):
    return run(["git", *args], cwd=cwd, env=env, input_text=input_text, check=check).stdout.strip()


def git_ok(*args, cwd=None):
    return run(["git", *args], cwd=cwd, check=False).returncode == 0


def ref_exists(ref, cwd=None):
    return git_ok("rev-parse", "--verify", "-q", ref + "^{commit}", cwd=cwd)


def show_file(ref, path, cwd=None):
    """Text of <path> at <ref>, None when absent; Refused when it is not valid UTF-8."""
    proc = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=cwd, capture_output=True)
    if proc.returncode != 0:
        return None
    return decode(proc.stdout, f"{path} at {ref}")


def decode(data, where):
    """UTF-8 text; a leading byte order mark (from some editors) is dropped, so the next script edit removes it."""
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise Refused(f"{where} is not valid UTF-8 (byte {exc.start})") from None


def read_local(path, where):
    """Text of a working-tree file; Refused when it is not valid UTF-8 (OSError passes through)."""
    with open(path, "rb") as fh:
        return decode(fh.read(), where)


def toplevel():
    proc = run(["git", "rev-parse", "--show-toplevel"], check=False)
    if proc.returncode != 0:
        raise Refused("not inside a git repository")
    return proc.stdout.strip()


def is_linked_worktree(cwd=None):
    out = git("rev-parse", "--path-format=absolute", "--git-dir", "--git-common-dir", cwd=cwd).splitlines()
    return os.path.realpath(out[0]) != os.path.realpath(out[1])


def worktrees(cwd=None):
    """Return [(path, branch or '')] from `git worktree list --porcelain`, main checkout first."""
    result, path = [], None
    for line in git("worktree", "list", "--porcelain", cwd=cwd).splitlines():
        if line.startswith("worktree "):
            path = line[len("worktree "):]
            result.append([path, ""])
        elif line.startswith("branch ") and result:
            result[-1][1] = line[len("branch "):].replace("refs/heads/", "", 1)
    return [tuple(x) for x in result]


def current_branch(cwd=None):
    return git("branch", "--show-current", cwd=cwd)


def identity(cwd=None):
    who = git("config", "user.email", cwd=cwd, check=False) or git("config", "user.name", cwd=cwd, check=False)
    if not who:
        raise Refused("git user.email and user.name are both unset; configure your git identity first")
    return who


def fetch(cwd=None):
    git("fetch", "origin", "--prune", "--quiet", cwd=cwd)


def resolve_int(explicit, top):
    if explicit:
        if not ref_exists(f"refs/remotes/origin/{explicit}", cwd=top):
            raise Refused(f"origin/{explicit} does not exist")
        return explicit
    path = os.path.join(top, ".agents", "environments.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        envs = data.get("environments") if isinstance(data.get("environments"), dict) else data
        branch = (envs.get("dev") or {}).get("branch")
        if isinstance(branch, str) and branch:
            if not ref_exists(f"refs/remotes/origin/{branch}", cwd=top):
                raise Refused(f".agents/environments.json names dev branch {branch}, but origin/{branch} does not exist")
            return branch
    except (OSError, ValueError, AttributeError):
        pass
    if ref_exists("refs/remotes/origin/dev", cwd=top):
        return "dev"
    raise Refused("cannot find the integration branch (no .agents/environments.json dev.branch, no origin/dev); "
                  "ask which branch PRs go into and pass --int <branch>")


def validate_id(feature_id):
    if (not ID_RE.match(feature_id) or ".." in feature_id or feature_id.endswith(".")
            or feature_id.endswith(".lock")):
        raise Usage(f"invalid ID {feature_id!r}: use a ticket id (WEST-123) or a kebab slug, "
                      "matching [A-Za-z0-9][A-Za-z0-9._-]*, without '..'")
    if feature_id.lower() in RESERVED_IDS:
        raise Usage(f"invalid ID {feature_id!r}: docs/status/{feature_id}.md is reserved for documentation; "
                      "use the ticket id or another slug")
    return feature_id


def status_path(feature_id):
    return f"{STATUS_DIR}/{feature_id}.md"


def branch_matches(feature_id, branch):
    """True when `branch` is <type>/<ID> or <type>/<ID>-<slug>, so WEST-1 never accepts feat/WEST-12-other."""
    pattern = r"(?:%s)/%s(?:-\S+)?" % ("|".join(TYPES), re.escape(feature_id))
    return re.fullmatch(pattern, branch, re.IGNORECASE) is not None


# ---------------------------------------------------------------- the file format

class Status:
    def __init__(self):
        self.fm = {k: "" for k in KEYS}
        self.acs = []        # dicts: id, text, UT, IT, E2E, evidence
        self.deferred = []   # dicts: what, why, owner
        self.notes = []      # dicts: date, text

    def ac(self, ac_id):
        for item in self.acs:
            if item["id"] == ac_id:
                return item
        return None

    def render(self):
        out = ["---"]
        out += [f"{k}: {self.fm.get(k, '')}".rstrip() for k in KEYS]
        out += ["---", "", "## Acceptance criteria", ""]
        for a in self.acs:
            line = f"- {a['id']}: {a['text']} | UT {a['UT']} | IT {a['IT']} | E2E {a['E2E']}"
            if a.get("evidence"):
                line += f" | evidence: {a['evidence']}"
            out.append(line)
        if self.acs:
            out.append("")
        out += ["## Deferred", ""]
        out += [f"- {d['what']} - {d['why']} - owner: {d['owner']}" for d in self.deferred]
        if self.deferred:
            out.append("")
        out += ["## Notes", ""]
        out += [f"- {n['date']} {n['text']}" for n in self.notes]
        return "\n".join(out).rstrip("\n") + "\n"


def parse(text):
    """Parse a status file. Return (Status, problems); problems are human-readable strings."""
    st, problems = Status(), []
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        return st, ["missing frontmatter: the first line must be ---"]
    try:
        end = lines.index("---", 1)
    except ValueError:
        return st, ["frontmatter is not closed by a --- line"]
    seen = set()
    for n, line in enumerate(lines[1:end], start=2):
        m = FM_LINE_RE.match(line)
        if not m:
            problems.append(f"line {n}: frontmatter line is not 'key: value': {line!r}")
            continue
        key, value = m.group(1), (m.group(2) or "").strip()
        if key not in KEYS:
            problems.append(f"line {n}: unknown frontmatter key {key!r}")
        elif key in seen:
            problems.append(f"line {n}: duplicate frontmatter key {key!r}")
        else:
            st.fm[key] = value
        seen.add(key)
    for key in KEYS:
        if key not in seen:
            problems.append(f"frontmatter key {key!r} is missing")
    section, order = None, []
    for n, line in enumerate(lines[end + 1:], start=end + 2):
        if not line.strip():
            continue
        if line.startswith("## "):
            name = line[3:].strip()
            if name not in SECTIONS:
                problems.append(f"line {n}: unknown section {name!r}")
                section = "?"
            else:
                section = name
            order.append(name)
            continue
        if section is None:
            problems.append(f"line {n}: text outside a section: {line!r}")
            continue
        if section == "Acceptance criteria":
            m = AC_LINE_RE.match(line)
            if not m:
                problems.append(f"line {n}: AC line does not match '- ACn: <text> | UT <r> | IT <r> | E2E <r>[ | evidence: <path>]'")
                continue
            item = {k: m.group(k) for k in ("id", "text", "UT", "IT", "E2E")}
            item["evidence"] = (m.group("evidence") or "").strip()
            if not AC_ID_RE.match(item["id"]):
                problems.append(f"line {n}: AC id {item['id']!r} must be AC<number>")
            if st.ac(item["id"]):
                problems.append(f"line {n}: duplicate {item['id']}")
            for tier in TIERS:
                if item[tier] not in RESULTS:
                    problems.append(f"line {n}: {item['id']} has unknown {tier} result {item[tier]!r} "
                                    f"(use {', '.join(RESULTS)})")
            st.acs.append(item)
        elif section == "Deferred":
            m = DEFER_LINE_RE.match(line)
            if not m:
                problems.append(f"line {n}: Deferred line does not match '- <what> - <why> - owner: <who>'")
                continue
            st.deferred.append(m.groupdict())
        elif section == "Notes":
            m = NOTE_LINE_RE.match(line)
            if not m:
                problems.append(f"line {n}: Notes line does not match '- YYYY-MM-DD <one line>'")
                continue
            if len(m.group("text")) > NOTE_MAX:
                problems.append(f"line {n}: note longer than {NOTE_MAX} characters; put long reasoning in the PR")
            st.notes.append(m.groupdict())
    if order != list(SECTIONS):
        problems.append(f"sections must be exactly {', '.join('## ' + s for s in SECTIONS)} in that order")
    return st, problems


def evidence_problems(feature_id, evidence, top, head_check=False, ref=None):
    """Return (problems, warnings) for an E2E evidence path relative to the repo top.

    With `ref`, the evidence must be committed at that ref instead of existing in the working tree.
    """
    problems, warnings = [], []
    if not evidence:
        return [f"E2E pass needs an evidence file (--evidence <file>: {EVIDENCE_FORMAT}); there is no --force"], warnings
    if not evidence.lower().endswith(".json"):
        return [f"evidence {evidence} is not a .json file; E2E pass evidence must be {EVIDENCE_FORMAT}. "
                "A screenshot or log can go next to it, but it does not count as evidence"], warnings
    if ref is not None:
        norm = posixpath.normpath(evidence)
        if posixpath.isabs(evidence) or norm == ".." or norm.startswith("../"):
            return [f"evidence {evidence} is outside the repo"], warnings
        if not git_ok("cat-file", "-e", f"{ref}:{norm}", cwd=top):
            return [f"evidence file {evidence} is not committed at {ref}"], warnings
        read = lambda: show_file(ref, norm, top) or ""
    else:
        full = os.path.realpath(os.path.join(top, evidence))
        if os.path.commonpath([full, os.path.realpath(top)]) != os.path.realpath(top):
            return [f"evidence {evidence} is outside the repo"], warnings
        if not os.path.isfile(full):
            return [f"evidence file {evidence} does not exist"], warnings

        def read():
            with open(full, encoding="utf-8") as fh:
                return fh.read()
    try:
        text = read()
    except (OSError, ValueError, Refused) as exc:
        return [f"evidence {evidence} cannot be read: {exc}"], warnings
    if not text.strip():
        return [f"evidence {evidence} is empty; it must be {EVIDENCE_FORMAT}"], warnings
    try:
        data = json.loads(text)
    except ValueError as exc:
        return [f"evidence {evidence} is not valid JSON ({exc}); it must be {EVIDENCE_FORMAT}"], warnings
    if not isinstance(data, dict) or not data:
        return [f"evidence {evidence} is not a non-empty JSON object; it must be {EVIDENCE_FORMAT}"], warnings
    if data.get("verdict") != "PASS":
        problems.append(f"evidence {evidence} has verdict {data.get('verdict')!r}, not \"PASS\"")
    if str(data.get("id", "")).lower() != feature_id.lower():
        problems.append(f"evidence {evidence} has id {data.get('id')!r}, not {feature_id!r}")
    commit = data.get("commit")
    if head_check and isinstance(commit, str) and commit:
        if not git_ok("merge-base", "--is-ancestor", commit, "HEAD", cwd=top):
            warnings.append(f"warning: evidence commit {commit[:12]} is not an ancestor of HEAD; "
                            "the tested code may differ from this branch")
    return problems, warnings


def semantic_problems(st, feature_id, top, kinds=("meta", "evidence", "gate"), ref=None):
    """Rules beyond syntax, used by check and before every write.

    Kinds: meta (frontmatter), evidence (E2E pass proof), gate (state merged needs every AC done).
    """
    found = {"meta": [], "evidence": [], "gate": []}
    problems = found["meta"]
    fm = st.fm
    if fm["id"] != feature_id:
        problems.append(f"id {fm['id']!r} does not match the file name {feature_id!r}")
    if fm["state"] not in STATES:
        problems.append(f"unknown state {fm['state']!r} (use {', '.join(STATES)})")
    if not fm["title"]:
        problems.append("title is empty")
    if not fm["branch"]:
        problems.append("branch is empty")
    elif not branch_matches(feature_id, fm["branch"]):
        problems.append(f"branch {fm['branch']!r} is not <type>/{feature_id} or <type>/{feature_id}-<slug> "
                        f"(type one of {', '.join(TYPES)})")
    if not fm["picked_by"]:
        problems.append("picked_by is empty")
    for key in ("picked_at", "updated_at"):
        if not TS_RE.match(fm[key]):
            problems.append(f"{key} {fm[key]!r} is not YYYY-MM-DDTHH:MM:SSZ")
    if fm["pr"] and not re.fullmatch(r"https?://\S+", fm["pr"]):
        problems.append(f"pr {fm['pr']!r} is not a URL")
    for a in (st.acs if "evidence" in kinds else ()):
        if a["E2E"] == "pass":
            found["evidence"] += [f"{a['id']}: {p}" for p in evidence_problems(feature_id, a["evidence"], top, ref=ref)[0]]
    if fm["state"] == "merged":
        if not st.acs:
            found["gate"].append("state merged needs at least one AC")
        for a in st.acs:
            open_tiers = [f"{t} {a[t]}" for t in TIERS if a[t] not in ("pass", "na")]
            if open_tiers:
                found["gate"].append(f"state merged but {a['id']} has {', '.join(open_tiers)}")
    return [p for kind in kinds for p in found[kind]]


# ---------------------------------------------------------------- claims

def claim_status(feature_id, top):
    """(sha, Status or None) of origin/claim/<ID> as of the last fetch; (None, None) when there is no claim.

    The Status is None when the claim's status file is missing or does not parse.
    """
    ref = f"refs/remotes/origin/claim/{feature_id}"
    if not ref_exists(ref, top):
        return None, None
    sha = git("rev-parse", ref, cwd=top)
    try:
        text = show_file(ref, status_path(feature_id), top)
    except Refused:
        text = None
    if not text:
        return sha, None
    st, problems = parse(text)
    return sha, (None if problems else st)


def same_pick(a, b):
    """True when two versions of a status file come from the same pick (same branch and pick time)."""
    return a.fm["branch"] == b.fm["branch"] and a.fm["picked_at"] == b.fm["picked_at"]


def require_claim(feature_id, top, st, why):
    """Refuse unless claim/<ID> on origin (fetched now) belongs to this file's pick, so a reopen never runs unlocked."""
    fetch(top)
    sha, claim = claim_status(feature_id, top)
    if sha is None:
        raise Refused(f"{why} needs claim/{feature_id}, but it is gone from origin (released), so another agent may "
                      f"pick {feature_id}. Pick it again from the main checkout: status.py pick {feature_id} --slug "
                      f"<new-slug>, and merge this branch into the new worktree if its work is still needed")
    if claim is None or not same_pick(claim, st):
        holder = f"{claim.fm['picked_by']} on {claim.fm['branch']}" if claim else "an unreadable claim"
        raise Refused(f"{why} needs claim/{feature_id} for {st.fm['branch']}, but the claim now belongs to {holder}; "
                      "ask that holder before continuing")


# ---------------------------------------------------------------- writing in the feature worktree

def open_for_write(feature_id):
    top = toplevel()
    if not is_linked_worktree(top):
        raise Refused("this is the main checkout; status edits happen only inside the feature's worktree "
                      f"(run `status.py pick {feature_id}` from here to create it, or cd into it)")
    rel = status_path(feature_id)
    path = os.path.join(top, rel)
    if not os.path.isfile(path):
        raise Refused(f"{rel} not found in this worktree; run `status.py pick {feature_id}` first")
    old = read_local(path, rel)
    st, hard = parse(old)
    # Only syntax and frontmatter problems block an edit; a failing gate or missing evidence is what edits repair.
    hard = hard or semantic_problems(st, feature_id, top, kinds=("meta",))
    if hard:
        raise Refused(f"{rel} is invalid, fix it before editing:\n  " + "\n  ".join(hard))
    branch = current_branch(top)
    if branch != st.fm["branch"]:
        raise Refused(f"this worktree is on {branch or 'a detached HEAD'!r}, but {rel} belongs to branch "
                      f"{st.fm['branch']!r}; cd into that branch's worktree")
    return top, rel, path, old, st


def render_checked(st, rel):
    """Render and re-parse; refuse instead of writing a file the script itself could not edit again."""
    new = st.render()
    _, problems = parse(new)
    if not problems:
        problems = semantic_problems(st, st.fm["id"], None, kinds=("meta",))
    if problems:
        raise Refused(f"refusing to write {rel}, the result would be invalid:\n  " + "\n  ".join(problems))
    return new


def write_back(rel, path, old, st, dry_run):
    st.fm["updated_at"] = now_ts()
    new = render_checked(st, rel)
    if dry_run:
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                                   f"a/{rel}", f"b/{rel}"))
        return
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new)
    info(f"updated {rel}")


def one_line(text, what, limit=None):
    text = (text or "").strip()
    # splitlines() is what parse() uses, so it also catches \v, \f, \x1c-\x1e, \x85, U+2028 and U+2029.
    if not text or len(text.splitlines()) != 1:
        raise Refused(f"{what} must be a single non-empty line (no line breaks or line separators)")
    if limit and len(text) > limit:
        raise Refused(f"{what} is {len(text)} characters; the limit is {limit}. Put long reasoning in the PR "
                      "description or a flow-trace file and link it")
    return text


def add_note(st, text):
    st.notes.append({"date": today(), "text": one_line(text, "note", NOTE_MAX)})


def cmd_set(a):
    feature_id = validate_id(a.id)
    top, rel, path, old, st = open_for_write(feature_id)
    cur = st.fm["state"]
    if a.state != cur and a.state not in TRANSITIONS.get(cur, ()):
        allowed = ", ".join(TRANSITIONS.get(cur, ())) or "nothing via set (after release, a new pick starts a new cycle)"
        raise Refused(f"illegal transition {cur} -> {a.state}; from {cur} you can go to {allowed}")
    if a.state == cur and not (a.note or a.pr is not None):
        raise Refused(f"{feature_id} is already {cur}")
    if a.pr is not None:
        pr = one_line(a.pr, "--pr") if a.pr.strip() else ""
        if pr and not re.fullmatch(r"https?://\S+", pr):
            raise Refused(f"--pr {a.pr!r} is not a URL")
        st.fm["pr"] = pr
    if a.state != cur and a.state in ACTIVE and cur in REOPENABLE:
        require_claim(feature_id, top, st, f"{cur} -> {a.state}")
    st.fm["state"] = a.state
    if a.state == "merged":
        gate = semantic_problems(st, feature_id, top, kinds=("evidence", "gate"))
        if gate:
            raise Refused("cannot set merged:\n  " + "\n  ".join(gate))
    if a.state != cur:
        add_note(st, f"{cur} -> {a.state}" + (f": {a.note}" if a.note else ""))
    elif a.note:
        add_note(st, a.note)
    write_back(rel, path, old, st, a.dry_run)
    return 0


def cmd_ac(a):
    feature_id = validate_id(a.id)
    if not AC_ID_RE.match(a.ac):
        raise Usage(f"AC id {a.ac!r} must be AC<number>, for example AC3")
    if (a.tier is None) != (a.result is None):
        raise Usage("--tier and --result go together")
    if a.evidence and not (a.tier == "e2e" and a.result == "pass"):
        raise Usage("--evidence is only recorded with --tier e2e --result pass")
    top, rel, path, old, st = open_for_write(feature_id)
    item = st.ac(a.ac)
    added = item is None
    if added:
        if not a.text:
            raise Refused(f"{a.ac} does not exist yet; pass --text to add it")
        item = {"id": a.ac, "text": "", "UT": "todo", "IT": "todo", "E2E": "todo", "evidence": ""}
        st.acs.append(item)
        st.acs.sort(key=lambda x: int(x["id"][2:]))
    if a.text:
        text = one_line(a.text, "--text")
        if "|" in text:
            raise Refused("--text must not contain '|'")
        if not added and text != item["text"]:
            # A changed AC is a new criterion: every tier, na included, must be decided again.
            item.update({t: "todo" for t in TIERS})
            item["evidence"] = ""
            add_note(st, f"{a.ac} text changed, all tiers reset to todo")
            info(f"{a.ac} text changed: all tiers reset to todo; record each tier again (na included)")
        item["text"] = text
    if a.tier:
        tier = a.tier.upper()
        if tier == "E2E":
            if a.result == "pass":
                rel_ev = ""
                if a.evidence:
                    full = os.path.realpath(os.path.abspath(a.evidence))
                    rel_ev = os.path.relpath(full, os.path.realpath(top))
                problems, warnings = evidence_problems(feature_id, rel_ev, top, head_check=True)
                if problems:
                    raise Refused("evidence refused:\n  " + "\n  ".join(problems))
                for w in warnings:
                    info(w)
                item["evidence"] = rel_ev
        item[tier] = a.result
    write_back(rel, path, old, st, a.dry_run)
    return 0


def cmd_stale(a):
    feature_id = validate_id(a.id)
    top, rel, path, old, st = open_for_write(feature_id)
    ids = [x.strip() for x in a.acs.split(",") if x.strip()]
    if not ids:
        raise Usage("--acs needs at least one AC id")
    missing = [x for x in ids if st.ac(x) is None]
    if missing:
        raise Refused(f"unknown AC: {', '.join(missing)}")
    for x in ids:
        item = st.ac(x)
        for tier in TIERS:
            if item[tier] == "pass":
                item[tier] = "stale"
    if st.fm["state"] == "merged":
        raise Refused(f"{feature_id} is merged, so this pick is finished and stale cannot reopen it. For a spec change "
                      f"or failed QA after the merge: run `status.py release {feature_id}`, then from the main checkout "
                      f"`status.py pick {feature_id} --slug <new-slug>` (a new branch that keeps the ACs), then run "
                      f"`status.py stale {feature_id} --acs {a.acs}` in the new worktree")
    msg = f"stale {','.join(ids)}" + (f": {a.note}" if a.note else "")
    if st.fm["state"] == "in-review":
        require_claim(feature_id, top, st, f"reopening {st.fm['state']} work")
        msg = f"{st.fm['state']} -> in-progress (reopen), {msg}"
        st.fm["state"] = "in-progress"
    add_note(st, msg)
    write_back(rel, path, old, st, a.dry_run)
    return 0


def cmd_defer(a):
    feature_id = validate_id(a.id)
    top, rel, path, old, st = open_for_write(feature_id)
    what = one_line(a.what, "--what")
    why = one_line(a.why, "--why")
    owner = one_line(a.owner, "--owner")
    if " - " in what:
        raise Refused("--what must not contain ' - '")
    if " - owner: " in why:
        raise Refused("--why must not contain ' - owner: '")
    st.deferred.append({"what": what, "why": why, "owner": owner})
    write_back(rel, path, old, st, a.dry_run)
    return 0


def cmd_note(a):
    feature_id = validate_id(a.id)
    top, rel, path, old, st = open_for_write(feature_id)
    add_note(st, a.text)
    write_back(rel, path, old, st, a.dry_run)
    return 0


# ---------------------------------------------------------------- pick

def matching_branches(feature_id, top):
    """Local and origin branches that look like work on this ID, other than claim refs.

    A ticket id ends in digits, so <type>/<ID>-<slug> is unambiguous (WEST-1 never matches WEST-12-x).
    A slug ID has no such boundary (cart would match cart-total), so only a branch named exactly <type>/<ID> counts;
    the claim/<ID> ref, checked by name, is what protects slug IDs.
    """
    tail = r"(?:-|$)" if TICKET_RE.match(feature_id) else r"$"
    pattern = re.compile(r"(?:^|/)" + re.escape(feature_id) + tail, re.IGNORECASE)
    hits = []
    refs = git("for-each-ref", "--format=%(refname)", "refs/heads", "refs/remotes/origin", cwd=top).splitlines()
    for ref in refs:
        name = ref.replace("refs/heads/", "", 1).replace("refs/remotes/origin/", "origin/", 1)
        short = name[len("origin/"):] if name.startswith("origin/") else name
        if short == "HEAD" or short.lower().startswith("claim/"):
            continue
        if "/" in short and pattern.search(short):
            hits.append(name)
    return hits


def abandoned_status(feature_id, name, top):
    """The Status on branch `name` (local, or origin/<x>) when its own file gives it up (deferred or dropped), else None."""
    ref = f"refs/remotes/{name}" if name.startswith("origin/") else f"refs/heads/{name}"
    short = name[len("origin/"):] if name.startswith("origin/") else name
    try:
        text = show_file(ref, status_path(feature_id), top)
    except Refused:
        return None
    if not text:
        return None
    st, problems = parse(text)
    if problems or st.fm["id"] != feature_id or st.fm["branch"] != short or st.fm["state"] not in ABANDONED:
        return None
    return st


def stale_claim_hint(feature_id, top, int_branch, int_text, claim_st):
    """(hint, stale) explaining a claim whose own pick is already finished, instead of only naming its holder.

    stale is True when that pick is merged, dropped or deferred: then release is the only way forward.
    """
    if int_text:
        int_st, problems = parse(int_text)
        if not problems and same_pick(int_st, claim_st):
            state = int_st.fm["state"]
            if state in RELEASABLE:
                return (f". The claim is stale: {feature_id} is {state} on origin/{int_branch}; run "
                        f"`status.py release {feature_id}` (safe for anyone), then pick again"), True
            if state == "in-review":
                return (f". Its PR/MR has merged while the file said in-review (that file is on origin/{int_branch}); "
                        f"run the recovery in the feature-status skill (section 3), then `status.py release {feature_id}`"), False
    branch = claim_st.fm.get("branch", "")
    if branch:
        st = abandoned_status(feature_id, f"origin/{branch}", top)
        if st is not None and same_pick(st, claim_st):
            return (f". The claim is stale: {branch} is {st.fm['state']} on origin; run "
                    f"`status.py release {feature_id}`, then pick again"), True
    return "", False


def holder_of(text):
    if not text:
        return "", ""
    st, _ = parse(text)
    return st.fm.get("picked_by", ""), st.fm.get("state", "")


def worktree_for_branch(branch, top):
    for path, br in worktrees(top):
        if br == branch:
            return path
    return None


def worktree_dir(main, branch, root):
    base = root or os.path.join(os.path.dirname(main), os.path.basename(main) + ".worktrees")
    return os.path.join(os.path.abspath(base), branch.replace("/", "-"))


def cmd_pick(a):
    feature_id = validate_id(a.id)
    if a.takeover and not a.resume:
        raise Usage("--takeover only goes with --resume")
    top = toplevel()
    fetch(top)
    int_branch = resolve_int(a.int, top)
    me = identity(top)
    rel = status_path(feature_id)
    main = worktrees(top)[0][0]
    claim_ref = f"refs/remotes/origin/claim/{feature_id}"

    int_text = show_file(f"refs/remotes/origin/{int_branch}", rel, top)

    # Resume or refuse when someone holds the claim.
    if ref_exists(claim_ref, top):
        claim_text = show_file(claim_ref, rel, top)
        holder, _ = holder_of(claim_text)
        claim_st, _ = parse(claim_text or "")
        branch = claim_st.fm.get("branch", "")
        if not (a.resume and holder == me and branch):
            why, stale = stale_claim_hint(feature_id, top, int_branch, int_text, claim_st)
            # A stale claim is finished work: resuming it leads nowhere, so only release is suggested.
            hint = " (you hold it: pass --resume)" if holder == me and not stale else ""
            raise Refused(f"{feature_id} is already picked: claim/{feature_id} is held by {holder or 'unknown'} "
                          f"on branch {branch or '?'}{hint}{why}")
        return resume(a, top, main, branch, holder)

    prior = None
    if int_text is not None:
        prior, problems = parse(int_text)
        if prior.fm["state"] in ACTIVE:
            landed = (" In-review on the integration branch usually means its PR/MR merged before `set merged`; the "
                      "recovery in the feature-status skill (section 3) records it") if prior.fm["state"] == "in-review" else ""
            raise Refused(f"{rel} on origin/{int_branch} is {prior.fm['state']} (picked_by "
                          f"{prior.fm['picked_by'] or 'unknown'}); someone owns it. Ask before taking it over.{landed}")
        if problems:
            raise Refused(f"{rel} on origin/{int_branch} is invalid: {problems[0]}")
    hits = matching_branches(feature_id, top)
    if prior is not None and prior.fm["branch"]:
        # The finished feature's own branch (merged, dropped, deferred) does not block a re-pick.
        old = prior.fm["branch"]
        hits = [h for h in hits if h not in (old, f"origin/{old}")]
    # A branch whose own status file says deferred or dropped was given up (its claim is gone): it does not block,
    # and when <int> has no file, the newest such file is the prior one, so the re-pick keeps its ACs.
    abandoned = {h: st for h, st in ((h, abandoned_status(feature_id, h, top)) for h in hits) if st is not None}
    hits = [h for h in hits if h not in abandoned]
    if prior is None and abandoned:
        prior = max(abandoned.values(), key=lambda x: x.fm["updated_at"])
    if hits:
        raise Refused(f"branches for {feature_id} already exist: {', '.join(hits)}; another agent may be on it, "
                      "ask before picking")

    title = a.title or (prior.fm["title"] if prior else "")
    if not title:
        raise Refused("--title is required for a new feature")
    title = one_line(title, "--title")
    slug = a.slug
    if slug is None:
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40].rstrip("-") if TICKET_RE.match(feature_id) else ""
    if slug and not SLUG_RE.match(slug):
        raise Usage(f"--slug {slug!r} must be lowercase kebab case")
    branch = f"{a.type}/{feature_id}-{slug}" if slug else f"{a.type}/{feature_id}"
    if not git_ok("check-ref-format", f"refs/heads/{branch}"):
        raise Refused(f"{branch!r} is not a valid branch name")
    if ref_exists(f"refs/heads/{branch}", top) or ref_exists(f"refs/remotes/origin/{branch}", top):
        raise Refused(f"branch {branch} already exists (the earlier pick of {feature_id}); "
                      "pass --slug <new-slug> to name the new branch")
    wt = worktree_dir(main, branch, a.worktree_root)
    if not a.no_worktree and os.path.exists(wt):
        raise Refused(f"worktree path {wt} already exists")

    ts = now_ts()
    st = prior if prior else Status()
    old_text = int_text or (prior.render() if prior else "")
    st.fm.update({"id": feature_id, "title": title, "state": "picked", "branch": branch, "picked_by": me,
                  "picked_at": ts, "updated_at": ts, "pr": ""})
    if a.spec is not None:
        st.fm["spec"] = one_line(a.spec, "--spec") if a.spec.strip() else ""
    add_note(st, f"{'re-picked' if prior else 'picked'} by {me} on {branch}")
    content = render_checked(st, rel)
    if a.dry_run:
        sys.stdout.writelines(difflib.unified_diff(old_text.splitlines(True), content.splitlines(True),
                                                   f"a/{rel}" if prior else "/dev/null", f"b/{rel}"))
        info(f"dry run: would push claim/{feature_id} and {branch} atomically from origin/{int_branch}"
             + ("" if a.no_worktree else f" and add worktree {wt}"))
        return 0

    commit = make_commit(top, int_branch, rel, content, f"chore(status): [{feature_id}] pick")
    push = run(["git", "push", "--atomic", "--porcelain", "origin",
                f"--force-with-lease=refs/heads/claim/{feature_id}:",
                f"--force-with-lease=refs/heads/{branch}:",
                f"{commit}:refs/heads/claim/{feature_id}", f"{commit}:refs/heads/{branch}"],
               cwd=top, check=False)
    if push.returncode != 0:
        git("fetch", "origin", "--prune", "--quiet", cwd=top, check=False)
        said = (push.stderr or push.stdout).strip()
        taken = ref_exists(claim_ref, top) or ref_exists(f"refs/remotes/origin/{branch}", top)
        if not taken:
            raise Refused(f"the push of claim/{feature_id} and {branch} failed, and neither exists on origin, so "
                          f"nobody else holds {feature_id}; fix the cause git reports and rerun pick. "
                          f"Nothing was created. git said: {said}")
        try:
            holder, _ = holder_of(show_file(claim_ref, rel, top)) if ref_exists(claim_ref, top) else ("", "")
        except Refused:
            holder = ""
        raise Refused(f"lost the race for {feature_id}: the atomic push of claim/{feature_id} and {branch} was "
                      f"rejected" + (f"; it is now held by {holder}" if holder else "")
                      + f". Nothing was created. git said: {said}")
    info(f"picked {feature_id}: claim/{feature_id} and {branch} pushed at {commit[:12]} on top of origin/{int_branch}")
    if a.no_worktree:
        info(f"no worktree created; inside your worktree run: git switch -c {branch} --track origin/{branch}")
        print(branch)
        return 0
    add_worktree(top, wt, branch, commit, feature_id)
    info("worktree ready; cd into it:")
    print(wt)
    return 0


def add_worktree(top, wt, branch, start, feature_id):
    """Create the worktree on a new local branch tracking origin/<branch>.

    Runs after the claim is pushed, so a failure leaves no half-made local branch and says how to resume.
    """
    had_branch = ref_exists(f"refs/heads/{branch}", top)
    try:
        os.makedirs(os.path.dirname(wt), exist_ok=True)
        git("worktree", "add", "--quiet", "--no-track", "-b", branch, wt, start, cwd=top)
        git("branch", f"--set-upstream-to=origin/{branch}", branch, cwd=wt)
    except (Refused, OSError) as exc:
        if not had_branch and worktree_for_branch(branch, top) is None and ref_exists(f"refs/heads/{branch}", top):
            git("branch", "-D", branch, cwd=top, check=False)
        raise Refused(f"claim/{feature_id} and {branch} are pushed and held by you, but creating the worktree {wt} "
                      f"failed: {exc}. Fix that, then run `status.py pick {feature_id} --resume` to create it") from None


def last_activity(wt, feature_id):
    """(seconds since the newest change, file) among the worktree's private git index, HEAD and agent-progress.md
    and its status file; (None, None) when none of them exists."""
    paths = []
    gitdir = git("rev-parse", "--path-format=absolute", "--git-dir", cwd=wt, check=False)
    if gitdir:
        paths += [os.path.join(gitdir, name) for name in ("index", "HEAD", "agent-progress.md")]
    paths.append(os.path.join(wt, status_path(feature_id)))
    newest = None
    for path in paths:
        try:
            mtime = os.stat(path).st_mtime
        except OSError:
            continue
        if newest is None or mtime > newest[0]:
            newest = (mtime, path)
    if newest is None:
        return None, None
    return max(0, datetime.datetime.now().timestamp() - newest[0]), newest[1]


def refuse_if_live(a, existing, branch, holder):
    """Parallel agents share one git identity, so holding the claim does not mean the session that made it is gone."""
    age, path = last_activity(existing, a.id)
    if age is None or age >= LIVE_WINDOW or a.takeover:
        return
    raise Refused(f"claim/{a.id} is held by {holder} on {branch}, and its worktree {existing} changed "
                  f"{int(age // 60)} minute(s) ago ({path}), so another session may still be working there. "
                  f"Do not resume: ask the user whether that session is still running. Only after the user confirms "
                  f"it is dead, rerun with --resume --takeover")


def resume(a, top, main, branch, holder):
    existing = worktree_for_branch(branch, top)
    if existing:
        refuse_if_live(a, existing, branch, holder)
    if a.no_worktree:
        info(f"you hold the claim on {branch}; inside your worktree run: git switch -c {branch} --track origin/{branch}"
             f" (or git switch {branch} if it exists locally)")
        print(branch)
        return 0
    if existing:
        info(f"resuming: worktree for {branch} already exists")
        print(existing)
        return 0
    wt = worktree_dir(main, branch, a.worktree_root)
    if os.path.exists(wt):
        raise Refused(f"worktree path {wt} already exists but is not a worktree on {branch}")
    if a.dry_run:
        info(f"dry run: would resume by adding worktree {wt} on {branch}")
        print(wt)
        return 0
    if ref_exists(f"refs/heads/{branch}", top):
        os.makedirs(os.path.dirname(wt), exist_ok=True)
        git("worktree", "add", "--quiet", wt, branch, cwd=top)
        if (ref_exists(f"refs/remotes/origin/{branch}", top)
                and not git_ok("rev-parse", "--verify", "-q", f"{branch}@{{upstream}}", cwd=wt)):
            git("branch", f"--set-upstream-to=origin/{branch}", branch, cwd=wt)
    elif ref_exists(f"refs/remotes/origin/{branch}", top):
        add_worktree(top, wt, branch, f"origin/{branch}", a.id)
    else:
        raise Refused(f"you hold claim/{a.id} but branch {branch} exists neither locally nor on origin")
    info(f"resuming: worktree created for {branch}")
    print(wt)
    return 0


def make_commit(top, int_branch, rel, content, message):
    """Commit `content` at `rel` on top of origin/<int> with plumbing; the checkout's index and tree stay untouched."""
    tmp = tempfile.mkdtemp(prefix="status-index.")
    try:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
        base = f"refs/remotes/origin/{int_branch}"
        git("read-tree", base, cwd=top, env=env)
        blob = git("hash-object", "-w", "--stdin", cwd=top, input_text=content)
        git("update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}", cwd=top, env=env)
        tree = git("write-tree", cwd=top, env=env)
        return git("commit-tree", tree, "-p", base, "-m", message, cwd=top)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- release

def cmd_release(a):
    """Delete claim/<ID>, judged only by versions of the file from the claim's own pick.

    An older pick's merged file on <int> says nothing about a re-pick's live claim, so every source must match the
    claim's branch and picked_at, and the delete is leased on the claim commit that was judged.
    """
    feature_id = validate_id(a.id)
    top = toplevel()
    fetch(top)
    rel = status_path(feature_id)
    sha, claim = claim_status(feature_id, top)
    if sha is None:
        raise Refused(f"there is no claim/{feature_id} on origin")
    if claim is None:
        raise Refused(f"claim/{feature_id} has no valid {rel}, so its pick cannot be matched; ask the user before "
                      "deleting it by hand")
    int_branch = resolve_int(a.int, top)
    branch = claim.fm["branch"]
    sources = []
    int_text = show_file(f"refs/remotes/origin/{int_branch}", rel, top)
    if int_text:
        sources.append((f"origin/{int_branch}", int_text))
    if ref_exists(f"refs/remotes/origin/{branch}", top):
        text = show_file(f"refs/remotes/origin/{branch}", rel, top)
        if text:
            sources.append((f"origin/{branch}", text))
    elif os.path.isfile(os.path.join(top, rel)):
        sources.append(("this checkout", read_local(os.path.join(top, rel), rel)))
    ok, seen = None, []
    for where, text in sources:
        st, problems = parse(text)
        if problems:
            seen.append(f"invalid on {where}")
            continue
        state = st.fm["state"]
        if not same_pick(st, claim):
            seen.append(f"{state} on {where} from an earlier pick ({st.fm['branch']})")
            continue
        seen.append(f"{state} on {where}")
        # merged counts only once it is on <int>: a merged state on an unmerged branch means the PR is still open.
        if state in ABANDONED or (state == "merged" and where == f"origin/{int_branch}"):
            ok = where
            break
    if ok is None:
        landed = any(s_.startswith("in-review on origin/" + int_branch) for s_ in seen)
        hint = (f" Its PR/MR has merged while the file said in-review; run the recovery in the feature-status skill "
                f"(section 3) first.") if landed else ""
        raise Refused(f"refusing to release claim/{feature_id} (pick of {branch}): it needs that pick's file to be merged "
                      f"on origin/{int_branch} (the PR is merged), or dropped or deferred and pushed "
                      f"({', '.join(seen) or 'no status file found'}).{hint}")
    if a.dry_run:
        info(f"dry run: would delete claim/{feature_id} at {sha[:12]} (state read from {ok})")
        return 0
    push = run(["git", "push", "--quiet", "--porcelain", "origin",
                f"--force-with-lease=refs/heads/claim/{feature_id}:{sha}", f":refs/heads/claim/{feature_id}"],
               cwd=top, check=False)
    if push.returncode != 0:
        raise Refused(f"claim/{feature_id} changed on origin since it was checked (someone re-picked it?), so it was "
                      f"kept; rerun release to judge the new claim. git said: {(push.stderr or push.stdout).strip()}")
    info(f"released claim/{feature_id}")
    return 0


# ---------------------------------------------------------------- check

def cmd_check(a):
    top = toplevel()
    directory = os.path.join(top, STATUS_DIR)
    if a.ref is not None and a.ref.startswith("-"):
        raise Usage(f"--ref {a.ref!r} looks like an option; pass a branch or commit")
    if a.ref is not None and not ref_exists(a.ref, top):
        raise Refused(f"--ref {a.ref} is not a commit")
    if a.ids:
        ids = [validate_id(x) for x in a.ids]
    elif a.ref is not None:
        names = git("ls-tree", "--name-only", a.ref, f"{STATUS_DIR}/", cwd=top).splitlines()
        ids = sorted(posixpath.basename(n)[:-3] for n in names if n.endswith(".md") and not n.endswith("/README.md"))
    else:
        ids = sorted(f[:-3] for f in os.listdir(directory)
                     if f.endswith(".md") and f != "README.md") if os.path.isdir(directory) else []
    if a.base is not None:
        if a.base.startswith("-"):
            raise Usage(f"--base {a.base!r} looks like an option; pass a branch or commit")
        if not ref_exists(a.base, top):
            raise Refused(f"--base {a.base} is not a commit")
        changed = git("diff", "--name-only", "--end-of-options", f"{a.base}...HEAD", "--", STATUS_DIR,
                      cwd=top, check=True).splitlines()
        changed += git("diff", "--name-only", "HEAD", "--", STATUS_DIR, cwd=top).splitlines()
        changed += git("ls-files", "--others", "--exclude-standard", "--", STATUS_DIR, cwd=top).splitlines()
        keep = {os.path.basename(p)[:-3] for p in changed if p.endswith(".md")}
        ids = [x for x in ids if x in keep]
    bad = 0
    for feature_id in ids:
        rel = status_path(feature_id)
        try:
            if a.ref is not None:
                text = show_file(a.ref, rel, top)
            else:
                try:
                    text = read_local(os.path.join(top, rel), rel)
                except OSError:
                    text = None
        except Refused as exc:
            print(f"{rel}: {exc}")
            bad += 1
            continue
        if text is None:
            print(f"{rel}: not found" + (f" at {a.ref}" if a.ref is not None else ""))
            bad += 1
            continue
        try:
            validate_id(feature_id)
        except Refused as exc:
            print(f"{rel}: {exc}")
            bad += 1
            continue
        st, problems = parse(text)
        if not problems:
            problems = semantic_problems(st, feature_id, top, ref=a.ref)
        for p in problems:
            print(f"{rel}: {p}")
        bad += bool(problems)
    if bad:
        return 1
    info(f"ok: {len(ids)} status file(s) valid")
    return 0


# ---------------------------------------------------------------- board

def ac_counts(st):
    done = sum(1 for x in st.acs if all(x[t] in ("pass", "na") for t in TIERS))
    stale = sum(1 for x in st.acs if any(x[t] == "stale" for t in TIERS))
    return done, len(st.acs), stale


def collect(top, int_branch):
    """Return (items, invalid): items maps ID to (Status, source); invalid maps ID to (source, first problem)."""
    items, invalid = {}, {}

    def offer(read, source, fid_hint):
        try:
            text = read()
        except Refused as exc:
            invalid.setdefault(fid_hint, (source, str(exc)))
            return
        if not text:
            return
        st, problems = parse(text)
        fid = st.fm.get("id")
        if not problems and fid != fid_hint:
            problems = [f"id {fid!r} does not match the file name"]
        if problems:
            invalid.setdefault(fid_hint, (source, problems[0]))
            return
        cur = items.get(fid)
        if cur is None or st.fm["updated_at"] >= cur[0].fm["updated_at"]:
            items[fid] = (st, source)

    int_ref = f"refs/remotes/origin/{int_branch}"
    names = git("ls-tree", "--name-only", int_ref, f"{STATUS_DIR}/", cwd=top).splitlines()
    for name in names:
        if name.endswith(".md") and not name.endswith("/README.md"):
            offer(lambda: show_file(int_ref, name, top), f"origin/{int_branch}", posixpath.basename(name)[:-3])
    claims = git("for-each-ref", "--format=%(refname)", "refs/remotes/origin/claim/", cwd=top).splitlines()
    for ref in claims:
        fid = ref.rsplit("/", 1)[-1]
        rel = status_path(fid)
        try:
            text = show_file(ref, rel, top)
        except Refused as exc:
            invalid.setdefault(fid, (f"claim/{fid}", str(exc)))
            continue
        offer(lambda: text, f"claim/{fid}", fid)
        if text:
            branch = parse(text)[0].fm.get("branch")
            if branch and ref_exists(f"refs/remotes/origin/{branch}", top):
                offer(lambda: show_file(f"refs/remotes/origin/{branch}", rel, top), f"origin/{branch}", fid)
    return items, invalid


def live_pr(top, st, tool):
    target = st.fm["pr"] or st.fm["branch"]
    try:
        if tool == "gh":
            proc = run(["gh", "pr", "view", target, "--json", "state,url,mergeCommit"], cwd=top, check=False, timeout=20)
            if proc.returncode != 0:
                return None
            data = json.loads(proc.stdout)
            return {"state": data.get("state", "").lower(), "url": data.get("url", ""),
                    "merge": (data.get("mergeCommit") or {}).get("oid", "")}
        proc = run(["glab", "mr", "view", st.fm["branch"], "-F", "json"], cwd=top, check=False, timeout=20)
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout)
        return {"state": data.get("state", "").lower(), "url": data.get("web_url", ""),
                "merge": data.get("squash_commit_sha") or data.get("merge_commit_sha") or ""}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def env_versions(top, notes):
    """Run the `version` command of every service in .agents/environments.json that may run without asking."""
    path = os.path.join(top, ".agents", "environments.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        notes.append("deploy state skipped: no readable .agents/environments.json")
        return {}
    envs = data.get("environments") if isinstance(data.get("environments"), dict) else {}
    result = {}
    for name, env in envs.items():
        if not isinstance(env, dict) or name == data.get("defaultEnvironment", "dev") or name in ("dev", "local"):
            continue
        allowed = env.get("allowedWithoutAsking") or []
        for svc in env.get("services") or []:
            cmd = svc.get("version") if isinstance(svc, dict) else None
            if not cmd:
                continue
            if env.get("policy") == "confirm-each-step" and cmd not in allowed:
                notes.append(f"{name}/{svc.get('name')}: version not in allowedWithoutAsking, skipped")
                continue
            try:
                proc = run(["sh", "-c", cmd], cwd=top, check=False, timeout=20)
                sha = proc.stdout.strip().split()[0] if proc.returncode == 0 and proc.stdout.strip() else ""
            except (OSError, subprocess.SubprocessError):
                sha = ""
            if sha and ref_exists(sha, top):
                result.setdefault(name, []).append(sha)
            else:
                notes.append(f"{name}/{svc.get('name')}: version unknown")
    return result


def cmd_board(a):
    top = toplevel()
    proc = run(["git", "fetch", "origin", "--prune", "--quiet"], cwd=top, check=False)
    notes = [] if proc.returncode == 0 else ["fetch failed; board shows the last fetched state"]
    int_branch = resolve_int(a.int, top)
    items, invalid = collect(top, int_branch)
    for fid, (source, problem) in sorted(invalid.items()):
        notes.append(f"{status_path(fid)} on {source} is invalid: {problem}; run status.py check {fid} there and fix it "
                     "with the status.py subcommands")
    live = a.live
    tool = None
    versions = {}
    if live:
        url = git("remote", "get-url", "origin", cwd=top, check=False)
        tool = "glab" if "gitlab" in url else "gh"
        if not shutil.which(tool):
            notes.append(f"{tool} not installed: PR state skipped")
            tool = None
        versions = env_versions(top, notes)
    header = ["ID", "Title", "State", "Branch", "ACs done", "Stale", "PR", "Updated"]
    if live:
        header[7:7] = ["PR state", "Deployed"]
    rows = []
    for fid in sorted(items):
        st, _ = items[fid]
        done, total, stale = ac_counts(st)
        state = st.fm["state"]
        row = [fid, st.fm["title"].replace("|", "/"), state, st.fm["branch"], f"{done}/{total}", str(stale),
               st.fm["pr"], st.fm["updated_at"]]
        if live:
            pr = live_pr(top, st, tool) if tool else None
            pr_state = pr["state"] if pr else ""
            if pr and pr_state == "merged" and state != "merged":
                row[2] = f"{state} (PR merged)"
            if pr and not row[6]:
                row[6] = pr["url"]
            commit = (pr or {}).get("merge") or ""
            if not commit and ref_exists(f"refs/remotes/origin/{st.fm['branch']}", top) and pr_state == "merged":
                commit = git("rev-parse", f"refs/remotes/origin/{st.fm['branch']}", cwd=top)
            deployed = [env for env, shas in sorted(versions.items())
                        if commit and ref_exists(commit, top)
                        and all(git_ok("merge-base", "--is-ancestor", commit, s, cwd=top) for s in shas)]
            row[7:7] = [pr_state, ", ".join(deployed)]
        rows.append(row)
    for fid in sorted(set(invalid) - set(items)):
        rows.append([fid, "-", "invalid", "-", "-", "-", "-", "-"] + (["", ""] if live else []))
    rows.sort(key=lambda r: r[0])
    lines = [f"# Feature board (origin/{int_branch}, {now_ts()})", "",
             "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    if not rows:
        lines.append("| " + " | ".join(["-"] * len(header)) + " |")
    if notes:
        lines += [""] + [f"- {n}" for n in notes]
    out = "\n".join(lines) + "\n"
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(out)
        info(f"wrote {a.out}")
    else:
        sys.stdout.write(out)
    return 0


# ---------------------------------------------------------------- CLI

def parser():
    p = argparse.ArgumentParser(prog="status.py", description=__doc__.split("\n")[0],
                                epilog=FORMAT_HELP, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<subcommand>")

    def add(name, help_text, func):
        sp = sub.add_parser(name, help=help_text, description=help_text, epilog=FORMAT_HELP,
                            formatter_class=argparse.RawDescriptionHelpFormatter)
        sp.set_defaults(func=func)
        return sp

    sp = add("pick", "Claim a feature and create its branch and worktree; run it from any checkout before any "
             "worktree exists. Prints the worktree path (or the branch, with --no-worktree) as the only stdout line.",
             cmd_pick)
    sp.add_argument("id", help="ticket id (WEST-123) or kebab slug")
    sp.add_argument("--title", help="one-line title; required unless a status file already exists on <int>")
    sp.add_argument("--type", default="feat", choices=TYPES, help="branch type (default feat)")
    sp.add_argument("--slug", help="branch slug; default: from the title for ticket ids, none for slug ids")
    sp.add_argument("--spec", help="spec path or link to record")
    sp.add_argument("--int", help="integration branch (default: environments.json dev.branch, else dev)")
    sp.add_argument("--worktree-root", help="parent folder of worktrees (default: <main>/../<name>.worktrees)")
    sp.add_argument("--no-worktree", action="store_true", help="push the claim and branch only (harness worktrees)")
    sp.add_argument("--resume", action="store_true",
                    help="reuse a claim you already hold; refused while its local worktree changed in the last "
                         f"{LIVE_WINDOW // 60} minutes (another session may be live), recreates the worktree when it "
                         "does not exist locally")
    sp.add_argument("--takeover", action="store_true",
                    help="with --resume: resume although the worktree looks live; only after the user confirms the "
                         "other session is dead")
    sp.add_argument("--dry-run", action="store_true", help="print the status file diff; push and create nothing")

    sp = add("set", "Change the state (enforcing the transition table), and optionally the PR url.", cmd_set)
    sp.add_argument("id")
    sp.add_argument("state", choices=STATES)
    sp.add_argument("--note", help="one line recorded with the change")
    sp.add_argument("--pr", help="PR/MR url (empty string clears it)")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("ac", "Add an acceptance criterion or record one tier's result. E2E pass needs --evidence. "
             "Changing an existing AC's --text resets all its tiers to todo (na included) and notes it.", cmd_ac)
    sp.add_argument("id")
    sp.add_argument("ac", help="AC id, for example AC1")
    sp.add_argument("--text", help="AC text (required when adding)")
    sp.add_argument("--tier", choices=("ut", "it", "e2e"))
    sp.add_argument("--result", choices=RESULTS)
    sp.add_argument("--evidence", help="the e2e-verify JSON report inside the repo (any other file type is refused); "
                    "it must be a non-empty JSON object with verdict PASS and id equal to this ID")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("stale", "Mark passed tiers of ACs stale after a spec change; moves in-review work back to in-progress. "
             "Refused on a merged file: release, pick <ID> --slug <new-slug>, then stale in the new worktree.",
             cmd_stale)
    sp.add_argument("id")
    sp.add_argument("--acs", required=True, help="comma-separated AC ids, for example AC1,AC3")
    sp.add_argument("--note", help="one line: what changed in the spec")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("defer", "Record something deliberately left out.", cmd_defer)
    sp.add_argument("id")
    sp.add_argument("--what", required=True)
    sp.add_argument("--why", required=True)
    sp.add_argument("--owner", required=True)
    sp.add_argument("--dry-run", action="store_true")

    sp = add("note", f"Add a dated one-line note (at most {NOTE_MAX} characters).", cmd_note)
    sp.add_argument("id")
    sp.add_argument("text")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("release", "Delete claim/<ID> on origin once that pick's file is merged on <int> (the PR is merged), "
             "or dropped or deferred on <int> or on its pushed branch. Files from an earlier pick of the ID never count.",
             cmd_release)
    sp.add_argument("id")
    sp.add_argument("--int")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("check", "Validate status files (all of docs/status/*.md by default); one line per problem.", cmd_check)
    sp.add_argument("ids", nargs="*")
    mode = sp.add_mutually_exclusive_group()
    mode.add_argument("--base", help="only files changed since the merge base with this ref (for CI)")
    mode.add_argument("--ref", help="check the files and evidence committed at this ref instead of the working tree "
                      "(used by the PR hook)")

    sp = add("board", "Print a Markdown table of every feature on <int> and on unmerged claimed branches.", cmd_board)
    sp.add_argument("--int")
    sp.add_argument("--live", action="store_true", help="add PR state (gh/glab) and deploy state (environments)")
    sp.add_argument("--out", help="write the table to this file instead of stdout")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return args.func(args)
    except Usage as exc:
        info(f"status.py {args.cmd}: usage error: {exc}")
        return 2
    except Refused as exc:
        info(f"status.py {args.cmd}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
