"""ctx-run generate / verify: executable tests from conceptualTests, kept in sync with them.

For each .ctx whose source is a Python file, `generate` writes one pytest file (tests/contextdoc/ by
default) with one block per scenario. Every block starts with a marker holding the scenario's name and
a hash of the scenario, so later runs can tell which blocks are still valid:

    # --- contextdoc scenario: "Percentage discount" sha256:3f2a9c1b7d04 ---
    def test_...
    # --- end scenario ---

- same name and hash: the block is kept as is (no LLM call)
- changed hash: the block is regenerated (the scenario changed: the test follows it, never the reverse)
- scenario removed: the block is dropped

`generate --check` reports blocks that are missing, stale or orphaned without calling the LLM (for CI).
`verify` runs the generated tests with pytest and reports the outcome per scenario.
The conceptualTests stay the source of truth; prompts live in spec/runner/runner-spec.json ("generate").
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import ctx_run

SPEC = ctx_run._SPEC["generate"]
DEFAULT_OUT = os.path.join("tests", "contextdoc")
HASH_CHARS = 12

_BLOCK_RE = re.compile(
    r'^# --- contextdoc scenario: (?P<name>"(?:[^"\\\n]|\\.)*") sha256:(?P<hash>[0-9a-f]+) ---\n(?P<code>.*?)^# --- end scenario ---\n?',
    re.M | re.S,
)


# ---------------------------------------------------------------------------
# Scenario identity and file layout
# ---------------------------------------------------------------------------

def scenario_hash(scenario: dict) -> str:
    """Short hash of the scenario as canonical JSON (the same serialization as the cache key)."""
    return hashlib.sha256(json.dumps(scenario, sort_keys=True).encode()).hexdigest()[:HASH_CHARS]


def framework_for(source_path: str) -> str | None:
    return SPEC["frameworks"].get(os.path.splitext(source_path)[1].lower())


def test_file_for(source_path: str, out_dir: str) -> str:
    """tests/contextdoc/test_<path_of_the_source>.py: unique per source, readable."""
    rel = os.path.relpath(source_path)
    slug = re.sub(r"[^0-9A-Za-z]+", "_", os.path.splitext(rel)[0]).strip("_")
    return os.path.join(out_dir, f"test_{slug}.py")


@dataclass
class Block:
    name: str
    hash: str
    code: str


def parse_blocks(text: str) -> list[Block]:
    return [Block(json.loads(m["name"]), m["hash"], m["code"]) for m in _BLOCK_RE.finditer(text)]


def render_file(ctx_path: str, source_path: str, test_path: str, blocks: list[Block]) -> str:
    source_dir = os.path.relpath(os.path.dirname(os.path.abspath(source_path)), os.path.dirname(os.path.abspath(test_path)))
    header = ctx_run._fill(SPEC["fileHeader"], ctx=os.path.relpath(ctx_path), source_dir=json.dumps(source_dir))
    parts = [header]
    for b in blocks:
        start = ctx_run._fill(SPEC["blockStart"], name=json.dumps(b.name, ensure_ascii=False), hash=b.hash)
        parts.append(f"\n{start}\n{b.code.rstrip()}\n{SPEC['blockEnd']}\n")
    return "".join(parts)


def test_functions(code: str) -> list[str]:
    """Top-level test functions (and Test* classes) defined in a block."""
    tree = ast.parse(code)
    return [n.name for n in tree.body
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"))
            or (isinstance(n, ast.ClassDef) and n.name.startswith("Test"))]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def local_imports(source_path: str, source_content: str) -> list[str]:
    """Paths of the modules in the same folder that SOURCE imports (their APIs are needed to build objects)."""
    try:
        tree = ast.parse(source_content)
    except SyntaxError:
        return []
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level in (0, 1):
            names.add(node.module)
    folder = os.path.dirname(os.path.abspath(source_path))
    paths = [os.path.join(folder, f"{n}.py") for n in sorted(names) if "." not in n]
    return [p for p in paths if os.path.isfile(p) and os.path.abspath(p) != os.path.abspath(source_path)]


def build_generate_prompt(scenario: dict, source_path: str, source_content: str) -> str:
    module = os.path.splitext(os.path.basename(source_path))[0]
    parts = [ctx_run._fill(SPEC["source"], label=os.path.relpath(source_path), source=source_content)]
    for path in local_imports(source_path, source_content):
        with open(path, encoding="utf-8") as f:
            parts.append(ctx_run._fill(SPEC["related"], label=os.path.relpath(path), source=f.read()))
    parts += [
        ctx_run._fill(SPEC["module"], module=module),
        ctx_run._fill(SPEC["scenario"], name=scenario.get("name", "unnamed")),
        SPEC["stepsHeader"],
    ]
    for i, step in enumerate(scenario.get("steps", []), 1):
        parts.append(ctx_run._fill(SPEC["step"], n=i, action=step.get("action", ""), expect=step.get("expect", "")))
    parts.append(SPEC["instructions"])
    return "\n".join(parts)


def clean_code(raw: str) -> tuple[str | None, str | None]:
    """(code, None) if RAW is valid Python with at least one test, else (None, reason)."""
    code = re.sub(r"^\s*```(?:python|py)?\s*\n|\n?```\s*$", "", raw.strip())
    if "# --- contextdoc scenario:" in code or SPEC["blockEnd"] in code:
        return None, "the answer contains block markers"
    try:
        tests = test_functions(code)
    except SyntaxError as exc:
        return None, f"syntax error: {exc.msg} (line {exc.lineno})"
    if not tests:
        return None, "no top-level test function"
    return code, None


def generate_block(model: str, scenario: dict, source_path: str, source_content: str, timeout: int) -> tuple[str | None, str | None]:
    """Asks the LLM for the scenario's tests, with one retry on an invalid answer."""
    user = build_generate_prompt(scenario, source_path, source_content)
    error = None
    for _ in range(2):
        prompt = user if error is None else user + ctx_run._fill(SPEC["retry"], error=error)
        try:
            raw = ctx_run.call_llm(model, SPEC["system"], prompt, timeout=timeout)
        except Exception as exc:  # noqa: BLE001 — reported per scenario, never fatal
            return None, ctx_run._fill(ctx_run._SPEC["results"]["llmError"], error=exc)
        code, error = clean_code(raw)
        if code:
            return code, None
    return None, f"could not generate valid tests: {error}"


