#!/usr/bin/env python3
"""ctx-mcp: MCP server exposing a project's ContextDoc files to any MCP-capable agent.

Read-only tools, confined to the project folder (the server's working directory, or --root):
- get_context(file_path): project.ctx + the file's .ctx, to read before changing the file
- list_tensions(path): every tension in the .ctx files under PATH
- list_scenarios(path): the conceptualTests under PATH (the specification)
- check_drift(path): sources that changed after their .ctx (git history, like `ctx-watch status`)

Run: python tools/ctx-mcp/ctx_mcp.py [--root DIR]   (stdio transport)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

try:  # mcp 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server

# ctx-watch provides the drift rules (git history, .ctxignore, skipped dirs)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ctx-watch"))
import ctx_watch  # noqa: E402

ROOT = Path.cwd()

INSTRUCTIONS = (
    "ContextDoc: .ctx files next to source files hold what the code can't say: tensions (decisions that "
    "look wrong but are intentional), workflows and conceptualTests. Call get_context before changing a "
    "file. conceptualTests are the specification: adapt the code to them, never modify them to make code "
    "pass; if they can't be satisfied, ask the user."
)

server = _Server("contextdoc", instructions=INSTRUCTIONS)


def _resolve(path: str) -> Path:
    """PATH inside the project root, or ValueError."""
    p = (ROOT / path).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise ValueError(f"{path} is outside the project root")
    return p


def _rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix() if p != ROOT else "."


def _ctx_files(base: Path) -> list[Path]:
    if base.is_file():
        return [base] if base.suffix == ".ctx" else ([Path(str(base) + ".ctx")] if Path(str(base) + ".ctx").is_file() else [])
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in ctx_watch.SKIP_DIRS]
        found += [Path(dirpath) / f for f in filenames if f.endswith(".ctx")]
    return sorted(found)


def _load(p: Path) -> dict:
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _project_ctx(start: Path) -> Path | None:
    d = start if start.is_dir() else start.parent
    while True:
        if (d / "project.ctx").is_file():
            return d / "project.ctx"
        if d == ROOT or d.parent == d:
            return None
        d = d.parent


@server.tool()
def get_context(file_path: str) -> str:
    """ContextDoc context for a source file: project.ctx and the file's .ctx (tensions, workflows,
    conceptualTests). Read it before changing the file."""
    src = _resolve(file_path)
    ctx = Path(str(src) + ".ctx")
    parts = []
    project = _project_ctx(src)
    if project:
        parts.append(f"--- {_rel(project)} ---\n{project.read_text(encoding='utf-8').strip()}")
    if ctx.is_file():
        parts.append(f"--- {_rel(ctx)} ---\n{ctx.read_text(encoding='utf-8').strip()}")
    else:
        parts.append(f"{_rel(src)} has no .ctx file.")
    return "\n\n".join(parts) + "\n\nconceptualTests are the specification: never modify them to fit the code."


@server.tool()
def list_tensions(path: str = ".") -> list[dict]:
    """Every tension (intentional decision not to undo) in the .ctx files under PATH."""
    out = []
    for p in _ctx_files(_resolve(path)):
        for t in _load(p).get("tensions") or []:
            out.append({"file": _rel(p), "tension": str(t)})
    return out


@server.tool()
def list_scenarios(path: str = ".") -> list[dict]:
    """The conceptualTests (scenarios with action/expect steps) in the .ctx files under PATH."""
    out = []
    for p in _ctx_files(_resolve(path)):
        for s in _load(p).get("conceptualTests") or []:
            if isinstance(s, dict):
                out.append({"file": _rel(p), "name": s.get("name", "unnamed"), "steps": s.get("steps") or []})
    return out


@server.tool()
def check_drift(path: str = ".") -> list[dict]:
    """Source files under PATH that changed after their .ctx (git history; modification times outside git)."""
    base = _resolve(path)
    history = ctx_watch.GitHistory.load(ROOT)
    patterns = ctx_watch._load_ignore_patterns(ROOT)
    out = []
    for ctx in _ctx_files(base):
        src = Path(str(ctx)[:-4])
        if not src.is_file() or ctx_watch._is_ignored(src, ROOT, patterns):
            continue
        if history is not None:
            reason = history.drift(src, ctx)
        else:
            reason = ".ctx is older than the source" if ctx.stat().st_mtime < src.stat().st_mtime else None
        if reason:
            out.append({"file": _rel(src), "reason": reason})
    return out


def main() -> None:
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", help="project folder (default: current directory)")
    ROOT = Path(parser.parse_args().root).resolve()
    server.run()


if __name__ == "__main__":
    main()
