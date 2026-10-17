# ctx-mcp

MCP server that exposes a project's ContextDoc files to any MCP-capable agent (Claude Code, Claude Desktop,
Cursor, …). Read-only, confined to the project folder.

| Tool | Returns |
|---|---|
| `get_context(file_path)` | `project.ctx` and the file's `.ctx`: read it before changing the file |
| `list_tensions(path=".")` | every tension in the `.ctx` files under `path` |
| `list_scenarios(path=".")` | the `conceptualTests` under `path`, the specification |
| `check_drift(path=".")` | source files that changed after their `.ctx` (git history, as `ctx-watch status`) |

The server also sends agents a short instruction: call `get_context` before editing, and never modify
`conceptualTests` to make code pass.

## Install

```bash
pip install -r tools/ctx-mcp/requirements.txt
```

Claude Code, from the project root:

```bash
claude mcp add --transport stdio contextdoc -- python /path/to/contextdoc/tools/ctx-mcp/ctx_mcp.py
```

or a project `.mcp.json`:

```json
{
  "mcpServers": {
    "contextdoc": {
      "command": "python",
      "args": ["/path/to/contextdoc/tools/ctx-mcp/ctx_mcp.py", "--root", "."]
    }
  }
}
```

The server uses `ctx-watch` from the same checkout for drift detection. Works with the `mcp` SDK 1.x and 2.x.

## Tests

`python -m pytest -q` in this folder, including a round trip over stdio through the MCP client.
