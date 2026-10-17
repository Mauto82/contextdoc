"""ctx-lint: the shared fixtures (spec/lint/fixtures, also checked by the VS Code extension) and the CLI."""
import json
import os
import sys

import pytest
from click.testing import CliRunner

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
FIXTURES = os.path.join(HERE, "..", "..", "..", "spec", "lint", "fixtures")
sys.path.insert(0, FIXTURES)

import ctx_lint  # noqa: E402
import generate  # noqa: E402

with open(os.path.join(FIXTURES, "expected.json"), encoding="utf-8") as f:
    EXPECTED = json.load(f)
ACTUAL = generate.generate()


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_fixture_matches_expected(name):
    assert ACTUAL[name] == EXPECTED[name]


def codes(name):
    return [c for _, c, _ in EXPECTED[name]]


def test_every_rule_is_covered_by_the_fixtures():
    found = {c for v in EXPECTED.values() for _, c, _ in v}
    assert found == {"L001", "L002", "L003", "L004", "L005", "L006", "L007", "L008"}


def test_a_clean_ctx_and_project_ctx_have_no_warnings():
    assert codes("clean.py.ctx") == [] and codes("project.ctx") == []


def test_legacy_conceptdoc_section_gets_the_legacy_hint():
    msg = next(m for _, c, m in EXPECTED["calc.py.ctx"] if c == "L003")
    assert "'dependencies'" in msg and "ConceptDoc" in msg


def test_italian_validation_scenarios_are_recognized():
    assert codes("validate.py.ctx") == ["L005"]


def test_cli_text_and_strict(tmp_path):
    (tmp_path / "a.py.ctx").write_text('purpose: "x"\nconceptualTests:\n  - name: "s"\n    steps:\n      - action: "do"\n')
    runner = CliRunner()
    result = runner.invoke(ctx_lint.cli, [str(tmp_path), "--no-color"])
    assert result.exit_code == 0
    assert "a.py.ctx:5: L006" in result.output
    assert runner.invoke(ctx_lint.cli, [str(tmp_path), "--strict"]).exit_code == 1


def test_cli_json(tmp_path):
    (tmp_path / "a.py.ctx").write_text('purpose: "x"\nmetadata: {}\n')
    out = json.loads(CliRunner().invoke(ctx_lint.cli, [str(tmp_path), "--format", "json"]).output)
    (findings,) = out.values()
    assert findings[0]["code"] == "L003" and findings[0]["line"] == 2


def test_clean_tree_with_strict_passes(tmp_path):
    (tmp_path / "ok.py.ctx").write_text('purpose: "fine"\n')
    assert CliRunner().invoke(ctx_lint.cli, [str(tmp_path), "--strict"]).exit_code == 0
