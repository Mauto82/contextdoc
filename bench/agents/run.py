#!/usr/bin/env python3
"""Agents with and without ContextDoc: does the context stop an agent from breaking documented tensions?

Each task (tasks.py) asks for a change whose obvious implementation breaks a tension of the examples.
The agent (Claude Code, non-interactive) works on a fresh copy of the example in one of four conditions:

  none        no .ctx files, no CLAUDE.md
  ctx         .ctx files only (the agent may or may not open them)
  ctx+claude  .ctx files and the example's CLAUDE.md (instructions to read them)
  ctx+hook    .ctx files and the Claude Code hook (integrations/claude-code), no CLAUDE.md

Measured from the files, not from the agent's words: tension violated (task check), conceptualTests
modified, files changed. User settings, plugins and MCP servers are not loaded (--setting-sources
project,local, --strict-mcp-config), so only the project under test shapes the agent.

    python bench/agents/run.py --model haiku --reps 3 --jobs 4 --out bench/results/agents-<date>
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from tasks import TASKS

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "integrations" / "claude-code" / "contextdoc_hook.py"
CONDITIONS = ["none", "ctx", "ctx+claude", "ctx+hook"]
TOP_KEY = re.compile(r"^[A-Za-z_]\w*\s*:")


def tests_section(text: str) -> str:
    lines, inside = [], False
    for line in text.splitlines():
        if TOP_KEY.match(line):
            inside = line.split(":", 1)[0] == "conceptualTests"
        if inside:
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def snapshot_tests(workdir: Path) -> dict[str, str]:
    return {str(p.relative_to(workdir)): tests_section(p.read_text(encoding="utf-8")) for p in workdir.rglob("*.ctx")}


def prepare(task: dict, condition: str, workdir: Path) -> None:
    shutil.copytree(REPO / "examples" / task["project"], workdir,
                    ignore=shutil.ignore_patterns("__pycache__", "tests", "Dockerfile", "docker-compose.yml"))
    if condition == "none":
        for p in workdir.rglob("*.ctx"):
            p.unlink()
    if condition in ("none", "ctx", "ctx+hook"):
        (workdir / "CLAUDE.md").unlink(missing_ok=True)
    readme = workdir / "README.md"
    if readme.exists():
        readme.unlink()  # the example READMEs explain ContextDoc: they would leak the context in every condition
    if condition == "ctx+hook":
        (workdir / ".claude").mkdir()
        settings = {"hooks": {"PreToolUse": [{"matcher": "Read|Edit|Write", "hooks": [
            {"type": "command", "command": f"python3 {HOOK}", "timeout": 30}]}]}}
        (workdir / ".claude" / "settings.json").write_text(json.dumps(settings))
    env = {"GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@example.com",
           "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@example.com", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    for cmd in (["git", "init", "-q"], ["git", "add", "-A"], ["git", "commit", "-q", "-m", "start"]):
        subprocess.run(cmd, cwd=workdir, check=True, env=env)


def run_one(task_id: str, condition: str, rep: int, model: str, timeout: int) -> dict:
    task = TASKS[task_id]
    workdir = Path(tempfile.mkdtemp(prefix=f"ctxbench-{task_id}-{condition}-{rep}-".replace("+", "_")))
    shutil.rmtree(workdir)
    prepare(task, condition, workdir)
    before = snapshot_tests(workdir)
    started = time.time()
    cmd = ["claude", "-p", task["prompt"], "--model", model, "--output-format", "json",
           "--permission-mode", "acceptEdits", "--allowedTools", "Read,Edit,Write,Glob,Grep",
           "--setting-sources", "project,local", "--strict-mcp-config", "--no-session-persistence"]
    try:
        proc = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        out = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {}
        error = None if out else (proc.stderr or proc.stdout)[-300:]
    except subprocess.TimeoutExpired:
        out, error = {}, f"timeout after {timeout}s"
    after = snapshot_tests(workdir)
    changed = subprocess.run(["git", "status", "--porcelain"], cwd=workdir, capture_output=True, text=True).stdout.split("\n")
    result = {
        "task": task_id, "condition": condition, "rep": rep, "model": model,
        "violated": task["check"](workdir),
        "conceptual_tests_modified": sorted(k for k in before if after.get(k) != before[k]),
        "files_changed": sorted(l[3:] for l in changed if l.strip()),
        "seconds": round(time.time() - started, 1),
        "turns": out.get("num_turns"), "cost_usd": out.get("total_cost_usd"),
        "answer": (out.get("result") or "")[:600], "error": error,
    }
    shutil.rmtree(workdir, ignore_errors=True)
    return result


def summarize(results: list[dict]) -> str:
    lines = ["| Task | " + " | ".join(CONDITIONS) + " |", "|---|" + "---|" * len(CONDITIONS)]
    for task_id in TASKS:
        cells = []
        for cond in CONDITIONS:
            rs = [r for r in results if r["task"] == task_id and r["condition"] == cond and not r["error"]]
            cells.append(f"{sum(r['violated'] for r in rs)}/{len(rs)}" if rs else "–")
        lines.append(f"| {task_id} | " + " | ".join(cells) + " |")
    total = [f"{sum(r['violated'] for r in results if r['condition'] == c and not r['error'])}/"
             f"{sum(1 for r in results if r['condition'] == c and not r['error'])}" for c in CONDITIONS]
    lines.append("| **all** | " + " | ".join(f"**{t}**" for t in total) + " |")
    modified = [r for r in results if r["conceptual_tests_modified"]]
    errors = [r for r in results if r["error"]]
    lines.append("")
    lines.append(f"Cells: runs that violated the tension / valid runs. conceptualTests modified in {len(modified)} run(s); "
                 f"{len(errors)} run(s) failed to complete.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="haiku")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--tasks", nargs="*", default=list(TASKS))
    ap.add_argument("--conditions", nargs="*", default=CONDITIONS)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(t, c, r) for t in args.tasks for c in args.conditions for r in range(1, args.reps + 1)]
    results = []
    with cf.ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(run_one, t, c, r, args.model, args.timeout): (t, c, r) for t, c, r in jobs}
        for f in cf.as_completed(futures):
            r = f.result()
            results.append(r)
            print(f"{r['task']:16} {r['condition']:11} rep{r['rep']}  violated={r['violated']!s:5} "
                  f"tests_modified={len(r['conceptual_tests_modified'])} {r['seconds']}s {('ERROR ' + r['error'][:80]) if r['error'] else ''}", flush=True)
    results.sort(key=lambda r: (r["task"], CONDITIONS.index(r["condition"]), r["rep"]))
    (out / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    summary = summarize(results)
    (out / "summary.md").write_text(f"# Agents with and without ContextDoc — model {args.model}, {args.reps} run(s) each\n\n{summary}\n")
    print("\n" + summary)


if __name__ == "__main__":
    main()