@dataclass
class ScenarioStatus:
    name: str
    state: str          # kept | generated | regenerated | removed | failed | missing | stale | orphan | ok
    detail: str = ""


@dataclass
class FileReport:
    ctx_path: str
    test_path: str | None
    skipped: str | None = None
    scenarios: list[ScenarioStatus] = field(default_factory=list)


def plan_file(ctx_path: str, out_dir: str):
    """(source_path, source_content, scenarios, test_path, existing blocks by name) or a skip reason."""
    ctx = ctx_run.load_ctx(ctx_path)
    scenarios = ctx.get("conceptualTests") or []
    if not scenarios:
        return "no conceptualTests"
    source_path, source_content, warning = ctx_run.resolve_source(ctx_path)
    if source_content is None:
        return warning or "source not available"
    if framework_for(source_path) is None:
        return f"no test framework for {os.path.splitext(source_path)[1] or 'this file type'} yet (supported: pytest)"
    test_path = test_file_for(source_path, out_dir)
    existing = {}
    if os.path.isfile(test_path):
        with open(test_path, encoding="utf-8") as f:
            existing = {b.name: b for b in parse_blocks(f.read())}
    return source_path, source_content, scenarios, test_path, existing


def generate_file(ctx_path: str, model: str, out_dir: str, force: bool, timeout: int) -> FileReport:
    plan = plan_file(ctx_path, out_dir)
    if isinstance(plan, str):
        return FileReport(ctx_path, None, skipped=plan)
    source_path, source_content, scenarios, test_path, existing = plan
    report = FileReport(ctx_path, test_path)
    blocks: list[Block] = []
    for scenario in scenarios:
        name = scenario.get("name", "unnamed")
        h = scenario_hash(scenario)
        old = existing.pop(name, None)
        if old and old.hash == h and not force:
            blocks.append(old)
            report.scenarios.append(ScenarioStatus(name, "kept"))
            continue
        code, error = generate_block(model, scenario, source_path, source_content, timeout)
        if code is None:
            report.scenarios.append(ScenarioStatus(name, "failed", error or ""))
            continue
        blocks.append(Block(name, h, code))
        report.scenarios.append(ScenarioStatus(name, "regenerated" if old else "generated",
                                               "scenario changed" if old and old.hash != h else ""))
    for name in existing:
        report.scenarios.append(ScenarioStatus(name, "removed", "scenario no longer in the .ctx"))
    if blocks:
        os.makedirs(os.path.dirname(test_path), exist_ok=True)
        with open(test_path, "w", encoding="utf-8") as f:
            f.write(render_file(ctx_path, source_path, test_path, blocks))
    elif os.path.isfile(test_path):
        os.remove(test_path)
    return report


