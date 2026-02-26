"""
Shared fixtures for ctx-run tests.
"""
import sys
import os
from unittest.mock import patch

# Make ctx_run importable from tests/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path):
    """
    Give every test its own cache file so tests don't share cached LLM results.
    Without this, two tests using the same scenario/source/model would share a
    cache key and the second test would get a cache hit instead of calling the mock.
    """
    cache_file = str(tmp_path / "ctx_run_test_cache.json")
    with patch("ctx_run._cache_path", return_value=cache_file):
        yield cache_file


SAMPLE_CTX = """
purpose: "Sample service for testing"

conceptualTests:
  - name: "Basic flow"
    steps:
      - action: "call process(valid_input)"
        expect: "returns processed result"
      - action: "call process(None)"
        expect: "raises ValueError"

  - name: "Edge case"
    steps:
      - action: "call process with empty string"
        expect: "returns empty result"
"""

SAMPLE_SOURCE = """
def process(value):
    if value is None:
        raise ValueError("value cannot be None")
    return value.strip() if value else ""
"""

VALID_LLM_RESPONSE = """{
  "overall": true,
  "steps": [
    {
      "action": "call process(valid_input)",
      "passed": true,
      "explanation": "The function returns the stripped value."
    },
    {
      "action": "call process(None)",
      "passed": true,
      "explanation": "None raises ValueError as expected."
    }
  ]
}"""

FENCED_LLM_RESPONSE = """```json
{
  "overall": true,
  "steps": [
    {
      "action": "call process(valid_input)",
      "passed": true,
      "explanation": "Returns stripped value."
    }
  ]
}
```"""

PARTIAL_LLM_RESPONSE = """Here is my analysis:
{
  "overall": false,
  "steps": [
    {
      "action": "call process(valid_input)",
      "passed": false,
      "explanation": "Function does not validate type."
    }
  ]
}
Some extra text after."""

FAILING_LLM_RESPONSE = """{
  "overall": false,
  "steps": [
    {
      "action": "call process(valid_input)",
      "passed": true,
      "explanation": "Returns stripped value."
    },
    {
      "action": "call process(None)",
      "passed": false,
      "explanation": "Code raises ValueError but caller does not catch it."
    }
  ]
}"""


@pytest.fixture
def ctx_file(tmp_path):
    """A valid .ctx file with conceptualTests."""
    p = tmp_path / "sample.py.ctx"
    p.write_text(SAMPLE_CTX)
    return str(p)


@pytest.fixture
def source_file(tmp_path):
    """Source file matching ctx_file fixture."""
    p = tmp_path / "sample.py"
    p.write_text(SAMPLE_SOURCE)
    return str(p)


@pytest.fixture
def ctx_with_source(tmp_path):
    """Both .ctx and corresponding source in the same tmp dir."""
    ctx = tmp_path / "service.py.ctx"
    src = tmp_path / "service.py"
    ctx.write_text(SAMPLE_CTX)
    src.write_text(SAMPLE_SOURCE)
    return str(ctx), str(src)


@pytest.fixture
def ctx_no_tests(tmp_path):
    """A .ctx file with no conceptualTests section."""
    p = tmp_path / "simple.py.ctx"
    p.write_text("purpose: 'Just a purpose, no tests'\ntensions:\n  - 'some tension'\n")
    return str(p)


@pytest.fixture
def ctx_directory(tmp_path):
    """Directory with 3 .ctx files: 2 with conceptualTests, 1 without."""
    (tmp_path / "a.py.ctx").write_text(SAMPLE_CTX)
    (tmp_path / "b.py.ctx").write_text(SAMPLE_CTX)
    (tmp_path / "c.py.ctx").write_text("purpose: 'no tests here'\n")
    return str(tmp_path)
