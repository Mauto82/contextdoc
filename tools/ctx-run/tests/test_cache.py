"""
Tests for the caching layer in ctx-run.
"""
import json
import os
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from ctx_run import (
    cli,
    make_cache_key,
    load_cache,
    save_cache,
    _scenario_to_cache_entry,
    _scenario_from_cache_entry,
    ScenarioResult,
    StepResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_llm_response(steps_pass: list[bool]) -> str:
    steps = [
        {
            "action": f"action {i+1}",
            "passed": p,
            "explanation": "ok" if p else "failed",
        }
        for i, p in enumerate(steps_pass)
    ]
    return json.dumps({"overall": all(steps_pass), "steps": steps})


def run_cli(args):
    return CliRunner().invoke(cli, args)


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_same_inputs_same_key(self):
        scenario = {"name": "Test", "steps": [{"action": "a", "expect": "b"}]}
        k1 = make_cache_key(scenario, "source", "model")
        k2 = make_cache_key(scenario, "source", "model")
        assert k1 == k2

    def test_different_model_different_key(self):
        scenario = {"name": "Test", "steps": []}
        k1 = make_cache_key(scenario, "src", "model-a")
        k2 = make_cache_key(scenario, "src", "model-b")
        assert k1 != k2

    def test_different_source_different_key(self):
        scenario = {"name": "Test", "steps": []}
        k1 = make_cache_key(scenario, "source v1", "model")
        k2 = make_cache_key(scenario, "source v2", "model")
        assert k1 != k2

    def test_different_scenario_different_key(self):
        s1 = {"name": "Scenario A", "steps": []}
        s2 = {"name": "Scenario B", "steps": []}
        assert make_cache_key(s1, "src", "m") != make_cache_key(s2, "src", "m")

    def test_none_source_handled(self):
        scenario = {"name": "Test", "steps": []}
        key = make_cache_key(scenario, None, "model")
        assert len(key) == 64  # SHA-256 hex


# ---------------------------------------------------------------------------
# Cache serialisation round-trip
# ---------------------------------------------------------------------------

class TestCacheSerialization:
    def _make_result(self, passed: bool) -> ScenarioResult:
        return ScenarioResult(
            name="My scenario",
            steps=[
                StepResult(action="do x", expect="y happens", passed=passed, explanation="because"),
            ],
            overall_passed=passed,
        )

    def test_round_trip_passing(self):
        original = self._make_result(True)
        entry = _scenario_to_cache_entry(original)
        restored = _scenario_from_cache_entry(entry)
        assert restored.name == original.name
        assert restored.overall_passed is True
        assert restored.from_cache is True
        assert len(restored.steps) == 1
        assert restored.steps[0].passed is True

    def test_round_trip_failing(self):
        original = self._make_result(False)
        entry = _scenario_to_cache_entry(original)
        restored = _scenario_from_cache_entry(entry)
        assert restored.overall_passed is False
        assert restored.steps[0].passed is False
        assert restored.from_cache is True

    def test_timestamp_present(self):
        result = self._make_result(True)
        entry = _scenario_to_cache_entry(result)
        assert "timestamp" in entry

    def test_error_scenario_round_trip(self):
        original = ScenarioResult(name="err", overall_passed=False, error="LLM died")
        entry = _scenario_to_cache_entry(original)
        restored = _scenario_from_cache_entry(entry)
        assert restored.error == "LLM died"


# ---------------------------------------------------------------------------
# Cache persistence (disk)
# ---------------------------------------------------------------------------

class TestCachePersistence:
    def test_save_and_load(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        entries = {"abc123": {"timestamp": "2024-01-01", "result": {"name": "x", "overall_passed": True, "error": None, "steps": []}}}
        with patch("ctx_run._cache_path", return_value=cache_file):
            save_cache(entries)
            loaded = load_cache()
        assert "abc123" in loaded

    def test_load_missing_returns_empty(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("ctx_run._cache_path", return_value=missing):
            result = load_cache()
        assert result == {}

    def test_save_is_atomic(self, tmp_path):
        """save_cache writes to .tmp then os.replace — original never partially written."""
        cache_file = str(tmp_path / "cache.json")
        with patch("ctx_run._cache_path", return_value=cache_file):
            save_cache({"k": {"timestamp": "t", "result": {"name": "s", "overall_passed": True, "error": None, "steps": []}}})
        assert os.path.isfile(cache_file)
        assert not os.path.isfile(cache_file + ".tmp")  # tmp cleaned up


# ---------------------------------------------------------------------------
# CLI: --no-cache flag
# ---------------------------------------------------------------------------

class TestNoCacheFlag:
    def test_no_cache_calls_llm_every_time(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        call_count = 0
        def counting_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return make_llm_response([True, True])

        with patch("ctx_run.call_llm", side_effect=counting_llm):
            run_cli(["run", ctx_path, "--no-cache", "--model", "mock"])
            run_cli(["run", ctx_path, "--no-cache", "--model", "mock"])

        # Two runs, "Basic flow" scenario each time = 2 calls minimum
        assert call_count >= 2

    def test_with_cache_skips_llm_on_second_run(self, ctx_with_source, tmp_path):
        ctx_path, _ = ctx_with_source
        cache_file = str(tmp_path / "test_cache.json")
        call_count = 0

        def counting_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return make_llm_response([True, True])

        with patch("ctx_run._cache_path", return_value=cache_file):
            with patch("ctx_run.call_llm", side_effect=counting_llm):
                # First run: LLM called, result cached
                run_cli(["run", ctx_path, "--model", "mock"])
                calls_after_first = call_count

                # Second run: should read from cache
                run_cli(["run", ctx_path, "--model", "mock"])
                calls_after_second = call_count

        assert calls_after_second == calls_after_first  # no new LLM calls


# ---------------------------------------------------------------------------
# CLI: --timeout flag
# ---------------------------------------------------------------------------

class TestTimeoutFlag:
    def test_timeout_passed_to_call_llm(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        captured_kwargs = {}

        def capturing_llm(model, system, user, timeout=60):
            captured_kwargs["timeout"] = timeout
            return make_llm_response([True, True])

        with patch("ctx_run.call_llm", side_effect=capturing_llm):
            run_cli(["run", ctx_path, "--timeout", "120", "--model", "mock", "--no-cache"])

        assert captured_kwargs.get("timeout") == 120

    def test_default_timeout_is_60(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        captured_kwargs = {}

        def capturing_llm(model, system, user, timeout=60):
            captured_kwargs["timeout"] = timeout
            return make_llm_response([True, True])

        with patch("ctx_run.call_llm", side_effect=capturing_llm):
            run_cli(["run", ctx_path, "--model", "mock", "--no-cache"])

        assert captured_kwargs.get("timeout") == 60


# ---------------------------------------------------------------------------
# CLI: --fix flag
# ---------------------------------------------------------------------------

class TestFixFlag:
    def test_fix_makes_extra_llm_call_on_failure(self, tmp_path):
        # Use a single-scenario ctx so we can count exactly: 1 eval + 1 fix = 2
        ctx = tmp_path / "single.py.ctx"
        ctx.write_text(
            "conceptualTests:\n"
            "  - name: \"Single\"\n"
            "    steps:\n"
            "      - action: \"do x\"\n"
            "        expect: \"y\"\n"
        )
        (tmp_path / "single.py").write_text("def foo(): pass")
        ctx_path = str(ctx)

        call_count = 0

        def counting_llm(model, system, user, timeout=60):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return make_llm_response([False])   # eval: failure → triggers fix
            return "Add proper implementation to foo()."

        with patch("ctx_run.call_llm", side_effect=counting_llm):
            run_cli(["run", ctx_path, "--fix", "--model", "mock", "--no-cache"])

        # Exactly 1 eval call + 1 fix call = 2
        assert call_count == 2

    def test_fix_suggestion_appears_in_output(self, ctx_with_source):
        ctx_path, _ = ctx_with_source

        call_num = [0]
        def sequenced_llm(model, system, user, timeout=60):
            call_num[0] += 1
            if call_num[0] == 1:
                return make_llm_response([True, False])
            return "Add validation in process() to fix this step."

        with patch("ctx_run.call_llm", side_effect=sequenced_llm):
            result = run_cli(["run", ctx_path, "--fix", "--model", "mock", "--no-cache"])

        assert "Fix suggestion" in result.output
        assert "Add validation in process()" in result.output

    def test_no_fix_call_when_all_pass(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        call_count = [0]

        def counting_llm(model, system, user, timeout=60):
            call_count[0] += 1
            return make_llm_response([True, True])

        with patch("ctx_run.call_llm", side_effect=counting_llm):
            result = run_cli(["run", ctx_path, "--fix", "--model", "mock", "--no-cache"])

        # Only eval calls, no fix calls
        assert "Fix suggestion" not in result.output
        assert result.exit_code == 0

    def test_fix_not_in_output_without_flag(self, ctx_with_source):
        ctx_path, _ = ctx_with_source
        with patch("ctx_run.call_llm", return_value=make_llm_response([True, False])):
            result = run_cli(["run", ctx_path, "--model", "mock", "--no-cache"])
        assert "Fix suggestion" not in result.output


# ---------------------------------------------------------------------------
# CLI: clear-cache command
# ---------------------------------------------------------------------------

class TestClearCache:
    def test_clear_existing_cache(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        with open(cache_file, "w") as f:
            json.dump({"version": 1, "entries": {}}, f)

        with patch("ctx_run._cache_path", return_value=cache_file):
            result = CliRunner().invoke(cli, ["clear-cache"])

        assert result.exit_code == 0
        assert "cleared" in result.output
        assert not os.path.isfile(cache_file)

    def test_clear_no_cache_no_error(self, tmp_path):
        missing = str(tmp_path / "nonexistent.json")
        with patch("ctx_run._cache_path", return_value=missing):
            result = CliRunner().invoke(cli, ["clear-cache"])
        assert result.exit_code == 0
        assert "No cache" in result.output
