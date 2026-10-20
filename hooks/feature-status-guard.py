#!/usr/bin/env python3
"""PreToolUse hook: keep docs/status/<ID>.md honest in repos that use the feature-status skill.

A repo is opted in when docs/status/ exists at its top level, its AGENTS.md mentions feature-status,
or (for the Bash rules) the same holds on origin/<int>, read with git ls-tree and git show.
<int> is integrationBranch in .agents/environments.json, else the legacy dev environment's branch; for this opt-in
check only (never a PR target), origin/dev and origin/HEAD are also read, so an unrecorded repo is still guarded.
Repos that are not opted in are never blocked.

Rules, each a "deny" whose reason names the command to run instead:
1. Write/Edit/MultiEdit/NotebookEdit of a .md file under <top>/docs/status/ (README.md excepted, symlinks resolved,
   the docs/status part compared without case, as on macOS), and Bash commands that write one by hand: a > or >>
   redirect (also attached, x>file), sed -i, perl -i, awk -i inplace, tee, cp, mv, ln, install, truncate, dd of=,
   git checkout <ref> -- <path>, git restore --source, or python/node/perl/ruby -c/-e code that names the path and
   has a write signal (a w/a/x open mode, write, append, rename, unlink, remove, copy, move, >).
   Status files change only through status.py.
   The Bash part is best effort; arbitrary shell cannot be parsed completely, and a quoted string that merely
   contains x>docs/status/<ID>.md is also denied.
2. Bash `git worktree add`, `git switch -c/-C` or `git checkout -b/-B` that creates or checks out a branch
   <type>/<ID>-<slug>, unless claim/<ID> exists among the local origin refs (as of the last fetch; the hook never
   touches the network) or a docs/status/<ID>.md at the start point or the branch names that same branch and is
   active (picked, in-progress, in-review, blocked), or the branch's own ref holds it in any state:
   run status.py pick first, which creates the worktree itself.
   Creating a branch (-b/-c, not checking one out) is also denied when claim/<ID> exists but its status file (read
   from the local ref refs/remotes/origin/claim/<ID>) names a different branch: one ID, one branch.
   Branch names without a recognizable <type>/<ID> are out of scope.
   Rules 2 and 3 judge a branch only when its ID is a ticket id (TICKET_RE, WEST-12) or a claim/<ID> exists for it:
   a slug-only branch with no claim (fix/csv-export) is a small no-ticket change and passes.
3. Bash `gh pr create|new` / `glab mr create|new` from such a branch when docs/status/<ID>.md is missing on the
   branch, or (non-draft only) its state is not in-review or merged, `status.py check <ID> --ref <branch>` fails,
   or the local branch is ahead of its local upstream tracking ref (unpushed commits; fix: git push).
Commands are found like guard-protected-branches.py does: payload cwd, earlier `cd <dir>`, `git -C <dir>`,
and the strings run by `bash -c`, `sh -c`, `zsh -c` and `eval`; git, gh and glab are matched by basename.
A `cd` or `-C` target it cannot resolve (a variable other than $PWD or $(git rev-parse --show-toplevel), or a folder an
earlier segment creates) falls back to the payload cwd, whose repo shares refs with its worktrees; so in an opted-in
cwd such a command may be judged against the cwd's repo.
Fails open on bad input and when git fails.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
# Set from status_script() below: the copy shipped next to this hook (the plugin, or a checkout), else the legacy
# install.sh path, so deny messages always name a command that exists on this machine.
STATUS_CMD = "python3 <hephaestus>/skills/feature-status/scripts/status.py"
TYPES = ("feat", "fix", "refactor", "chore", "docs", "test")
BRANCH_RE = re.compile(r"^(?:refs/heads/|refs/remotes/origin/|origin/)?(%s)/([A-Za-z0-9][A-Za-z0-9._-]*)$" % "|".join(TYPES))
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TICKET_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+")
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READY_STATES = ("in-review", "merged")
ACTIVE_STATES = ("picked", "in-progress", "in-review", "blocked")
STATE_RE = re.compile(r"^state:\s*(\S+)\s*$", re.M)
BRANCH_FIELD_RE = re.compile(r"^branch:\s*(\S+)\s*$", re.M)
STATUS_PATH_RE = re.compile(r"(?:[^\s'\"`;|&<>()]*/)?docs/status/[^/\s'\"`;|&<>()]+\.md", re.I)
# A > or >> anywhere in a token: `> f`, `>f`, `2>f`, `&>f`, and `x>f` (shlex keeps a redirect glued to the word before it).
REDIRECT_RE = re.compile(r">>?[|&]?(.*)$")
# Interpreter code that names a status path counts as a write only with one of these; plain reads stay allowed.
WRITE_SIGNAL_RE = re.compile(r"""['"][rbt]*[wax+][rbtwax+]*['"]|write|append|rename|os\.replace|unlink|remove|\brm|"""
                             r"""truncate|copy|move|>|syswrite""", re.I)
