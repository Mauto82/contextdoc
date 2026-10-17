"""Regenerates expected.json from cases.json with ctx-run, the reference implementation.

Run it only when the runner spec or the runner's behavior changes on purpose:
    python spec/runner/fixtures/generate.py
then check that the VS Code extension still matches (npm run test:unit in vscode-extension).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "tools", "ctx-run"))
import ctx_run  # noqa: E402


def expected_for(case: dict) -> dict:
    scenario = case["scenario"]
    args = (case["sourcePath"], case["sourceContent"], case["sourceWarning"], case["language"])
    parsed = ctx_run.parse_llm_response(case["raw"], len(scenario.get("steps", [])))
    result = ctx_run.build_scenario_result(scenario, case["raw"], parsed)
    failed = [s for s in result.steps if not s.passed]
    return {
        "system": ctx_run.build_system_prompt(),
        "user": ctx_run.build_user_message(scenario, *args),
        "fix": ctx_run.build_fix_prompt(scenario, failed, case["sourcePath"], case["sourceContent"], case["language"]),
        "key": ctx_run.make_cache_key(scenario, case["sourceContent"], case["model"]),
        "result": {
            "name": result.name,
            "overall_passed": result.overall_passed,
            "error": result.error,
            "steps": [{"action": s.action, "expect": s.expect, "passed": s.passed, "explanation": s.explanation}
                      for s in result.steps],
        },
    }


def generate() -> dict:
    with open(os.path.join(HERE, "cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    return {case["id"]: expected_for(case) for case in cases}


if __name__ == "__main__":
    with open(os.path.join(HERE, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(generate(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("expected.json regenerated")
