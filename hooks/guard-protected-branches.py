#!/usr/bin/env python3
"""PreToolUse hook for Bash: ask the user before anything lands on a protected branch or merges a PR/MR.

worktree-flow says staging and prod change only on the user's explicit word, and agents never merge their own PR/MR.
A permission prompt is that explicit word, so this hook returns "ask" for:
- git push whose destination is a protected branch (explicit refspec, or no refspec while on one), or --all / --mirror;
- git merge while the current branch is protected, unless it is `--ff-only` onto that branch's own remote counterpart
  (`origin/<branch>`, `refs/remotes/<remote>/<branch>`, `@{u}`, `@{upstream}`), which only brings in what the remote already has;
- git pull while the current branch is protected that names another branch (`git pull origin feature`) or a source that is
  not a configured remote (`git pull ../other main`); a bare `git pull` or one naming the current branch only syncs and passes;
- gh pr merge and glab mr merge, whatever the target (-R/--repo included);
- a push, merge or branch-naming pull whose repo directory cannot be resolved (a `cd` or `git -C` target with variables, or one that does not exist).
The current branch is read from the repo the command acts on: payload cwd, then any earlier `cd <dir>` in the command, then `git -C <dir>`.
`$PWD`, `${PWD}`, `$(pwd)` and `$(git rev-parse --show-toplevel)` (also in backticks, optionally followed by /<path>)
resolve to the directory they name; any other variable leaves the directory unresolved.
Known limit: a fetch that rewrites refs/remotes/origin/<branch> (`git fetch origin +feature:refs/remotes/origin/main`) or a
changed upstream makes a later `--ff-only` merge look like a sync; that takes a deliberate setup step, not a slip.
`git`, `gh` and `glab` are matched by basename, so /usr/bin/git counts.
Commands inside `bash -c`, `sh -c`, `zsh -c` and `eval` strings are scanned too.
Protected branches: main, master, staging, stage, prod, production.
"""
import json
import os
import re
import shlex
import subprocess
import sys

PROTECTED = {"main", "master", "staging", "stage", "prod", "production"}
SEPARATOR_CHARS = ";&|()\n"
FALLBACK_SEPARATORS = re.compile(r"\s*(?:&&|\|\||;|\||\n)\s*")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
GIT_VALUE_FLAGS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
REPO_FLAGS = {"-R", "--repo"}
UNRESOLVED = None
CURRENT_DIR_IDIOMS = ("$PWD", "${PWD}", "$(pwd)", "`pwd`")
TOPLEVEL_IDIOMS = ("$(git rev-parse --show-toplevel)", "`git rev-parse --show-toplevel`")


