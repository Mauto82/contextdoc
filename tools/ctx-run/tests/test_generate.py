"""
ctx-run generate / verify (ctx_generate.py), with the LLM mocked.

A small project in a tmp folder: calc.py, whose div() has a bug, and its .ctx with two scenarios.
The mocked LLM returns tests that follow each scenario, so the "Division" test fails on the bug.
"""
import os
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import ctx_generate
from ctx_run import cli

SOURCE = "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a * b  # bug: should divide\n"

CTX = """purpose: "Arithmetic"
conceptualTests:
  - name: "Addition"
    steps:
      - action: "add(2, 3)"
        expect: "returns 5"
  - name: "Division «÷»"
    steps:
      - action: "div(6, 3)"
        expect: "returns 2"
"""

TESTS = {
    "Addition": "import calc\n\n\ndef test_addition():\n    assert calc.add(2, 3) == 5\n",
    "Division «÷»": "import calc\n\n\ndef test_division():\n    assert calc.div(6, 3) == 2\n",
    "Subtraction": "import calc\n\n\ndef test_subtraction():\n    assert calc.add(5, -3) == 2\n",
}


def fake_llm(responses=None):
    """Answers with the test for the scenario named in the prompt; counts calls."""
    calls = []

    def call(model, system, user, timeout=60):
        calls.append(user)
        if responses:
            return responses.pop(0)
        for name, code in TESTS.items():
            if f'Scenario: "{name}"' in user:
                return f"```python\n{code}```"
        raise AssertionError("unexpected prompt")

    return call, calls


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "calc.py").write_text(SOURCE)
    (tmp_path / "calc.py.ctx").write_text(CTX)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def run(*args):
    return CliRunner().invoke(cli, [*args, "--no-color"])


def generated_file(project):
    return project / "tests" / "contextdoc" / "test_calc.py"


class TestGenerate:
    def test_writes_one_block_per_scenario(self, project):
        call, calls = fake_llm()
        with patch("ctx_run.call_llm", call):
            result = run("generate", "calc.py.ctx")
        assert result.exit_code == 0, result.output
        assert len(calls) == 2
        blocks = ctx_generate.parse_blocks(generated_file(project).read_text())
        assert [b.name for b in blocks] == ["Addition", "Division «÷»"]
        assert "[GENERATED] Addition" in result.output

    def test_unchanged_scenarios_are_kept_without_llm_calls(self, project):
        call, calls = fake_llm()
        with patch("ctx_run.call_llm", call):
            run("generate", "calc.py.ctx")
            calls.clear()
            result = run("generate", "calc.py.ctx")
        assert calls == []
        assert "[KEPT] Addition" in result.output

    def test_changed_scenario_is_regenerated_and_removed_one_dropped(self, project):
        call, calls = fake_llm()
        with patch("ctx_run.call_llm", call):
            run("generate", "calc.py.ctx")
            ctx = CTX.replace('expect: "returns 5"', 'expect: "returns 5, an int"')
            ctx = ctx.split('  - name: "Division')[0] + '  - name: "Subtraction"\n    steps:\n      - action: "add(5, -3)"\n        expect: "returns 2"\n'
            (project / "calc.py.ctx").write_text(ctx)
            calls.clear()
            result = run("generate", "calc.py.ctx")
        assert len(calls) == 2  # Addition (changed) and Subtraction (new)
        assert "[REGENERATED] Addition" in result.output
        assert "[GENERATED] Subtraction" in result.output
        assert "[REMOVED] Division «÷»" in result.output
        assert [b.name for b in ctx_generate.parse_blocks(generated_file(project).read_text())] == ["Addition", "Subtraction"]

    def test_invalid_answer_is_retried_once(self, project):
        call, calls = fake_llm(["not python at all :(", TESTS["Addition"], TESTS["Division «÷»"]])
        with patch("ctx_run.call_llm", call):
            result = run("generate", "calc.py.ctx")
        assert result.exit_code == 0
        assert "Your previous answer was not valid" in calls[1]

    def test_two_invalid_answers_fail_the_scenario(self, project):
        call, _ = fake_llm(["def helper(): pass", "x = 1", TESTS["Division «÷»"]])
        with patch("ctx_run.call_llm", call):
            result = run("generate", "calc.py.ctx")
        assert result.exit_code == 1
        assert "[FAILED] Addition" in result.output
        assert "no top-level test function" in result.output

    def test_non_python_sources_are_skipped(self, project):
        (project / "app.js").write_text("module.exports = {}\n")
        (project / "app.js.ctx").write_text(CTX)
        call, calls = fake_llm()
        with patch("ctx_run.call_llm", call):
            result = run("generate", "app.js.ctx")
        assert calls == []
        assert "skipped" in result.output and "pytest" in result.output


class TestCheck:
    def test_up_to_date(self, project):
        with patch("ctx_run.call_llm", fake_llm()[0]):
            run("generate", "calc.py.ctx")
        assert run("generate", "calc.py.ctx", "--check").exit_code == 0

    def test_missing_stale_and_orphan_fail(self, project):
        result = run("generate", "calc.py.ctx", "--check")
        assert result.exit_code == 1 and "[MISSING] Addition" in result.output
        with patch("ctx_run.call_llm", fake_llm()[0]):
            run("generate", "calc.py.ctx")
        (project / "calc.py.ctx").write_text(CTX.replace("returns 5", "returns five").split('  - name: "Division')[0])
        result = run("generate", "calc.py.ctx", "--check")
        assert result.exit_code == 1
        assert "[STALE] Addition" in result.output
        assert "[ORPHAN] Division «÷»" in result.output

    def test_check_never_calls_the_llm(self, project):
        with patch("ctx_run.call_llm", side_effect=AssertionError("no LLM in --check")):
            run("generate", "calc.py.ctx", "--check")


class TestVerify:
    def test_reports_each_scenario_from_a_real_pytest_run(self, project):
        with patch("ctx_run.call_llm", fake_llm()[0]):
            run("generate", "calc.py.ctx")
        result = run("verify", "calc.py.ctx")
        assert result.exit_code == 1  # div() has a bug
        assert "[PASSED] Addition" in result.output
        assert "[FAILED] Division «÷»" in result.output

    def test_stale_tests_count_as_not_passing(self, project):
        with patch("ctx_run.call_llm", fake_llm()[0]):
            run("generate", "calc.py.ctx")
        (project / "calc.py").write_text(SOURCE.replace("a * b", "a / b"))  # fix the bug
        (project / "calc.py.ctx").write_text(CTX.replace("returns 5", "returns five"))
        result = run("verify", "calc.py.ctx")
        assert "[STALE] Addition" in result.output
        assert "[PASSED] Division «÷»" in result.output
        assert result.exit_code == 1

    def test_without_generated_tests(self, project):
        assert run("verify", "calc.py.ctx").exit_code == 2