def check_file(ctx_path: str, out_dir: str) -> FileReport:
    plan = plan_file(ctx_path, out_dir)
    if isinstance(plan, str):
        return FileReport(ctx_path, None, skipped=plan)
    _, _, scenarios, test_path, existing = plan
    report = FileReport(ctx_path, test_path)
    for scenario in scenarios:
        name = scenario.get("name", "unnamed")
        old = existing.pop(name, None)
        if old is None:
            report.scenarios.append(ScenarioStatus(name, "missing", "no generated test"))
        elif old.hash != scenario_hash(scenario):
            report.scenarios.append(ScenarioStatus(name, "stale", "scenario changed since the test was generated"))
        else:
            report.scenarios.append(ScenarioStatus(name, "ok"))
    for name in existing:
        report.scenarios.append(ScenarioStatus(name, "orphan", "scenario no longer in the .ctx"))
    return report


# ---------------------------------------------------------------------------
# Verify: run the generated tests, report per scenario
# ---------------------------------------------------------------------------

details_of_last_run: dict[str, dict[str, str]] = {}


def verify_files(test_paths: list[str], timeout: int = 600) -> dict[str, dict[str, str]]:
    """{test file: {scenario: passed | failed | skipped | error}} from a pytest run with JUnit XML.
    The first failure message of each scenario is in details_of_last_run[file][scenario]."""
    details_of_last_run.clear()
    tests_of: dict[str, dict[str, str]] = {}   # file -> test function -> scenario
    for path in test_paths:
        with open(path, encoding="utf-8") as f:
            tests_of[path] = {t: b.name for b in parse_blocks(f.read()) for t in test_functions(b.code)}
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = os.path.join(tmp, "junit.xml")
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml_path}", *test_paths],
                       capture_output=True, text=True, timeout=timeout)
        outcomes: dict[str, dict[str, str]] = {p: {} for p in test_paths}
        if not os.path.isfile(xml_path):
            return {p: {s: "error" for s in set(tests_of[p].values())} for p in test_paths}
        root = ET.parse(xml_path).getroot()
    rank = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}
    for case in root.iter("testcase"):
        func = case.get("name", "").split("[")[0]
        module = case.get("classname", "").split(".")[-1]
        problem = case.find("failure") if case.find("failure") is not None else case.find("error")
        result = ("failed" if case.find("failure") is not None else
                  "error" if case.find("error") is not None else
                  "skipped" if case.find("skipped") is not None else "passed")
        for path, tests in tests_of.items():
            if os.path.splitext(os.path.basename(path))[0] == module or module in tests:
                scenario = tests.get(func) or tests.get(module)
                if scenario:
                    prev = outcomes[path].get(scenario, "passed")
                    outcomes[path][scenario] = max(prev, result, key=rank.get)
                    if problem is not None and scenario not in details_of_last_run.setdefault(path, {}):
                        details_of_last_run[path][scenario] = (problem.get("message") or "").splitlines()[0][:160] if problem.get("message") else ""
    # a scenario whose tests never ran (e.g. import error in the file) is an error
    for path, tests in tests_of.items():
        for scenario in set(tests.values()):
            outcomes[path].setdefault(scenario, "error")
    return outcomes
