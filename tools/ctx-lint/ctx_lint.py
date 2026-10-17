#!/usr/bin/env python3
"""ctx-lint: warns about .ctx files that drift from ContextDoc's principles. Never blocking by itself.

Rules (spec/lint/lint-spec.json, shared with the VS Code extension):
  L001 too long            L005 many "error on missing/invalid input" scenarios
  L002 copied signatures   L006 steps without an observable expect
  L003 unknown sections    L007 invalid YAML
  L004 duplicated in project.ctx   L008 purpose longer than one line

    python tools/ctx-lint/ctx_lint.py PATH... [--strict] [--format text|json]
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

import click
import yaml


def _load_spec() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    for path in (os.environ.get("CTX_LINT_SPEC"), os.path.join(here, "contextdoc_spec", "lint-spec.json"),
                 os.path.join(here, "lint-spec.json"),
                 os.path.join(here, "..", "..", "spec", "lint", "lint-spec.json")):
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
    raise RuntimeError("lint-spec.json not found (set CTX_LINT_SPEC to its path)")


SPEC = _load_spec()
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".mypy_cache"}


def _msg(code: str, **values: object) -> str:
    return re.sub(r"\$\{(\w+)\}", lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0),
                  SPEC["messages"][code])


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


@dataclass(frozen=True, order=True)
class Finding:
    line: int
    code: str
    message: str


class _Lines:
    """Finds the line where a piece of text appears, for the report."""

    def __init__(self, text: str) -> None:
        self.lines = text.splitlines()

    def of(self, needle: str, start: int = 1) -> int:
        """First line, from START on, containing the beginning of NEEDLE (whitespace-insensitive)."""
        probe = _norm(needle)[:40]
        if probe:
            for i in range(start - 1, len(self.lines)):
                if probe in _norm(self.lines[i]):
                    return i + 1
        return start

    def key(self, name: str) -> int:
        for i, line in enumerate(self.lines):
            if re.match(rf"^{re.escape(name)}\s*:", line):
                return i + 1
        return 1


def _project_ctx(ctx_path: str, root: str) -> str | None:
    d = os.path.dirname(os.path.abspath(ctx_path))
    root = os.path.abspath(root)
    while True:
        candidate = os.path.join(d, "project.ctx")
        if os.path.isfile(candidate) and os.path.abspath(candidate) != os.path.abspath(ctx_path):
            return candidate
        if d == root or os.path.dirname(d) == d or not d.startswith(root):
            return None
        d = os.path.dirname(d)


def _strings(value) -> list[str]:
    """Every string inside a YAML value (lists, dicts, nested)."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _items(data: dict, key: str) -> list[str]:
    value = data.get(key)
    if isinstance(value, dict):
        return [str(v) for v in value.values()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def lint_file(ctx_path: str, root: str = ".") -> list[Finding]:
    with open(ctx_path, encoding="utf-8") as f:
        text = f.read()
    lines = _Lines(text)
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return [Finding((mark.line + 1) if mark else 1, "L007", _msg("L007", error=_norm(getattr(exc, "problem", None) or exc)))]
    if not isinstance(data, dict):
        return [Finding(1, "L007", _msg("L007", error="the top level must be a mapping of sections"))]
    findings: list[Finding] = []

    # L001: length
    if len(lines.lines) > SPEC["maxLines"]:
        findings.append(Finding(1, "L001", _msg("L001", lines=len(lines.lines), max=SPEC["maxLines"])))

    # L003: sections outside the schema
    allowed = SPEC["sections"]
    for key in data:
        if key not in allowed:
            hint = _msg("L003legacy") if key in SPEC["legacySections"] else _msg("L003unknown")
            findings.append(Finding(lines.key(str(key)), "L003", _msg("L003", key=key, allowed=", ".join(allowed), hint=hint)))

    # L008: purpose
    purpose = data.get("purpose")
    if isinstance(purpose, str) and (len(purpose) > SPEC["purposeMaxChars"] or "\n" in purpose.strip()):
        findings.append(Finding(lines.key("purpose"), "L008", _msg("L008", chars=len(purpose.strip()))))

    # L002: signatures copied from the source
    source = ctx_path[:-4]
    pattern = SPEC["signaturePatterns"].get(os.path.splitext(source)[1].lower())
    if pattern and os.path.isfile(source):
        with open(source, encoding="utf-8", errors="replace") as f:
            signatures = {_norm(m.group(0)) for m in re.finditer(pattern, f.read(), re.M)}
        signatures = {s for s in signatures if len(s) >= SPEC["minSignatureChars"]}
        reported = set()
        for s in _strings({k: v for k, v in data.items() if k in allowed}):
            for sig in signatures:
                if sig in _norm(s) and sig not in reported:
                    reported.add(sig)
                    findings.append(Finding(lines.of(sig), "L002", _msg("L002", signature=sig)))

    # L004: duplicated in project.ctx
    if os.path.basename(ctx_path) != "project.ctx":
        project = _project_ctx(ctx_path, root)
        if project:
            try:
                with open(project, encoding="utf-8") as f:
                    pdata = yaml.safe_load(f) or {}
            except (OSError, yaml.YAMLError):
                pdata = {}
            if isinstance(pdata, dict):
                theirs = {_norm(s) for k in ("tensions", "workflows") for s in _items(pdata, k)}
                for k in ("tensions", "workflows"):
                    for s in _items(data, k):
                        if _norm(s) in theirs:
                            findings.append(Finding(lines.of(s), "L004", _msg("L004", other=os.path.relpath(project, os.path.dirname(os.path.abspath(ctx_path))))))

    # L005 / L006: scenarios
    action_re = re.compile(SPEC["validation"]["action"], re.I)
    expect_re = re.compile(SPEC["validation"]["expect"], re.I)
    validation_steps = 0
    total_steps = 0
    tests_line = lines.key("conceptualTests")
    vague = {v.lower() for v in SPEC["vagueExpects"]}
    for scenario in data.get("conceptualTests") or []:
        if not isinstance(scenario, dict):
            continue
        for step in scenario.get("steps") or []:
            if not isinstance(step, dict):
                continue
            total_steps += 1
            action, expect = str(step.get("action", "")), step.get("expect")
            at = lines.of(action, tests_line) if action else tests_line
            if expect is None or not str(expect).strip():
                findings.append(Finding(at, "L006", _msg("L006missing")))
                continue
            if str(expect).strip().strip(".!").lower() in vague:
                findings.append(Finding(lines.of(str(expect), at), "L006", _msg("L006vague", expect=str(expect).strip())))
            if action_re.search(action) and expect_re.search(str(expect)):
                validation_steps += 1
    v = SPEC["validation"]
    if validation_steps >= v["minSteps"] and validation_steps >= v["minShare"] * total_steps:
        findings.append(Finding(tests_line, "L005", _msg("L005", count=validation_steps, total=total_steps)))

    return sorted(findings)


def collect(paths: tuple[str, ...]) -> list[str]:
    out = []
    for p in paths:
        if os.path.isfile(p):
            if p.endswith(".ctx"):
                out.append(p)
            continue
        for dirpath, dirnames, filenames in os.walk(p):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            out += [os.path.join(dirpath, f) for f in filenames if f.endswith(".ctx")]
    return sorted(set(out))


@click.command()
@click.argument("paths", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--strict", is_flag=True, help="Exit 1 when there are warnings (for CI).")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.option("--no-color", is_flag=True, help="Disable ANSI colors.")
def cli(paths: tuple[str, ...], strict: bool, fmt: str, no_color: bool) -> None:
    """Lint .ctx files under PATHS against ContextDoc's principles (warnings only)."""
    color = not no_color and sys.stdout.isatty()
    y = (lambda s: f"\033[33m{s}\033[0m") if color else (lambda s: s)
    files = collect(paths)
    root = os.path.commonpath([os.path.abspath(p) for p in paths]) if paths else "."
    if os.path.isfile(root):
        root = os.path.dirname(root)
    report = {f: lint_file(f, root) for f in files}
    total = sum(len(v) for v in report.values())
    if fmt == "json":
        click.echo(json.dumps({os.path.relpath(f): [vars(x) for x in v] for f, v in report.items()}, indent=2))
    else:
        for f, findings in report.items():
            for x in findings:
                click.echo(f"{os.path.relpath(f)}:{x.line}: {y(x.code)} {x.message}")
        click.echo(f"{len(files)} .ctx file(s), {total} warning(s)" if total else f"✓  {len(files)} .ctx file(s), no warnings")
    sys.exit(1 if strict and total else 0)


if __name__ == "__main__":
    cli()
