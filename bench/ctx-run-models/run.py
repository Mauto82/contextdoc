#!/usr/bin/env python3
"""How good is a model at judging conceptual tests? ctx-run on examples/project-0, -1 and -2 (68 steps,
5 of them real gaps, see ground_truth.json), scored step by step.

    python bench/ctx-run-models/run.py --model ollama/gemma4:e2b --reps 3

Reports correct steps, gaps caught, false FAILs, scenarios without an answer, consistency across runs
and time. No cache: every run calls the model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "tools" / "ctx-run"))
import ctx_run  # noqa: E402

EXAMPLES = REPO / "examples"


def one_run(model: str, timeout: int) -> dict:
    steps, errors = {}, 0
    for project in ("project-0", "project-1", "project-2"):
        for ctx_path in ctx_run.collect_ctx_files(str(EXAMPLES / project)):
            result = ctx_run.run_ctx_file(ctx_path, model, fail_fast=False, timeout=timeout, use_cache=False)
            rel = os.path.relpath(ctx_path, EXAMPLES)
            for sc in result.scenarios:
                errors += sc.error is not None
                for i, st in enumerate(sc.steps, 1):
                    steps[f"{rel} | {sc.name} | {i}"] = st.passed
    return {"steps": steps, "errors": errors}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()
    truth = json.loads((HERE / "ground_truth.json").read_text())
    fails = set(truth["fail"])
    runs = []
    for _ in range(args.reps):
        t = time.time()
        r = one_run(args.model, args.timeout)
        r["seconds"] = round(time.time() - t)
        runs.append(r)
    keys = [k for k in runs[0]["steps"]] if runs else []
    for i, r in enumerate(runs, 1):
        s = r["steps"]
        correct = sum((s.get(k) is False) == (k in fails) for k in s if k in s)
        caught = sum(1 for k in fails if s.get(k) is False)
        false_fail = sum(1 for k, v in s.items() if v is False and k not in fails)
        missing = truth["total_steps"] - len(s)
        print(f"{args.model} run {i}: {correct}/{truth['total_steps']} correct, gaps caught {caught}/{len(fails)}, "
              f"false FAIL {false_fail}, steps without answer {missing}, scenario errors {r['errors']}, {r['seconds']}s")
    if len(runs) > 1:
        same = sum(len({r['steps'].get(k) for r in runs}) == 1 for k in keys)
        print(f"consistency across runs: {same}/{len(keys)} steps with the same verdict")


if __name__ == "__main__":
    main()
