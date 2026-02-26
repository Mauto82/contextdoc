"""
CLI integration tests for ctx-run.
Uses Click's CliRunner to invoke the command without spawning a subprocess.
LLM calls are mocked — no API key required.
"""
import json
import pytest
from unittest.mock import patch
from click.testing import CliRunner

from ctx_run import cli


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_llm_response(steps_pass: list[bool]) -> str:
    """Build a fake LLM JSON response with the given pass/fail pattern."""
    steps = [
        {
            "action": f"action {i+1}",
            "passed": passed,
            "explanation": "ok" if passed else "failed because X",
        }
        for i, passed in enumerate(steps_pass)
    ]
    overall = all(steps_pass)
    return json.dumps({"overall": overall, "steps": steps})


def run_cli(args: list[str]) -> object:
    runner = CliRunner()
    return runner.invoke(cli, args)


# ---------------------------------------------------------------------------
# Single file run
# ---------------------------------------------------------------------------

class TestSingleFileRun:
    def test_all_pass_exit_0(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        # 2 steps in SAMPLE_CTX scenario "Basic flow"
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--model", "mock"])
        assert result.exit_code == 0
        assert "all scenarios passed" in result.output

    def test_one_fail_exit_1(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, False])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--model", "mock"])
        assert result.exit_code == 1
        assert "failed" in result.output

    def test_pass_shows_scenario_name(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--model", "mock"])
        assert "Basic flow" in result.output

    def test_verbose_shows_explanations_for_pass(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--verbose", "--model", "mock"])
        assert "ok" in result.output  # explanation shown

    def test_non_verbose_hides_pass_explanations(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = json.dumps({
            "overall": True,
            "steps": [
                {"action": "a", "passed": True, "explanation": "unique_pass_text_xyz"},
                {"action": "b", "passed": True, "explanation": "another_pass_text_abc"},
            ]
        })
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--model", "mock"])
        assert "unique_pass_text_xyz" not in result.output


# ---------------------------------------------------------------------------
# Directory scan
# ---------------------------------------------------------------------------

class TestDirectoryScan:
    def test_skips_files_without_conceptual_tests(self, ctx_directory, tmp_path):
        # ctx_directory has 2 .ctx with tests and 1 without
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_directory, "--model", "mock"])
        assert "skipped" in result.output

    def test_summary_counts_correct(self, ctx_directory):
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_directory, "--model", "mock"])
        assert "1 skipped" in result.output

    def test_fail_fast_stops_after_first_failure(self, ctx_directory):
        call_count = 0
        def fake_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return make_llm_response([False, False])
        with patch("ctx_run.call_llm", side_effect=fake_llm):
            result = run_cli(["run", ctx_directory, "--fail-fast", "--model", "mock"])
        # Should stop after first file's failure — not process all files
        assert call_count == 1


# ---------------------------------------------------------------------------
# Missing source file
# ---------------------------------------------------------------------------

class TestMissingSource:
    def test_missing_source_still_runs(self, ctx_file):
        # ctx_file has no corresponding .py file
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_file, "--model", "mock"])
        # Should run (not crash), LLM call happens
        assert result.exit_code in (0, 1)  # not exit code 2

    def test_missing_source_shows_warning(self, ctx_file):
        mock_response = make_llm_response([False, False])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_file, "--model", "mock"])
        assert "WARNING" in result.output or "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# LLM failure handling
# ---------------------------------------------------------------------------

class TestLlmFailureHandling:
    def test_unparseable_response_shows_error_not_crash(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        with patch("ctx_run.call_llm", return_value="this is not json at all"):
            result = run_cli(["run", ctx_path, "--model", "mock"])
        assert result.exit_code == 1
        assert "ERROR" in result.output
        # Click captures sys.exit(1) as SystemExit — not an unhandled crash
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_llm_api_error_shows_error_not_crash(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        with patch("ctx_run.call_llm", side_effect=Exception("API unreachable")):
            result = run_cli(["run", ctx_path, "--model", "mock"])
        assert result.exit_code == 1
        assert "API unreachable" in result.output
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

class TestJsonOutput:
    def test_json_output_is_valid(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--output", "json", "--model", "mock"])
        data = json.loads(result.output)
        assert "summary" in data
        assert "results" in data

    def test_json_summary_structure(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--output", "json", "--model", "mock"])
        summary = json.loads(result.output)["summary"]
        assert "files" in summary
        assert "scenarios" in summary
        assert "steps_passed" in summary
        assert "steps_total" in summary

    def test_json_exit_0_on_all_pass(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, True])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--output", "json", "--model", "mock"])
        assert result.exit_code == 0

    def test_json_exit_1_on_failure(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        mock_response = make_llm_response([True, False])
        with patch("ctx_run.call_llm", return_value=mock_response):
            result = run_cli(["run", ctx_path, "--output", "json", "--model", "mock"])
        assert result.exit_code == 1
