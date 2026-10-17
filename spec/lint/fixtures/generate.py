"""Regenerates expected.json from the fixture project with ctx-lint, the reference implementation.

    python spec/lint/fixtures/generate.py
then check the VS Code extension still matches (npm run test:unit in vscode-extension).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "tools", "ctx-lint"))
import ctx_lint  # noqa: E402

PROJECT = os.path.join(HERE, "project")


def generate() -> dict:
    files = sorted(f for f in os.listdir(PROJECT) if f.endswith(".ctx"))
    return {f: [[x.line, x.code, x.message] for x in ctx_lint.lint_file(os.path.join(PROJECT, f), PROJECT)] for f in files}


if __name__ == "__main__":
    with open(os.path.join(HERE, "expected.json"), "w", encoding="utf-8") as f:
        json.dump(generate(), f, indent=2, ensure_ascii=False)
        f.write("\n")
    print("expected.json regenerated")
