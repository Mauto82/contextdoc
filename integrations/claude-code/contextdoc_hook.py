#!/usr/bin/env python3
"""ContextDoc hook for Claude Code (PreToolUse on Read, Edit and Write). Standard library only.

Agents read .ctx files only when an instructions file tells them to, and they don't always do it.
This hook hands the context over without asking:

- Read / Edit / Write of a source file with a .ctx companion: project.ctx and the file's .ctx are added
  to Claude's context (once per session and .ctx version; afterwards a one-line reminder).
- Edit / Write of a .ctx that changes its conceptualTests: the user is asked to approve, because
  conceptualTests are the specification and an agent must never change them to fit its code.

Install: see integrations/claude-code/README.md. The hook never blocks on errors: if anything goes
wrong it exits 0 without output and Claude Code carries on as if it weren't there.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile

MAX_CONTEXT_CHARS = 9000  # Claude Code moves longer additionalContext to a file
TOP_LEVEL_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\s*:")


def conceptual_tests_section(text: str) -> str:
    """The conceptualTests block of a .ctx (from its key to the next top-level key), comments dropped."""
    lines, inside = [], False
    for line in text.splitlines():
        if TOP_LEVEL_KEY.match(line):
            inside = line.split(":", 1)[0].strip() == "conceptualTests"
        if inside and not line.lstrip().startswith("#"):
            lines.append(line.rstrip())
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def find_project_ctx(start_dir: str, project_dir: str) -> str | None:
    """project.ctx in the file's folder or the nearest parent, without leaving the project."""
    project_dir = os.path.abspath(project_dir)
    d = os.path.abspath(start_dir)
    while True:
        candidate = os.path.join(d, "project.ctx")
        if os.path.isfile(candidate):
            return candidate
        if d == project_dir or os.path.dirname(d) == d or not d.startswith(project_dir):
            return None
        d = os.path.dirname(d)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def already_given(session_id: str, key: str) -> bool:
    """True if KEY was already injected in this session (state in the temp folder)."""
    folder = os.path.join(tempfile.gettempdir(), "contextdoc-hook")
    os.makedirs(folder, exist_ok=True)
    state_file = os.path.join(folder, hashlib.sha256(session_id.encode()).hexdigest()[:16] + ".json")
    try:
        seen = set(json.loads(read(state_file)))
    except (OSError, ValueError):
        seen = set()
    if key in seen:
        return True
    seen.add(key)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)
    return False


def output(**fields) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", **fields}}))


def edit_of_ctx(tool: str, tool_input: dict, path: str) -> None:
    """Asks the user before conceptualTests change; any other .ctx edit goes through."""
    try:
        current = read(path)
    except OSError:
        return  # a new .ctx: writing a spec for the first time is fine
    if tool == "Write":
        new = tool_input.get("content", "")
    else:
        old_s, new_s = tool_input.get("old_string", ""), tool_input.get("new_string", "")
        if not old_s or old_s not in current:
            return
        new = current.replace(old_s, new_s) if tool_input.get("replace_all") else current.replace(old_s, new_s, 1)
    if conceptual_tests_section(current) == conceptual_tests_section(new):
        return
    output(
        permissionDecision="ask",
        permissionDecisionReason=(
            f"ContextDoc: this edit changes the conceptualTests of {os.path.basename(path)}. "
            "They are the specification: approve only if the requirement changed, not to make code pass."
        ),
        additionalContext=(
            "ContextDoc: conceptualTests are the specification. Never change them to make your code pass; "
            "if the code cannot satisfy a test, report the conflict and ask the user."
        ),
    )


def context_for_source(path: str, project_dir: str, session_id: str) -> None:
    ctx_path = path + ".ctx"
    project_ctx = find_project_ctx(os.path.dirname(path), project_dir)
    files = [p for p in (project_ctx, ctx_path) if p and os.path.isfile(p)]
    if not os.path.isfile(ctx_path):
        files = []  # project.ctx alone is given once, with the first documented file
    if not files:
        return
    rel = os.path.relpath(path, project_dir)
    version = hashlib.sha256("".join(read(p) for p in files).encode()).hexdigest()[:12]
    if already_given(session_id, f"{ctx_path}:{version}"):
        output(additionalContext=(
            f"ContextDoc: {rel} has a .ctx (given earlier in this session): respect its tensions; "
            "its conceptualTests are the spec, never modify them to fit the code."
        ))
        return
    parts = [
        f"ContextDoc context for {rel}. Respect the tensions (decisions that look wrong but are intentional); "
        "the conceptualTests are the specification: adapt the code to them, never the other way round, "
        "and ask the user if they cannot be satisfied. Update the .ctx if you change behavior it describes.",
    ]
    for p in files:
        parts.append(f"\n--- {os.path.relpath(p, project_dir)} ---\n{read(p).strip()}")
    text = "\n".join(parts)
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[:MAX_CONTEXT_CHARS] + "\n[... truncated: read the .ctx files for the rest]"
    output(additionalContext=text)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path")
    if tool not in ("Read", "Edit", "Write") or not path:
        return
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    path = os.path.abspath(os.path.join(event.get("cwd") or project_dir, path))
    if path.endswith(".ctx"):
        if tool in ("Edit", "Write"):
            edit_of_ctx(tool, tool_input, path)
        return
    context_for_source(path, project_dir, event.get("session_id", "no-session"))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — a broken hook must never block the agent
        pass
    sys.exit(0)
