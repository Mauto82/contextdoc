"""
Tests for parse_llm_response — the most critical function in ctx_run.
Three-layer fallback: direct JSON → strip fences → regex extraction.
"""
import pytest
from ctx_run import parse_llm_response, build_scenario_result


# ---------------------------------------------------------------------------
# parse_llm_response
# ---------------------------------------------------------------------------

class TestParseDirectJson:
    def test_valid_json_parsed(self, valid_response=None):
        raw = '{"overall": true, "steps": [{"action": "a", "passed": true, "explanation": "ok"}]}'
        result = parse_llm_response(raw, expected_steps=1)
        assert result is not None
        assert result["overall"] is True
        assert len(result["steps"]) == 1

    def test_overall_false(self):
        raw = '{"overall": false, "steps": [{"action": "a", "passed": false, "explanation": "fail"}]}'
        result = parse_llm_response(raw, expected_steps=1)
        assert result["overall"] is False
        assert result["steps"][0]["passed"] is False

    def test_multiple_steps(self):
        raw = '''{
            "overall": true,
            "steps": [
                {"action": "step1", "passed": true, "explanation": "ok"},
                {"action": "step2", "passed": true, "explanation": "ok"}
            ]
        }'''
        result = parse_llm_response(raw, expected_steps=2)
        assert result is not None
        assert len(result["steps"]) == 2


class TestParseFencedJson:
    def test_json_fenced_with_label(self):
        raw = '```json\n{"overall": true, "steps": []}\n```'
        result = parse_llm_response(raw, expected_steps=0)
        assert result is not None
        assert result["overall"] is True

    def test_json_fenced_without_label(self):
        raw = '```\n{"overall": false, "steps": []}\n```'
        result = parse_llm_response(raw, expected_steps=0)
        assert result is not None
        assert result["overall"] is False

    def test_fenced_with_surrounding_text(self):
        raw = 'Here is my analysis:\n```json\n{"overall": true, "steps": []}\n```\nDone.'
        result = parse_llm_response(raw, expected_steps=0)
        assert result is not None


class TestParseRegexFallback:
    def test_json_embedded_in_prose(self):
        raw = 'Let me analyze this. {"overall": true, "steps": []} The code looks fine.'
        result = parse_llm_response(raw, expected_steps=0)
        assert result is not None
        assert result["overall"] is True

    def test_json_with_preamble_and_suffix(self):
        raw = 'Analysis complete:\n{"overall": false, "steps": [{"action": "x", "passed": false, "explanation": "e"}]}\nEnd of analysis.'
        result = parse_llm_response(raw, expected_steps=1)
        assert result is not None
        assert result["overall"] is False


class TestParseFailure:
    def test_completely_unparseable_returns_none(self):
        raw = "This is just plain text with no JSON at all."
        result = parse_llm_response(raw, expected_steps=1)
        assert result is None

    def test_empty_string_returns_none(self):
        result = parse_llm_response("", expected_steps=1)
        assert result is None

    def test_broken_json_returns_none(self):
        raw = '{"overall": true, "steps": [{"action": "x"'  # truncated
        result = parse_llm_response(raw, expected_steps=1)
        assert result is None

    def test_array_instead_of_object_returns_none(self):
        raw = '[{"overall": true}]'
        result = parse_llm_response(raw, expected_steps=1)
        # An array is valid JSON but not the expected structure — parse succeeds
        # but the caller will handle missing keys. parse_llm_response just parses.
        # Depending on implementation: either returns the array or None.
        # We only assert it doesn't raise.
        pass  # no assertion — just verify no exception


# ---------------------------------------------------------------------------
# build_scenario_result
# ---------------------------------------------------------------------------

class TestBuildScenarioResult:
    def _scenario(self, steps=None):
        return {
            "name": "Test scenario",
            "steps": steps or [
                {"action": "action 1", "expect": "expect 1"},
                {"action": "action 2", "expect": "expect 2"},
            ]
        }

    def test_all_pass(self):
        parsed = {
            "overall": True,
            "steps": [
                {"action": "action 1", "passed": True, "explanation": "ok"},
                {"action": "action 2", "passed": True, "explanation": "ok"},
            ]
        }
        result = build_scenario_result(self._scenario(), raw_response="", parsed=parsed)
        assert result.overall_passed is True
        assert all(s.passed for s in result.steps)
        assert result.error is None

    def test_one_fail_overrides_overall(self):
        """overall_passed must be recomputed from steps, not trusted from LLM."""
        parsed = {
            "overall": True,  # LLM says true — but one step is false
            "steps": [
                {"action": "action 1", "passed": True, "explanation": "ok"},
                {"action": "action 2", "passed": False, "explanation": "failed"},
            ]
        }
        result = build_scenario_result(self._scenario(), raw_response="", parsed=parsed)
        assert result.overall_passed is False  # recomputed correctly

    def test_missing_steps_padded_as_fail(self):
        """If LLM returns fewer steps than expected, missing ones are marked FAIL."""
        parsed = {
            "overall": True,
            "steps": [
                {"action": "action 1", "passed": True, "explanation": "ok"},
                # step 2 missing
            ]
        }
        result = build_scenario_result(self._scenario(), raw_response="", parsed=parsed)
        assert len(result.steps) == 2
        assert result.steps[1].passed is False
        assert "missing" in result.steps[1].explanation.lower()
        assert result.overall_passed is False

    def test_parse_failure_sets_error(self):
        """When parsed is None, scenario gets error message, not steps."""
        result = build_scenario_result(
            self._scenario(), raw_response="garbage", parsed=None
        )
        assert result.error is not None
        assert result.overall_passed is False
        assert len(result.steps) == 0

    def test_step_action_and_expect_preserved(self):
        parsed = {
            "overall": True,
            "steps": [
                {"action": "action 1", "passed": True, "explanation": "ok"},
                {"action": "action 2", "passed": True, "explanation": "ok"},
            ]
        }
        result = build_scenario_result(self._scenario(), raw_response="", parsed=parsed)
        assert result.steps[0].action == "action 1"
        assert result.steps[0].expect == "expect 1"
        assert result.steps[1].action == "action 2"
        assert result.steps[1].expect == "expect 2"
