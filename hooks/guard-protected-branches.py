#!/usr/bin/env python3
"""PreToolUse hook for Bash: ask the user before anything lands on a protected branch or merges a PR/MR.

worktree-flow says staging and prod change only on the user's explicit word, and agents never merge their own PR/MR.
A permission prompt is that explicit word, so this hook returns "ask" for:
- git push whose destination is a protected branch (explicit refspec, or no refspec while on one), or --all / --mirror;
- git merge while the current branch is protected;
- gh pr merge and glab mr merge, whatever the target (-R/--repo included);
- a push or merge whose repo directory cannot be resolved (a `cd` or `git -C` target with variables, or one that does not exist).
The current branch is read from the repo the command acts on: payload cwd, then any earlier `cd <dir>` in the command, then `git -C <dir>`.
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


def current_branch(directory):
    try:
        out = subprocess.run(["git", "-C", directory, "branch", "--show-current"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def resolve_dir(base, target):
    """Return the absolute directory `target` names relative to `base`, or UNRESOLVED."""
    if base is UNRESOLVED or not target or any(c in target for c in "$`*?") or target == "-":
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
        if token != "git":
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
        if token != cli:
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
        found = git_args(tokens, "merge", directory)
        if found is not None:
            repo = found[1]
            if repo is UNRESOLVED:
                yield "git merge in a directory this guard cannot resolve, so the current branch is unknown"
            else:
                branch = current_branch(repo)
                if branch in PROTECTED:
                    yield f"git merge into protected branch '{branch}'"
        if forge_merge(tokens, "gh", "pr"):
            yield "gh pr merge (agents never merge a PR without the user's word)"
        if forge_merge(tokens, "glab", "mr"):
            yield "glab mr merge (agents never merge an MR without the user's word)"


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    found = list(dict.fromkeys(reasons(command, os.path.abspath(payload.get("cwd") or "."))))
    if found:
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": "Protected-branch guard: " + "; ".join(found) + ". Approve only if you asked for this.",
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
