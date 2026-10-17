"""contextdoc_hook.py, fed the JSON that Claude Code sends to a PreToolUse hook."""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parent.parent / "contextdoc_hook.py"

CTX = """purpose: "Arithmetic"
tensions:
  - "div rounds toward zero on purpose"
conceptualTests:
  - name: "Division"
    steps:
      - action: "div(7, 2)"
        expect: "returns 3"
"""


def hook(project, tool, tool_input, session=None):
    event = {"session_id": session or str(uuid.uuid4()), "cwd": str(project), "tool_name": tool, "tool_input": tool_input}
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)})
    assert out.returncode == 0
    return json.loads(out.stdout)["hookSpecificOutput"] if out.stdout.strip() else None


@pytest.fixture
def project(tmp_path):
    (tmp_path / "project.ctx").write_text('purpose: "demo"\ntensions:\n  - "no global state"\n')
    (tmp_path / "calc.py").write_text("def div(a, b):\n    return int(a / b)\n")
    (tmp_path / "calc.py.ctx").write_text(CTX)
    (tmp_path / "plain.py").write_text("x = 1\n")
    return tmp_path


def test_read_of_a_documented_file_gets_project_and_file_context(project):
    out = hook(project, "Read", {"file_path": str(project / "calc.py")})
    assert "permissionDecision" not in out  # context only: the normal permission flow goes on
    assert "div rounds toward zero" in out["additionalContext"]
    assert "no global state" in out["additionalContext"]


def test_context_is_given_once_per_session_then_a_reminder(project):
    session = str(uuid.uuid4())
    first = hook(project, "Read", {"file_path": str(project / "calc.py")}, session)
    second = hook(project, "Edit", {"file_path": str(project / "calc.py"), "old_string": "int", "new_string": "round"}, session)
    assert "div rounds toward zero" in first["additionalContext"]
    assert "given earlier in this session" in second["additionalContext"]


def test_new_ctx_version_is_given_again(project):
    session = str(uuid.uuid4())
    hook(project, "Read", {"file_path": str(project / "calc.py")}, session)
    (project / "calc.py.ctx").write_text(CTX.replace("on purpose", "on purpose (billing)"))
    out = hook(project, "Read", {"file_path": str(project / "calc.py")}, session)
    assert "(billing)" in out["additionalContext"]


def test_files_without_ctx_get_nothing(project):
    assert hook(project, "Read", {"file_path": str(project / "plain.py")}) is None


def test_intent_first_write_of_a_missing_source_gets_its_spec(project):
    (project / "notify.py.ctx").write_text(CTX.replace("Arithmetic", "Notifications"))
    out = hook(project, "Write", {"file_path": str(project / "notify.py"), "content": "x = 1\n"})
    assert "Notifications" in out["additionalContext"]


def test_editing_conceptual_tests_asks_the_user(project):
    out = hook(project, "Edit", {"file_path": str(project / "calc.py.ctx"), "old_string": 'expect: "returns 3"', "new_string": 'expect: "returns 3.5"'})
    assert out["permissionDecision"] == "ask"
    assert "conceptualTests" in out["permissionDecisionReason"]


def test_rewriting_a_ctx_with_changed_tests_asks_the_user(project):
    out = hook(project, "Write", {"file_path": str(project / "calc.py.ctx"), "content": CTX.replace("div(7, 2)", "div(8, 2)")})
    assert out["permissionDecision"] == "ask"


def test_editing_other_sections_of_a_ctx_goes_through(project):
    out = hook(project, "Edit", {"file_path": str(project / "calc.py.ctx"), "old_string": "on purpose", "new_string": "on purpose, see ADR-3"})
    assert out is None


def test_writing_a_new_ctx_goes_through(project):
    assert hook(project, "Write", {"file_path": str(project / "new.py.ctx"), "content": CTX}) is None


def test_garbage_input_never_blocks(project):
    out = subprocess.run([sys.executable, str(HOOK)], input="not json", capture_output=True, text=True)
    assert out.returncode == 0 and out.stdout == ""