def current_branch(directory):
    try:
        out = subprocess.run(["git", "-C", directory, "branch", "--show-current"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def toplevel(directory):
    try:
        out = subprocess.run(["git", "-C", directory, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def resolve_dir(base, target):
    """Return the absolute directory `target` names relative to `base`, or UNRESOLVED."""
    if base is UNRESOLVED or not target or target == "-":
        return UNRESOLVED
    for idioms, value in ((TOPLEVEL_IDIOMS, lambda: toplevel(base)), (CURRENT_DIR_IDIOMS, lambda: base)):
        idiom = next((i for i in idioms if target == i or target.startswith(i + "/")), None)
        if idiom:
            root = value()
            if not root:
                return UNRESOLVED
            target = root + target[len(idiom):]
            break
    if any(c in target for c in "$`*?"):
        return UNRESOLVED
    path = os.path.normpath(os.path.join(base, os.path.expanduser(target)))
    return path if os.path.isdir(path) else UNRESOLVED


def branch_name(ref):
    ref = ref.lstrip("+")
    for prefix in ("refs/heads/", "refs/remotes/origin/"):
        if ref.startswith(prefix):
            ref = ref[len(prefix):]
    return ref


def segments(command):
    """Split a shell command into simple-command token lists, keeping quoted strings whole."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=SEPARATOR_CHARS)
        lexer.whitespace = " \t\r"
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        for part in FALLBACK_SEPARATORS.split(command):
            yield part.split()
        return
    current = []
    for token in tokens:
        if token and all(c in SEPARATOR_CHARS for c in token):
            if current:
                yield current
            current = []
        else:
            current.append(token)
    if current:
        yield current


def git_args(tokens, subcommand, directory):
    """Return (args after `git <subcommand>`, repo dir) or None, honouring -C and treating --git-dir/--work-tree as unresolved."""
    for i, token in enumerate(tokens):
        if os.path.basename(token) != "git":
            continue
        j = i + 1
        repo = directory
        while j < len(tokens) and tokens[j].startswith("-"):
            flag = tokens[j]
            if flag in GIT_VALUE_FLAGS:
                if flag == "-C":
                    repo = resolve_dir(repo, tokens[j + 1] if j + 1 < len(tokens) else "")
                elif flag in ("--git-dir", "--work-tree"):
                    repo = UNRESOLVED
                j += 2
            else:
                if flag.startswith(("--git-dir=", "--work-tree=")):
                    repo = UNRESOLVED
                j += 1
        if j < len(tokens) and tokens[j] == subcommand:
            return tokens[j + 1:], repo
    return None


def forge_merge(tokens, cli, noun):
    """True when tokens hold `<cli> ... <noun> ... merge`, skipping flags and -R/--repo values."""
    for i, token in enumerate(tokens):
        if os.path.basename(token) != cli:
            continue
        words = []
        j = i + 1
        while j < len(tokens) and len(words) < 2:
            if tokens[j] in REPO_FLAGS:
                j += 2
                continue
            if not tokens[j].startswith("-"):
                words.append(tokens[j])
            j += 1
        if words == [noun, "merge"]:
            return True
    return False


# Flags whose value may be the next token; attach-only ones (-S<key>, --recurse-submodules=<v>) must not be listed,
# or the branch after them would be skipped.
MERGE_VALUE_FLAGS = {"-m", "-F", "-s", "-X", "--strategy", "--strategy-option", "--file", "--into-name", "--cleanup"}
PULL_VALUE_FLAGS = MERGE_VALUE_FLAGS | {"--depth", "--deepen", "--shallow-since", "--shallow-exclude", "-j", "--jobs",
                                        "--upload-pack", "--negotiation-tip", "-o", "--server-option"}


def positionals(args, value_flags):
    """Return the non-flag arguments, skipping the values of flags that take one as a separate token."""
    out = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in value_flags:
            skip = True
            continue
        if not a.startswith("-"):
            out.append(a)
    return out


def remotes(directory):
    try:
        out = subprocess.run(["git", "-C", directory, "remote"], capture_output=True, text=True, timeout=5)
        return set(out.stdout.split())
    except (OSError, subprocess.SubprocessError):
        return set()


def is_own_upstream(ref, branch, directory):
    """True when git resolves `ref` to refs/remotes/<remote>/<branch> for a configured remote (origin/main, @{u}).
    Resolving through git means a local branch or tag named origin/main, which git prefers, does not count."""
    try:
        out = subprocess.run(["git", "-C", directory, "rev-parse", "--symbolic-full-name", ref, "--"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    full = out.stdout.split("\n", 1)[0].strip() if out.returncode == 0 else ""
    return any(full == f"refs/remotes/{r}/{branch}" for r in remotes(directory))


def merge_reason(args, repo):
    if repo is UNRESOLVED:
        return "git merge in a directory this guard cannot resolve, so the current branch is unknown"
    branch = current_branch(repo)
    if branch not in PROTECTED:
        return None
    targets = positionals(args, MERGE_VALUE_FLAGS)
    if "--ff-only" in args and targets and all(is_own_upstream(t, branch, repo) for t in targets):
        return None
    return f"git merge into protected branch '{branch}'"


def pull_reason(args, repo):
    refspecs = positionals(args, PULL_VALUE_FLAGS)[1:]
    if not refspecs:
        return None   # a bare pull only syncs the current branch with its own upstream
    if repo is UNRESOLVED:
        return "git pull of a named branch in a directory this guard cannot resolve, so the current branch is unknown"
    branch = current_branch(repo)
    if branch not in PROTECTED:
        return None
    source = positionals(args, PULL_VALUE_FLAGS)[0]
    if source not in remotes(repo):
        return f"git pull from '{source}', not a configured remote, into protected branch '{branch}'"
    for spec in refspecs:
        if branch_name(spec.split(":", 1)[0]) != branch:
            return f"git pull of '{spec}' into protected branch '{branch}'"
    return None


def push_reason(args, repo):
    if any(a in ("--all", "--mirror") for a in args):
        return "git push --all/--mirror can update protected branches"
    positional = []
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            skip = True
            continue
        if not a.startswith("-"):
            positional.append(a)
    refspecs = positional[1:]
    needs_branch = not refspecs or any(s.split(":", 1)[-1].lstrip("+") == "HEAD" for s in refspecs)
    if needs_branch and repo is UNRESOLVED:
        return "git push from a directory this guard cannot resolve, so the current branch is unknown"
    if not refspecs:
        branch = current_branch(repo)
        if branch in PROTECTED:
            return f"git push from protected branch '{branch}'"
        return None
    for spec in refspecs:
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        if dst.lstrip("+") == "HEAD":
            dst = current_branch(repo)
        if branch_name(dst) in PROTECTED:
            return f"git push to protected branch '{branch_name(dst)}'"
    return None


def nested_scripts(tokens):
    """Yield command strings run by `bash -c '...'`, `sh -lc '...'` or `eval ...`."""
    for i, token in enumerate(tokens):
        if os.path.basename(token) in SHELLS:
            j = i + 1
            while j < len(tokens) and tokens[j].startswith("-"):
                if "c" in tokens[j].lstrip("-") and not tokens[j].startswith("--") and j + 1 < len(tokens):
                    yield tokens[j + 1]
                    break
                j += 1
        elif token == "eval" and i + 1 < len(tokens):
            yield " ".join(tokens[i + 1:])


def reasons(command, directory, depth=0):
    for tokens in segments(command):
        if not tokens:
            continue
        if tokens[0] in ("cd", "pushd"):
            directory = resolve_dir(directory, tokens[1] if len(tokens) > 1 else "~")
            continue
        if depth < 3:
            for script in nested_scripts(tokens):
                yield from reasons(script, directory, depth + 1)
        found = git_args(tokens, "push", directory)
        if found is not None:
            r = push_reason(*found)
            if r:
                yield r
        for subcommand, check in (("merge", merge_reason), ("pull", pull_reason)):
            found = git_args(tokens, subcommand, directory)
            if found is not None:
                r = check(*found)
                if r:
                    yield r
        if forge_merge(tokens, "gh", "pr"):
            yield "gh pr merge (agents never merge a PR without the user's word)"
        if forge_merge(tokens, "glab", "mr"):
            yield "glab mr merge (agents never merge an MR without the user's word)"


NO_PROMPT_MODES = {"bypassPermissions", "dontAsk"}


def allowed_branches(cwd):
    """Branches the user opted out of the guard for this repo: git config agentguard.allow <branch> (repeatable)."""
    try:
        out = subprocess.run(["git", "-C", cwd, "config", "--get-all", "agentguard.allow"],
                             capture_output=True, text=True, timeout=5)
        return {b.strip() for b in out.stdout.split() if b.strip()}
    except (OSError, subprocess.SubprocessError):
        return set()


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    cwd = payload.get("cwd")
    if not isinstance(command, str) or (cwd is not None and not isinstance(cwd, str)):
        return 0   # malformed input fails open; a missing cwd falls back to the hook's own directory
    cwd = os.path.abspath(cwd or ".")
    found = list(dict.fromkeys(reasons(command, cwd)))
    allow = allowed_branches(cwd)
    found = [r for r in found if not any(f"'{b}'" in r for b in allow)]
    if not found:
        return 0
    reason = "Protected-branch guard: " + "; ".join(found) + "."
    if payload.get("permission_mode") in NO_PROMPT_MODES:
        decision = "deny"
        reason += (" This permission mode shows no prompt, so the guard denies instead of asking."
                   " If the user explicitly asked for this, tell them to run it themselves with `! <command>`")
        # agentguard.allow only lifts reasons that name a branch; a PR/MR merge never names one.
        if any("branch '" in r for r in found):
            reason += ", or to opt this repo out with `git config agentguard.allow <branch>`; never set that yourself."
        else:
            reason += "; `git config agentguard.allow` does not cover PR/MR merges."
    else:
        decision = "ask"
        reason += " Approve only if you asked for this."
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
