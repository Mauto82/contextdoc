"""ctx-mcp: the tools as functions, and one round trip through the MCP protocol over stdio."""
import json
import os
import subprocess
import sys
from pathlib import Path

import anyio
import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import ctx_mcp  # noqa: E402

CTX = """purpose: "Arithmetic"
tensions:
  - "div rounds toward zero on purpose"
conceptualTests:
  - name: "Division"
    steps:
      - action: "div(7, 2)"
        expect: "returns 3"
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "project.ctx").write_text('purpose: "demo"\ntensions:\n  - "no global state"\n')
    (tmp_path / "calc.py").write_text("def div(a, b):\n    return int(a / b)\n")
    (tmp_path / "calc.py.ctx").write_text(CTX)
    (tmp_path / "plain.py").write_text("x = 1\n")
    monkeypatch.setattr(ctx_mcp, "ROOT", tmp_path.resolve())
    return tmp_path


def test_get_context_includes_project_and_file_ctx(project):
    text = ctx_mcp.get_context("calc.py")
    assert "no global state" in text and "div rounds toward zero" in text
    assert "never modify them" in text


def test_get_context_for_a_file_without_ctx(project):
    assert "plain.py has no .ctx file" in ctx_mcp.get_context("plain.py")


def test_paths_outside_the_project_are_refused(project):
    with pytest.raises(ValueError):
        ctx_mcp.get_context("../etc/passwd")


def test_list_tensions_and_scenarios(project):
    tensions = ctx_mcp.list_tensions(".")
    assert {"file": "calc.py.ctx", "tension": "div rounds toward zero on purpose"} in tensions
    assert {"file": "project.ctx", "tension": "no global state"} in tensions
    scenarios = ctx_mcp.list_scenarios("calc.py")
    assert scenarios == [{"file": "calc.py.ctx", "name": "Division", "steps": [{"action": "div(7, 2)", "expect": "returns 3"}]}]


def test_check_drift_with_git(project):
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}
    git = lambda *a: subprocess.run(["git", *a], cwd=project, check=True, capture_output=True, env=env)  # noqa: E731
    git("init", "-q")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    assert ctx_mcp.check_drift(".") == []
    (project / "calc.py").write_text("def div(a, b):\n    return a // b\n")
    assert ctx_mcp.check_drift(".") == [{"file": "calc.py", "reason": "source has uncommitted changes, .ctx doesn't"}]


def test_round_trip_over_stdio(project):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def go():
        params = StdioServerParameters(command=sys.executable, args=[str(HERE / "ctx_mcp.py"), "--root", str(project)])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names = sorted(t.name for t in (await session.list_tools()).tools)
                result = await session.call_tool("get_context", {"file_path": "calc.py"})
                return names, result.content[0].text

    names, text = anyio.run(go)
    assert names == ["check_drift", "get_context", "list_scenarios", "list_tensions"]
    assert "div rounds toward zero" in text
