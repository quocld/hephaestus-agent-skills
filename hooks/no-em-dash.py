#!/usr/bin/env python3
"""PreToolUse hook: deny file writes whose new text contains an em dash (U+2014).

AGENTS.md bans the em dash; this makes the rule a gate instead of a reminder.
Reads the hook JSON on stdin and checks only the text being written, not what the file already holds.
"""
import json
import sys

EM_DASH = "\u2014"


def new_texts(tool_input):
    for key in ("content", "new_string", "new_source"):
        value = tool_input.get(key)
        if isinstance(value, str):
            yield value
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str):
            yield edit["new_string"]


def main():
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    if not isinstance(payload, dict):
        return 0
    tool_input = payload.get("tool_input") or {}
    if any(EM_DASH in text for text in new_texts(tool_input)):
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": "The new text contains an em dash (U+2014), which AGENTS.md bans. Rewrite it with a plain dash \"-\" or restructure the sentence, then retry.",
            }
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
