#!/usr/bin/env python3
"""PreToolUse hook: deny file writes that add an em dash (U+2014) on a line they change.

AGENTS.md bans the em dash; this makes the rule a gate instead of a reminder, limited to the lines a write changes.
A line counts as changed unless the same exact line already exists in what the write replaces:
- Edit: the lines of old_string; MultiEdit: the lines of each edit's own old_string.
- Write: the lines of the existing file; a new file is checked in full.
- NotebookEdit: the lines of every cell source in the existing notebook (the .ipynb JSON).
So unchanged em-dash lines copied into a replacement pass, while a touched line that keeps its em dash is denied.
When the existing file or notebook cannot be read, the new text is checked in full; bad input fails open.
"""
import json
import os
import sys

EM_DASH = "\u2014"
MAX_READ = 20 * 1024 * 1024


def lines_of(text):
    return text.splitlines() if isinstance(text, str) else []


def read_text(path):
    """Text of an existing file, or None when it does not exist, is too big, or cannot be read."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_READ:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, ValueError):
        return None


def notebook_lines(path):
    """Lines of every cell source in an existing notebook, or None when it cannot be read or parsed."""
    text = read_text(path)
    if text is None:
        return None
    try:
        cells = json.loads(text).get("cells") or []
    except (ValueError, AttributeError):
        return None
    out = []
    for cell in cells if isinstance(cells, list) else []:
        source = cell.get("source") if isinstance(cell, dict) else None
        if isinstance(source, list):
            source = "".join(s for s in source if isinstance(s, str))
        out += lines_of(source)
    return out


def resolve(path, cwd):
    if not isinstance(path, str) or not path:
        return None
    return os.path.normpath(os.path.join(cwd, os.path.expanduser(path)))


def pairs(tool_input, cwd):
    """Yield (new text, lines it replaces) for each piece of text the call writes."""
    if isinstance(tool_input.get("new_string"), str):
        yield tool_input["new_string"], lines_of(tool_input.get("old_string"))
    edits = tool_input.get("edits")
    for edit in edits if isinstance(edits, list) else []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            yield edit["new_string"], lines_of(edit.get("old_string"))
    if isinstance(tool_input.get("content"), str):
        path = resolve(tool_input.get("file_path"), cwd)
        yield tool_input["content"], lines_of(read_text(path) if path else None)
    if isinstance(tool_input.get("new_source"), str):
        path = resolve(tool_input.get("notebook_path"), cwd)
        yield tool_input["new_source"], (notebook_lines(path) if path else None) or []


def new_texts(tool_input):
    """Every piece of new text the call writes, MultiEdit edits included; the fallback checks these in full."""
    texts = [tool_input.get(k) for k in ("content", "new_string", "new_source")]
    edits = tool_input.get("edits")
    for edit in edits if isinstance(edits, list) else []:
        if isinstance(edit, dict):
            texts.append(edit.get("new_string"))
    return [t for t in texts if isinstance(t, str)]


def changed_em_dash_lines(tool_input, cwd):
    found = []
    for new, old in pairs(tool_input, cwd):
        if EM_DASH in new:
            old = set(old)
            found += [line for line in lines_of(new) if EM_DASH in line and line not in old]
    return found


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
    cwd = payload.get("cwd")
    try:
        cwd = cwd if isinstance(cwd, str) and cwd else os.getcwd()
        found = changed_em_dash_lines(tool_input, cwd)
    except Exception:  # noqa: BLE001 - a broken check must never block unrelated work
        found = [line for text in new_texts(tool_input) for line in lines_of(text) if EM_DASH in line]
    if found:
        sample = found[0].strip()
        sample = sample if len(sample) <= 120 else sample[:117] + "..."
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": (
                    f"{len(found)} line(s) you changed contain an em dash (U+2014), which AGENTS.md bans, "
                    f"for example: {sample!r}. Replace the em dash with a plain dash \"-\" on the lines you changed, "
                    "then retry. Unchanged lines that already have one are fine."),
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
