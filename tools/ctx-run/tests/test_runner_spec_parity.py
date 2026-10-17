"""
Parity with the shared runner spec (spec/runner): ctx-run must reproduce spec/runner/fixtures/expected.json
exactly. The VS Code extension checks the same file (vscode-extension/test/unit/parity.test.js), so a
change that only one runner follows fails one of the two suites.

If the change is intended, regenerate the expected file: python spec/runner/fixtures/generate.py
"""
import json
import os
import sys

import pytest

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "..", "..", "spec", "runner", "fixtures")
sys.path.insert(0, FIXTURES)

import generate  # noqa: E402

with open(os.path.join(FIXTURES, "expected.json"), encoding="utf-8") as f:
    EXPECTED = json.load(f)

ACTUAL = generate.generate()


@pytest.mark.parametrize("case_id", sorted(EXPECTED))
@pytest.mark.parametrize("part", ["system", "user", "fix", "key", "result"])
def test_matches_expected(case_id, part):
    assert ACTUAL[case_id][part] == EXPECTED[case_id][part]


def test_every_case_has_an_expected_entry():
    assert sorted(ACTUAL) == sorted(EXPECTED)