INTERPRETERS = {"python", "python3", "node", "perl", "ruby"}


def load_guard():
    spec = importlib.util.spec_from_file_location("guard_protected_branches", os.path.join(HERE, "guard-protected-branches.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(directory, *args, timeout=5):
    """Return stdout of a git command, or None when it fails."""
    try:
        out = subprocess.run(["git", "-C", directory, *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout if out.returncode == 0 else None


def toplevel(directory):
    out = git(directory, "rev-parse", "--show-toplevel")
    return out.strip() if out else None


def integration_refs(top):
    """Candidate origin/<int> refs that exist locally, in worktree-flow order, then the guesses an unrecorded repo has."""
    names = []
    try:
        with open(os.path.join(top, ".agents", "environments.json")) as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = None
    if isinstance(data, dict):
        # Each read on its own: a malformed dev entry must not drop the recorded integrationBranch.
        envs = data.get("environments")
        dev = envs.get("dev") if isinstance(envs, dict) else None
        for branch in (data.get("integrationBranch"), dev.get("branch") if isinstance(dev, dict) else None):
            if isinstance(branch, str) and branch:
                names.append(branch)
    names.append("dev")
    head = git(top, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if head:
        names.append(head.strip().rsplit("refs/remotes/origin/", 1)[-1])
    refs = []
    for name in dict.fromkeys(names):
        if git(top, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}") is not None:
            refs.append(f"refs/remotes/origin/{name}")
    return refs


def mentions_skill(text):
    return text is not None and "feature-status" in text


def opted_in(top, remote=False):
    if os.path.isdir(os.path.join(top, "docs", "status")):
        return True
    try:
        with open(os.path.join(top, "AGENTS.md"), errors="replace") as f:
            if mentions_skill(f.read()):
                return True
    except OSError:
        pass
    if remote:
        for ref in integration_refs(top):
            if (git(top, "ls-tree", "-d", "--name-only", ref, "docs/status") or "").strip():
                return True
            if mentions_skill(git(top, "show", f"{ref}:AGENTS.md")):
                return True
    return False


def id_candidates(rest):
    """IDs a branch remainder `<ID>-<slug>` may start with, ticket-shaped first, then longest first."""
    cands = [rest[:i] for i, c in enumerate(rest) if c == "-"] + [rest]
    cands = sorted((c for c in cands if ID_RE.match(c) and ".." not in c), key=len, reverse=True)
    ticket = TICKET_RE.match(rest)
    return list(dict.fromkeys(([ticket.group(0)] if ticket else []) + cands))


def suggested_id(rest):
    ticket = TICKET_RE.match(rest)
    return ticket.group(0) if ticket else "<ID>"


def in_scope(top, rest):
    """Rules 2 and 3 judge a branch only when its ID is a ticket id or a claim/<ID> exists for it."""
    if TICKET_RE.match(rest):
        return True
    claims = local_claims(top)
    return any(c in claims for c in id_candidates(rest))


def status_file(top, ref, ident):
    """Text of docs/status/<ident>.md at ref, or None."""
    return git(top, "show", f"{ref}:docs/status/{ident}.md")


# ---------- rule 1: hand edits of status files ----------

def nearest_existing_dir(path):
    d = os.path.dirname(path)
    while d and not os.path.isdir(d):
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent
    return d or None


def status_target(path, cwd):
    """Return the status file name (WEST-1.md) when `path` is docs/status/<name>.md in an opted-in repo, else None."""
    if not isinstance(path, str) or not path.lower().endswith(".md"):
        return None
    path = os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))
    if os.path.lexists(path):
        path = os.path.realpath(path)  # a symlink to a status file is the status file
    start = nearest_existing_dir(path)
    top = toplevel(start) if start else None
    if not top:
        return None
    real = os.path.join(os.path.realpath(start), os.path.relpath(path, start))
    parts = os.path.relpath(real, os.path.realpath(top)).split(os.sep)
    # realpath keeps the caller's case on macOS, where Docs/Status/X.md is the same file as docs/status/X.md.
    if ([p.lower() for p in parts[:2]] != ["docs", "status"] or len(parts) != 3 or parts[2].lower() == "readme.md"
            or not opted_in(top)):
        return None
    return parts[2]


def hand_edit_reason(name, how):
    ident = os.path.splitext(name)[0]
    return (f"docs/status/{name} is written only by the feature-status script, never by hand ({how}). "
            f"Use {STATUS_CMD} <set|ac|stale|defer|note> {ident} ... (see --help), "
            f"or {STATUS_CMD} pick {ident} --title \"<title>\" from the main checkout to create it.")


def write_reason(tool_input, cwd):
    name = status_target(tool_input.get("file_path") or tool_input.get("notebook_path"), cwd)
    return hand_edit_reason(name, "a file-editing tool") if name else None


def strip_env(tokens):
    """Drop leading VAR=value assignments and `env`/`command`/`sudo` wrappers."""
    i = 0
    while i < len(tokens) and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[i]) or tokens[i] in ("env", "command", "sudo")):
        i += 1
    return tokens[i:]


def shell_write_reason(tokens, directory):
    """Rule 1 for Bash: a simple command that writes a status file without status.py."""
    if directory is None:
        return None
    targets = []
    for i, t in enumerate(tokens):
        m = REDIRECT_RE.search(t)
        if m and t[:1] != "<":
            targets.append(m.group(1) or (tokens[i + 1] if i + 1 < len(tokens) else ""))
    words = strip_env(tokens)
    cmd = os.path.basename(words[0]) if words else ""
    args = [w for w in words[1:]]
    positional = [w for w in args if not w.startswith("-")]
    if cmd in ("sed", "perl") and any(w == "--in-place" or w.startswith("--in-place=")
                                      or (w.startswith("-") and not w.startswith("--") and "i" in w) for w in args):
        targets += positional
    elif cmd in ("awk", "gawk") and any(w in ("-iinplace", "--include=inplace")
                                        or (w in ("-i", "--include") and args[j + 1:j + 2] == ["inplace"])
                                        for j, w in enumerate(args)):
        targets += positional
    elif cmd in ("tee", "truncate", "mv"):
        targets += positional
    elif cmd in ("cp", "install", "ln") and positional:
        targets.append(positional[-1])
    elif cmd == "dd":
        targets += [w[3:] for w in args if w.startswith("of=")]
    if cmd in INTERPRETERS or re.match(r"^python3(\.\d+)?$", cmd):
        for j, w in enumerate(args):
            if w in ("-c", "-e", "-E", "--eval", "-p", "-pe", "-ne") and j + 1 < len(args):
                if WRITE_SIGNAL_RE.search(args[j + 1]):
                    targets += STATUS_PATH_RE.findall(args[j + 1])
    for target in targets:
        name = status_target(target, directory)
        if name:
            return hand_edit_reason(name, f"Bash `{cmd or 'redirect'}`")
    return None


def git_path_write_reason(args, repo, sub):
    """Rule 1 for `git checkout <ref> -- <paths>` and `git restore --source <ref> <paths>`, which copy another ref's file.

    `git checkout -- <path>` and `git restore <path>` without a ref only drop uncommitted edits, so they stay allowed.
    """
    if repo is None:
        return None
    if sub == "checkout":
        new_branch, positional = parse_branch_args(args, ("-b", "-B", "--orphan"), ("--conflict", "--pathspec-from-file"))
        if new_branch is not None:
            return None
        if "--" in positional:
            k = positional.index("--")
            paths = positional[k + 1:] if positional[:k] else []
        else:
            paths = positional[1:]
    else:
        source, paths, i = False, [], 0
        while i < len(args):
            a = args[i]
            if a in ("-s", "--source"):
                source, i = True, i + 2
                continue
            if a.startswith("--source=") or (a.startswith("-s") and not a.startswith("--") and len(a) > 2):
                source = True
            elif a != "--" and not a.startswith("-"):
                paths.append(a)
            i += 1
        if not source:
            return None
    for path in paths:
        name = status_target(path, repo)
        if name:
            return hand_edit_reason(name, f"Bash `git {sub}` copying another ref's version")
    return None


# ---------- rule 2: worktree without a claim ----------

def local_claims(top):
    """IDs with a claim/<ID> among the local origin refs, which pick and worktree-flow refresh with git fetch.

    The hook never calls the network: a remote lookup would stall every matching command when offline.
    """
    out = git(top, "for-each-ref", "--format=%(refname)", "refs/remotes/origin/claim/") or ""
    return {line[len("refs/remotes/origin/claim/"):] for line in out.splitlines() if line.startswith("refs/remotes/origin/claim/")}


def parse_branch_args(args, create_flags, value_flags):
    """Return (new branch or None, positional args) for git worktree/switch/checkout args.

    create_flags take the new branch name, separated (-b x), attached (-bx) or with = (--create=x), also as the
    first create letter of a bundle of short flags (-qb x, -fbx), as git's option parser reads them;
    value_flags take a value that is not a positional.
    """
    short_create = {f[1] for f in create_flags if len(f) == 2}
    new_branch, positional, i = None, [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional.append(a)
            positional += args[i + 1:]
            break
        hit = False
        for f in create_flags:
            if a == f:
                new_branch, hit = (args[i + 1] if i + 1 < len(args) else None), True
                i += 2
                break
            if f.startswith("--") and a.startswith(f + "="):
                new_branch, hit = a.split("=", 1)[1], True
                i += 1
                break
            if not f.startswith("--") and a.startswith(f) and len(a) > len(f):
                new_branch, hit = a[len(f):], True
                i += 1
                break
        if not hit and re.match(r"^-[A-Za-z]{2,}", a):
            for k, c in enumerate(a[1:], start=1):
                if c in short_create:
                    rest = a[k + 1:]
                    new_branch, hit = (rest or (args[i + 1] if i + 1 < len(args) else None)), True
                    i += 1 if rest else 2
                    break
                if not c.isalpha():
                    break
        if hit:
            continue
        if a in value_flags:
            i += 2
            continue
        if not a.startswith("-"):
            positional.append(a)
        i += 1
    return new_branch, positional


def branch_ref_name(ref):
    for prefix in ("refs/heads/", "refs/remotes/origin/", "origin/"):
        if ref.startswith(prefix):
            return ref[len(prefix):]
    return ref


def claim_branch(top, ident):
    """The `branch` field of the status file on the local refs/remotes/origin/claim/<ident>, or None when unreadable."""
    text = status_file(top, f"refs/remotes/origin/claim/{ident}", ident)
    return (BRANCH_FIELD_RE.search(text) or [None, None])[1] if text else None


def claim_reason(top, btype, rest, start, verb, creating=False):
    """Rule 2 core: deny unless the branch is visibly claimed. `start` is the start point or None.

    When `creating` a branch, a claim on the ID that names a different branch is a second branch for one ticket:
    parallel agents share one git identity, so only the claim's own branch counts.
    """
    name = f"{btype}/{rest}"
    cands = id_candidates(rest)
    claimed = [c for c in cands if c in local_claims(top)]
    if claimed:
        branches = {c: claim_branch(top, c) for c in claimed}
        # An unreadable claim file fails open, as the hook does whenever it cannot tell.
        if not creating or any(b is None or b == name for b in branches.values()):
            return None
        ident, other = next(iter(branches.items()))
        return (f"{verb} {name}, but claim/{ident} belongs to branch {other}, so this would be a second branch for "
                f"{ident}. Work on {other} instead ({STATUS_CMD} pick {ident} --resume prints its worktree when the "
                f"claim is yours), or ask the user; never pick a second branch for the same ID.")
    if not TICKET_RE.match(rest):
        return None  # a slug-only branch with no claim is a small no-ticket change: plain worktree-flow
    refs = [r for r in dict.fromkeys((start, f"refs/heads/{name}", f"refs/remotes/origin/{name}")) if r]
    for ref in refs:
        own = branch_ref_name(ref) == name
        for ident in cands:
            text = status_file(top, ref, ident)
            if text is None:
                continue
            field = (BRANCH_FIELD_RE.search(text) or [None, None])[1]
            state = (STATE_RE.search(text) or [None, None])[1]
            # A file inherited from <int> (a merged WEST-1) proves nothing about a new branch for WEST-1;
            # it counts only when it names this branch and is active, or sits on this branch's own ref.
            if field == name and (state in ACTIVE_STATES or own):
                return None
    ident = suggested_id(rest)
    return (f"{verb} {name}, but there is no claim/{ident} among the origin refs (as of the last fetch) and no active "
            f"docs/status/{ident}.md for that branch, so other agents cannot see the work is taken. "
            f"From this checkout run {STATUS_CMD} pick {ident} --title \"<title>\" --type {btype} --slug <slug> instead; "
            f"it claims the ID, pushes the branch and creates the worktree itself (last stdout line is its path; "
            f"in a harness worktree add --no-worktree and switch to the branch it prints). "
            f"If someone just picked it, run git fetch origin --prune and retry.")


def ref_exists(top, ref):
    return git(top, "rev-parse", "--verify", "--quiet", ref + "^{commit}") is not None


def worktree_reason(args, repo):
    if not args or args[0] != "add" or repo is None:
        return None
    new_branch, positional = parse_branch_args(args[1:], ("-b", "-B", "--orphan"), ("--reason",))
    positional = [p for p in positional if p != "--"]
    commitish = positional[1] if len(positional) > 1 else None
    m = BRANCH_RE.match(new_branch or commitish or "")
    if not m:
        return None
    top = toplevel(repo)
    if not top or not opted_in(top, remote=True):
        return None
    return claim_reason(top, *m.groups(), commitish, "git worktree add would put work on", creating=new_branch is not None)


def switch_reason(args, repo, sub):
    """Rule 2 for `git switch -c/-C` and `git checkout -b/-B`, and for checking out an existing feature branch."""
    if repo is None:
        return None
    if sub == "switch":
        create, values = ("-c", "-C", "--create", "--force-create", "--orphan"), ("--conflict",)
    else:
        create, values = ("-b", "-B", "--orphan"), ("--conflict", "--pathspec-from-file")
    new_branch, positional = parse_branch_args(args, create, values)
    if "--" in positional:
        if sub == "checkout" and new_branch is None:
            return None  # git checkout [<ref>] -- <paths> restores files
        positional = positional[:positional.index("--")]
    top = toplevel(repo)
    if not top:
        return None
    if new_branch is not None:
        m = BRANCH_RE.match(new_branch)
        start = positional[0] if positional else None
    else:
        target = positional[0] if positional else ""
        m = BRANCH_RE.match(target)
        # Only a name that is a branch (a path argument to checkout is not); origin/<name> covers switch's DWIM.
        if not m or not any(ref_exists(top, r) for r in (f"refs/heads/{target}", f"refs/remotes/origin/{target}")):
            return None
        start = None
    if not m or not opted_in(top, remote=True):
        return None
    return claim_reason(top, *m.groups(), start, f"git {sub} would put work on", creating=new_branch is not None)


# ---------- rule 3: PR/MR without a ready status file ----------

def forge_create(tokens, cli, noun):
    """Return the args after `<cli> <noun> create`, skipping -R/--repo values, or None."""
    for i, token in enumerate(tokens):
        if os.path.basename(token) != cli:
            continue
        words = []
        j = i + 1
        while j < len(tokens) and len(words) < 2:
            if tokens[j] in ("-R", "--repo"):
                j += 2
                continue
            if not tokens[j].startswith("-"):
                words.append(tokens[j])
            j += 1
        if words in ([noun, "create"], [noun, "new"]):  # `new` is the documented alias in gh and glab
            return tokens[j:]
    return None


def flag_value(args, names):
    for i, a in enumerate(args):
        for n in names:
            if a == n and i + 1 < len(args):
                return args[i + 1]
            if n.startswith("--") and a.startswith(n + "="):
                return a.split("=", 1)[1]
            if not n.startswith("--") and len(n) == 2 and a.startswith(n) and len(a) > 2:
                return a[2:]  # attached short form, -Hfeat/x
    return None


def status_script():
    """FEATURE_STATUS_SCRIPT when set (tests), else the copy next to this hooks folder (the plugin or a checkout),
    else the legacy install.sh copy."""
    override = os.environ.get("FEATURE_STATUS_SCRIPT")
    if override is not None:
        return override if os.path.isfile(override) else None
    for path in (os.path.join(HERE, "..", "skills", "feature-status", "scripts", "status.py"),
                 os.path.expanduser("~/.claude/skills/feature-status/scripts/status.py")):
        if os.path.isfile(path):
            return os.path.realpath(path)
    return None


_shipped = status_script() if os.environ.get("FEATURE_STATUS_SCRIPT") is None else None
if _shipped:
    STATUS_CMD = f'python3 "{_shipped}"'


def run_check(top, ident, ref):
    """Return (ok, output) from `status.py check <ident> --ref <ref>`, or None when the script is absent or unusable.

    --ref makes it validate the committed file and committed evidence, which is what the PR/MR ships.
    """
    script = status_script()
    if not script:
        return None
    try:
        out = subprocess.run([sys.executable, script, "check", ident, "--ref", ref], cwd=top, capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode == 0:
        return True, ""
    if out.returncode == 1:
        return False, " ".join((out.stdout + out.stderr).split())[:600]
    return None


def pr_reason(args, repo, cli):
    if repo is None:
        return None
    head = flag_value(args, ("--head", "-H") if cli == "gh" else ("--source-branch", "-s"))
    if head and ":" in head:
        head = head.split(":", 1)[1]  # gh accepts <owner>:<branch>
    draft = any(a in ("--draft", "-d", "--wip") for a in args) if cli == "gh" else any(a in ("--draft", "--wip") for a in args)
    top = toplevel(repo)
    if not top:
        return None
    branch = head or (git(top, "branch", "--show-current") or "").strip()
    m = BRANCH_RE.match(branch)
    if not m or not opted_in(top, remote=True):
        return None
    btype, rest = m.groups()
    name = f"{btype}/{rest}"
    if not in_scope(top, rest):
        return None
    if head:
        ref = next((r for r in (f"refs/heads/{name}", f"refs/remotes/origin/{name}")
                    if git(top, "rev-parse", "--verify", "--quiet", r) is not None), None)
        if ref is None:
            return None
    else:
        ref = "HEAD"
    found = next(((i, t) for i, t in ((i, status_file(top, ref, i)) for i in id_candidates(rest)) if t is not None), None)
    noun = "PR" if cli == "gh" else "MR"
    if found is None:
        ident = suggested_id(rest)
        return (f"{name} has no committed docs/status/{ident}.md, so the {noun} would hide the feature from the board. "
                f"Commit docs/status/{ident}.md on this branch (it exists when the branch came from "
                f"{STATUS_CMD} pick {ident} --title \"<title>\"; with --resume when the claim is yours), then retry. "
                f"If this branch was made without pick, ask the user before opening the {noun}.")
    if draft:
        return None
    ident, text = found
    state = (STATE_RE.search(text) or [None, None])[1]
    if state not in READY_STATES:
        return (f"docs/status/{ident}.md on {name} is in state '{state}', and a ready {noun} needs in-review "
                f"(or merged, set by the last push before the merge). "
                f"Run {STATUS_CMD} set {ident} in-review in this worktree, commit and push it, then retry "
                f"(or open the {noun} with --draft).")
    checked = run_check(top, ident, ref)
    if checked is not None and not checked[0]:
        return (f"{STATUS_CMD} check {ident} fails: {checked[1]} "
                f"Fix it with the status.py subcommands it names, commit, then retry (or open the {noun} with --draft).")
    ahead = unpushed(top, name if head else None)
    if ahead:
        return (f"{name} has {ahead} commit(s) not pushed to its upstream (as of the local tracking ref), so the {noun} "
                f"would not show the status file and code checked here. Run git push, then retry.")
    return None


def unpushed(top, branch):
    """Commits on the local branch (None: HEAD) ahead of its local upstream tracking ref; 0 without an upstream."""
    target = f"refs/heads/{branch}" if branch else "HEAD"
    if branch and not ref_exists(top, target):
        return 0
    upstream = git(top, "rev-parse", "--verify", "--quiet", "--symbolic-full-name", f"{branch or ''}@{{upstream}}")
    if not upstream or not upstream.strip():
        return 0
    out = git(top, "rev-list", "--count", f"{upstream.strip()}..{target}")
    try:
        return int(out.strip()) if out else 0
    except ValueError:
        return 0


# ---------- dispatch ----------

def bash_reasons(guard, command, directory, depth=0, fallback=None):
    """Yield deny reasons. An unresolvable `cd`/`-C` target falls back to `fallback`, the payload cwd."""
    fallback = fallback or directory
    for tokens in guard.segments(command):
        if not tokens:
            continue
        if tokens[0] in ("cd", "pushd"):
            directory = guard.resolve_dir(directory, tokens[1] if len(tokens) > 1 else "~") or fallback
            continue
        if depth < 3:
            for script in guard.nested_scripts(tokens):
                yield from bash_reasons(guard, script, directory, depth + 1, fallback)
        r = shell_write_reason(tokens, directory)
        if r:
            yield r
        found = guard.git_args(tokens, "worktree", directory)
        if found is not None:
            r = worktree_reason(found[0], found[1] or directory)
            if r:
                yield r
        for sub in ("switch", "checkout", "restore"):
            found = guard.git_args(tokens, sub, directory)
            if found is not None:
                # `git -C <new worktree>` names a folder an earlier segment creates; it shares this repo's refs.
                repo = found[1] or directory
                r = git_path_write_reason(found[0], repo, sub) if sub != "switch" else None
                if r:
                    yield r
                r = switch_reason(found[0], repo, sub) if sub != "restore" else None
                if r:
                    yield r
        for cli, noun in (("gh", "pr"), ("glab", "mr")):
            args = forge_create(tokens, cli, noun)
            if args is not None:
                r = pr_reason(args, directory, cli)
                if r:
                    yield r


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0
    tool = payload.get("tool_name") or ("Bash" if "command" in tool_input else "Write")
    try:
        cwd = payload.get("cwd")
        cwd = os.path.abspath(cwd if isinstance(cwd, str) and cwd else ".")
        if tool in WRITE_TOOLS:
            found = [r for r in [write_reason(tool_input, cwd)] if r]
        elif tool == "Bash" and isinstance(tool_input.get("command"), str):
            found = list(dict.fromkeys(bash_reasons(load_guard(), tool_input["command"], cwd)))
        else:
            found = []
    except Exception:  # noqa: BLE001 - a broken guard must never block unrelated work
        return 0
    if found:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "Feature-status guard: " + " ".join(found),
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
