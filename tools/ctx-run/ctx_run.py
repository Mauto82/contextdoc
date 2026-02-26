#!/usr/bin/env python3
"""
ctx-run: LLM-powered runner for ContextDoc conceptual tests.

Reads .ctx files, sends source code + conceptualTests to an LLM,
reports pass/fail per step per scenario.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

import click
import litellm
import yaml

# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------

GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

_color_enabled = True


def c(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if _color_enabled else text


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    action: str
    expect: str
    passed: bool
    explanation: str = ""


@dataclass
class ScenarioResult:
    name: str
    steps: list[StepResult] = field(default_factory=list)
    overall_passed: bool = False
    error: str | None = None
    fix_suggestion: str | None = None   # populated when --fix is set
    from_cache: bool = False            # True when result came from cache


@dataclass
class FileResult:
    ctx_path: str
    source_path: str | None
    scenarios: list[ScenarioResult] = field(default_factory=list)
    skipped: bool = False        # no conceptualTests section
    error: str | None = None     # file-level error


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

_SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache"}


def collect_ctx_files(target: str) -> list[str]:
    """Return sorted list of .ctx paths for a file or directory target."""
    if os.path.isfile(target):
        if not target.endswith(".ctx"):
            raise click.BadParameter(f"File must end in .ctx: {target}")
        return [target]

    if os.path.isdir(target):
        paths = []
        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for f in files:
                if f.endswith(".ctx"):
                    paths.append(os.path.join(root, f))
        if not paths:
            raise click.ClickException(f"No .ctx files found in: {target}")
        return sorted(paths)

    raise click.BadParameter(f"Path not found: {target}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def load_ctx(ctx_path: str) -> dict:
    """Parse .ctx YAML. Returns empty dict on any error (error reported upstream)."""
    with open(ctx_path) as f:
        return yaml.safe_load(f) or {}


_LANG_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".go": "go", ".rb": "ruby", ".rs": "rust", ".java": "java",
    ".cs": "csharp", ".php": "php", ".swift": "swift", ".kt": "kotlin",
}


def resolve_source(ctx_path: str) -> tuple[str | None, str | None, str | None]:
    """
    Returns (source_path, source_content, warning).
    warning is non-None when source is missing — not a hard error.
    """
    if not ctx_path.endswith(".ctx"):
        return None, None, "cannot derive source path: ctx file does not end in .ctx"
    source_path = ctx_path[:-4]
    if not os.path.isfile(source_path):
        return source_path, None, f"source file not found: {source_path}"
    with open(source_path) as f:
        return source_path, f.read(), None


def detect_language(source_path: str | None) -> str:
    if source_path is None:
        return ""
    ext = os.path.splitext(source_path)[1].lower()
    return _LANG_MAP.get(ext, "")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

_CACHE_VERSION = 1


def _cache_path() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "ctx-run", "cache.json")


def load_cache() -> dict:
    """Load the on-disk cache. Returns empty dict on any error."""
    path = _cache_path()
    if os.path.isfile(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if data.get("version") == _CACHE_VERSION:
                return data.get("entries", {})
        except Exception:
            pass
    return {}


def save_cache(entries: dict) -> None:
    """Atomically write the cache to disk."""
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump({"version": _CACHE_VERSION, "entries": entries}, f, indent=2)
    os.replace(tmp, path)


def make_cache_key(scenario: dict, source_content: str | None, model: str) -> str:
    """SHA-256 of scenario JSON + source content + model name."""
    data = json.dumps(scenario, sort_keys=True) + (source_content or "") + model
    return hashlib.sha256(data.encode()).hexdigest()


def _scenario_to_cache_entry(result: ScenarioResult) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": {
            "name": result.name,
            "overall_passed": result.overall_passed,
            "error": result.error,
            "steps": [
                {
                    "action": s.action,
                    "expect": s.expect,
                    "passed": s.passed,
                    "explanation": s.explanation,
                }
                for s in result.steps
            ],
        },
    }


def _scenario_from_cache_entry(entry: dict) -> ScenarioResult:
    d = entry["result"]
    steps = [
        StepResult(
            action=s["action"],
            expect=s["expect"],
            passed=s["passed"],
            explanation=s["explanation"],
        )
        for s in d.get("steps", [])
    ]
    return ScenarioResult(
        name=d["name"],
        steps=steps,
        overall_passed=d.get("overall_passed", False),
        error=d.get("error"),
        from_cache=True,
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    return (
        "You are a code behavior analyzer. "
        "Your job is to reason about whether source code correctly implements described behaviors — "
        "without executing the code.\n\n"
        "You will be given source code and a test scenario with sequential steps (action + expected outcome). "
        "For each step, reason about whether the source code, as written, would produce the expected outcome.\n\n"
        "Respond with valid JSON only. No explanation outside the JSON object. No markdown fences."
    )


def build_user_message(
    scenario: dict,
    source_path: str | None,
    source_content: str | None,
    source_warning: str | None,
    language: str,
) -> str:
    parts: list[str] = []

    # Source section
    if source_content:
        label = source_path or "unknown"
        fence = f"```{language}" if language else "```"
        parts.append(f"Source file: {label}\n{fence}\n{source_content}\n```")
    else:
        note = source_warning or "source file unavailable"
        parts.append(f"Source file: NOT AVAILABLE ({note})")
        parts.append(
            "Note: since source is unavailable, mark all steps as failed "
            "with explanation 'source code not available for analysis'."
        )

    # Scenario
    name = scenario.get("name", "unnamed")
    steps = scenario.get("steps", [])
    parts.append(f'\nScenario: "{name}"')
    parts.append("Steps:")
    for i, step in enumerate(steps, 1):
        parts.append(
            f'{i}. action: "{step.get("action", "")}"\n'
            f'   expect: "{step.get("expect", "")}"'
        )

    # Response format instruction
    parts.append(
        '\nFor each step, evaluate whether the source code produces the expected outcome.\n\n'
        "Respond with this exact JSON structure:\n"
        '{\n'
        '  "overall": true or false,\n'
        '  "steps": [\n'
        '    {\n'
        '      "action": "the action text",\n'
        '      "passed": true or false,\n'
        '      "explanation": "one sentence, max 25 words"\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        'Rules:\n'
        '- "overall" must be true only if ALL steps pass\n'
        '- Include one entry per step, in the same order\n'
        '- "explanation" is always required, even for passing steps\n'
        '- Do not include any text outside the JSON object'
    )

    return "\n".join(parts)


def build_fix_prompt(
    scenario: dict,
    failed_steps: list[StepResult],
    source_path: str | None,
    source_content: str | None,
    language: str,
) -> str:
    """Build the prompt for --fix: asks the LLM what to change to make the failing steps pass."""
    parts: list[str] = []

    if source_content:
        label = source_path or "unknown"
        fence = f"```{language}" if language else "```"
        parts.append(f"Source file: {label}\n{fence}\n{source_content}\n```")
    else:
        parts.append("Source file: NOT AVAILABLE")

    name = scenario.get("name", "unnamed")
    parts.append(f'\nScenario "{name}" has the following failing steps:')
    for step in failed_steps:
        parts.append(f'- action: "{step.action}"')
        parts.append(f'  expected: "{step.expect}"')
        if step.explanation:
            parts.append(f'  analysis: "{step.explanation}"')

    parts.append(
        "\nSuggest the minimal code change that would make these failing steps pass. "
        "Be specific: name the function or method, and describe exactly what to add, change, or remove. "
        "Reply in 2-4 sentences only. No code blocks needed."
    )

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------

def call_llm(model: str, system: str, user: str, timeout: int = 60) -> str:
    response = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0,
        max_tokens=1500,
        timeout=timeout,
    )
    return response.choices[0].message.content or ""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_llm_response(raw: str, expected_steps: int) -> dict | None:
    """
    Three-layer parsing with graceful fallback.
    Returns parsed dict or None if all attempts fail.
    """
    def try_parse(text: str) -> dict | None:
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return None

    # Layer 1: direct parse
    result = try_parse(raw)
    if result:
        return result

    # Layer 2: strip markdown fences
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    result = try_parse(stripped)
    if result:
        return result

    # Layer 3: extract outermost {...} block
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        result = try_parse(match.group())
        if result:
            return result

    return None


def build_scenario_result(
    scenario: dict,
    raw_response: str,
    parsed: dict | None,
) -> ScenarioResult:
    name = scenario.get("name", "unnamed")
    expected_steps = scenario.get("steps", [])

    if parsed is None:
        return ScenarioResult(
            name=name,
            overall_passed=False,
            error=f"LLM response could not be parsed. Raw: {raw_response[:200]}",
        )

    llm_steps = parsed.get("steps", [])
    step_results: list[StepResult] = []

    for i, expected in enumerate(expected_steps):
        if i < len(llm_steps):
            llm_step = llm_steps[i]
            passed = bool(llm_step.get("passed", False))
            explanation = llm_step.get("explanation", "")
        else:
            passed = False
            explanation = "Step missing from LLM response"

        step_results.append(StepResult(
            action=expected.get("action", ""),
            expect=expected.get("expect", ""),
            passed=passed,
            explanation=explanation,
        ))

    # Recompute overall from steps (do not trust LLM's "overall" field)
    overall_passed = all(s.passed for s in step_results)

    return ScenarioResult(
        name=name,
        steps=step_results,
        overall_passed=overall_passed,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_scenario(
    model: str,
    scenario: dict,
    source_path: str | None,
    source_content: str | None,
    source_warning: str | None,
    language: str,
    timeout: int = 60,
    use_cache: bool = True,
    cache_entries: dict | None = None,
    fix: bool = False,
) -> ScenarioResult:
    # Check cache
    if use_cache and cache_entries is not None:
        key = make_cache_key(scenario, source_content, model)
        if key in cache_entries:
            result = _scenario_from_cache_entry(cache_entries[key])
            return result

    # Run LLM
    system = build_system_prompt()
    user = build_user_message(scenario, source_path, source_content, source_warning, language)
    try:
        raw = call_llm(model, system, user, timeout=timeout)
    except Exception as exc:
        return ScenarioResult(
            name=scenario.get("name", "unnamed"),
            overall_passed=False,
            error=f"LLM error: {exc}",
        )
    parsed = parse_llm_response(raw, len(scenario.get("steps", [])))
    result = build_scenario_result(scenario, raw, parsed)

    # Save to cache (only successful evaluations — not errors or parse failures)
    if use_cache and cache_entries is not None and result.error is None:
        key = make_cache_key(scenario, source_content, model)
        cache_entries[key] = _scenario_to_cache_entry(result)

    # --fix: ask for a fix suggestion for failing scenarios
    if fix and not result.overall_passed and result.error is None:
        failed_steps = [s for s in result.steps if not s.passed]
        fix_system = (
            "You are a code improvement advisor. "
            "Given failing conceptual test steps and source code, "
            "suggest the minimal code change to make the tests pass."
        )
        fix_user = build_fix_prompt(scenario, failed_steps, source_path, source_content, language)
        try:
            result.fix_suggestion = call_llm(model, fix_system, fix_user, timeout=timeout)
        except Exception:
            pass  # fix is best-effort — never block the main run

    return result


def run_ctx_file(
    ctx_path: str,
    model: str,
    fail_fast: bool,
    timeout: int = 60,
    use_cache: bool = True,
    cache_entries: dict | None = None,
    fix: bool = False,
) -> FileResult:
    # Load .ctx
    try:
        ctx = load_ctx(ctx_path)
    except Exception as exc:
        return FileResult(ctx_path=ctx_path, source_path=None, error=str(exc))

    conceptual_tests = ctx.get("conceptualTests")
    if not conceptual_tests:
        return FileResult(ctx_path=ctx_path, source_path=None, skipped=True)

    # Load source
    source_path, source_content, source_warning = resolve_source(ctx_path)
    language = detect_language(source_path)

    scenarios: list[ScenarioResult] = []
    for scenario in conceptual_tests:
        result = run_scenario(
            model, scenario, source_path, source_content, source_warning, language,
            timeout=timeout, use_cache=use_cache, cache_entries=cache_entries, fix=fix,
        )
        scenarios.append(result)
        if fail_fast and not result.overall_passed:
            break

    return FileResult(
        ctx_path=ctx_path,
        source_path=source_path,
        scenarios=scenarios,
    )


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def relative_path(path: str) -> str:
    try:
        return os.path.relpath(path)
    except ValueError:
        return path


def render_text(results: list[FileResult], verbose: bool) -> None:
    for file_result in results:
        label = relative_path(file_result.ctx_path)

        if file_result.error:
            click.echo(c(BOLD, label))
            click.echo(f"  {c(RED, 'ERROR')} {file_result.error}")
            click.echo()
            continue

        if file_result.skipped:
            click.echo(c(DIM, f"{label}  (no conceptualTests, skipped)"))
            continue

        click.echo(c(BOLD, label))
        if file_result.source_path and not os.path.isfile(file_result.source_path):
            click.echo(f"  {c(YELLOW, 'WARNING')} source file not found: {file_result.source_path}")

        for scenario in file_result.scenarios:
            cache_label = f"  {c(DIM, '[cached]')}" if scenario.from_cache else ""
            click.echo(f"  scenario: {c(BOLD, scenario.name)}{cache_label}")

            if scenario.error:
                click.echo(f"    {c(RED, 'ERROR')} {scenario.error}")
                continue

            for step in scenario.steps:
                marker = c(GREEN, "[PASS]") if step.passed else c(RED, "[FAIL]")
                click.echo(f"    {marker} {step.action}")
                if not step.passed or verbose:
                    click.echo(f"           {c(DIM, step.explanation)}")

            if scenario.fix_suggestion:
                click.echo(f"\n    {c(CYAN, '→ Fix suggestion:')}")
                for line in scenario.fix_suggestion.strip().splitlines():
                    click.echo(f"      {line}")
                click.echo()

        click.echo()


def render_text_summary(results: list[FileResult]) -> tuple[int, int, int, int]:
    """Returns (files_run, scenarios_total, steps_passed, steps_total)."""
    files_run = sum(1 for r in results if not r.skipped and not r.error)
    scenarios_total = sum(len(r.scenarios) for r in results)
    steps_passed = sum(
        sum(1 for s in sc.steps if s.passed)
        for r in results for sc in r.scenarios
    )
    steps_total = sum(
        len(sc.steps)
        for r in results for sc in r.scenarios
    )
    return files_run, scenarios_total, steps_passed, steps_total


def render_json_output(results: list[FileResult]) -> None:
    files_run, scenarios_total, steps_passed, steps_total = render_text_summary(results)
    failed_scenarios = sum(
        1 for r in results for sc in r.scenarios if not sc.overall_passed
    )
    output = {
        "summary": {
            "files": files_run,
            "scenarios": scenarios_total,
            "steps_passed": steps_passed,
            "steps_total": steps_total,
            "failed_scenarios": failed_scenarios,
        },
        "results": [
            {
                "ctx_path": r.ctx_path,
                "source_path": r.source_path,
                "skipped": r.skipped,
                "error": r.error,
                "scenarios": [
                    {
                        "name": sc.name,
                        "overall_passed": sc.overall_passed,
                        "error": sc.error,
                        "from_cache": sc.from_cache,
                        "fix_suggestion": sc.fix_suggestion,
                        "steps": [
                            {
                                "action": st.action,
                                "expect": st.expect,
                                "passed": st.passed,
                                "explanation": st.explanation,
                            }
                            for st in sc.steps
                        ],
                    }
                    for sc in r.scenarios
                ],
            }
            for r in results
        ],
    }
    click.echo(json.dumps(output, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """ctx-run: LLM-powered runner for ContextDoc conceptual tests."""


@cli.command()
@click.argument("path")
@click.option(
    "--model",
    default=None,
    help="LiteLLM model string (e.g. ollama/llama3, claude-haiku-20240307, gpt-4o-mini). "
         "Defaults to $CTX_MODEL env var or claude-haiku-20240307.",
)
@click.option("--fail-fast", is_flag=True, help="Stop after first failing scenario.")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors.")
@click.option(
    "--output",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format.",
)
@click.option("--verbose", is_flag=True, help="Show LLM explanations for passing steps too.")
@click.option(
    "--timeout",
    default=60,
    show_default=True,
    type=int,
    help="LLM call timeout in seconds. Useful with slow local models.",
)
@click.option("--no-cache", is_flag=True, help="Disable result caching — always call the LLM.")
@click.option(
    "--fix",
    is_flag=True,
    help="After each failing scenario, ask the LLM to suggest a fix.",
)
def run(
    path: str,
    model: str | None,
    fail_fast: bool,
    no_color: bool,
    output: str,
    verbose: bool,
    timeout: int,
    no_cache: bool,
    fix: bool,
) -> None:
    """Run conceptual tests from PATH (.ctx file or directory)."""
    global _color_enabled
    _color_enabled = not no_color and sys.stdout.isatty()

    resolved_model = model or os.environ.get("CTX_MODEL") or "claude-haiku-20240307"
    use_cache = not no_cache

    # Load cache once for the whole run
    cache_entries = load_cache() if use_cache else {}

    try:
        ctx_files = collect_ctx_files(path)
    except (click.BadParameter, click.ClickException) as exc:
        click.echo(str(exc), err=True)
        sys.exit(2)

    results: list[FileResult] = []
    for ctx_path in ctx_files:
        result = run_ctx_file(
            ctx_path, resolved_model, fail_fast,
            timeout=timeout, use_cache=use_cache,
            cache_entries=cache_entries, fix=fix,
        )
        results.append(result)
        if fail_fast and any(not sc.overall_passed for sc in result.scenarios):
            break

    # Persist cache after all runs
    if use_cache and cache_entries:
        try:
            save_cache(cache_entries)
        except Exception:
            pass  # cache write failure is never fatal

    if output == "json":
        render_json_output(results)
    else:
        render_text(results, verbose)
        files_run, scenarios_total, steps_passed, steps_total = render_text_summary(results)
        failed = sum(1 for r in results for sc in r.scenarios if not sc.overall_passed)
        skipped = sum(1 for r in results if r.skipped)

        sep = "─" * 50
        click.echo(sep)
        summary_parts = [
            f"{files_run} file{'s' if files_run != 1 else ''}",
            f"{scenarios_total} scenario{'s' if scenarios_total != 1 else ''}",
            f"{steps_passed}/{steps_total} steps passed",
        ]
        if skipped:
            summary_parts.append(f"{skipped} skipped")
        click.echo("  " + "   ".join(summary_parts))
        if failed:
            click.echo(f"  {c(RED, f'{failed} scenario failed' if failed == 1 else f'{failed} scenarios FAILED')}")
        else:
            click.echo(f"  {c(GREEN, 'all scenarios passed')}")

    any_failed = any(
        not sc.overall_passed
        for r in results for sc in r.scenarios
    )
    any_error = any(r.error for r in results)
    sys.exit(1 if any_failed or any_error else 0)


@cli.command("clear-cache")
def clear_cache() -> None:
    """Delete the local LLM result cache."""
    path = _cache_path()
    if os.path.isfile(path):
        os.remove(path)
        click.echo(f"Cache cleared: {path}")
    else:
        click.echo("No cache found.")


if __name__ == "__main__":
    cli()
