# ContextDoc for Claude Code

A `PreToolUse` hook that hands ContextDoc context to Claude Code without relying on instructions,
and protects `conceptualTests`. Python 3, standard library only.

| When Claude… | The hook |
|---|---|
| reads, edits or writes a source file that has a `.ctx` | adds `project.ctx` and the file's `.ctx` to Claude's context (once per session and `.ctx` version; afterwards a one-line reminder) |
| writes a source file that doesn't exist yet but has a `.ctx` (intent-first) | gives the spec before the code is written |
| edits or rewrites a `.ctx` in a way that changes its `conceptualTests` | asks **you** to approve: they are the specification, and an agent must never change them to fit its code |
| touches anything else | stays silent |

It never blocks on errors: if something goes wrong it exits without output and Claude Code carries on.

## Install

Copy `contextdoc_hook.py` into your project (e.g. `.claude/hooks/`) and add to `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/contextdoc_hook.py\"",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

## MCP server

For agents other than Claude Code (or alongside the hook), [`tools/ctx-mcp`](../../tools/ctx-mcp/) exposes the same
context as MCP tools: `get_context`, `list_tensions`, `list_scenarios`, `check_drift`.

## Tests

`python -m pytest -q` in this folder: the hook is fed the JSON Claude Code sends to a `PreToolUse` hook.
