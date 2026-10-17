# Models for ctx-run

How well a model judges conceptual tests: `ctx-run` on `examples/project-0`, `-1` and `-2` (68 steps, 5 of
them real gaps, listed in `ground_truth.json`), scored step by step.

```bash
python bench/ctx-run-models/run.py --model ollama/gemma4:e2b --reps 3
```

## Results (2026-10-17, MacBook with 18 GB of RAM)

Measured with the VS Code extension's runner, which uses the same prompts as `ctx-run` (`spec/runner`).

| Model | Steps correct | Gaps caught (of 5) | False FAIL | Time per run | RAM while running |
|---|---|---|---|---|---|
| gpt-oss:120b (Ollama cloud) | 67/68 | 5 | 1 | 41 s | — |
| gpt-oss:120b, with `run.py` (ctx-run, Python) | 66/68 | 5 | 2 | 34 s | — |
| gemma4:31b (Ollama cloud) | 67/68 | 5 | 1 | 84 s | — |
| gemma4:e2b (local, 3 runs) | 65–66/68 | 3–4 | 0–2 | ~3 min | 8.7 GB |
| gemma4:e2b-mlx (local, 3 runs) | 65–66/68 | 3–4 | 0–2 | ~3 min | 8.7 GB |
| gemma4:12b-mlx (local) | 54/68 | 4 | 0 | 27 min | 7.7–16.2 GB* |

\* 16.2 GB through Ollama's OpenAI-compatible endpoint, which reserves the model's full context. With
Ollama's native API and a context sized to the prompt (what the extension does now) it loaded at 7.7–8.3 GB,
but showed 16.2 GB again at the end of one long run with timeouts (not reproduced; see issue #8). The 12b
answered 4 of 23 scenarios with an empty reply or a timeout.

Notes: e2b always missed the subtle gap (an unknown command should show the help, the code only prints a
message) and sometimes a second one; at temperature 0 it still changed its verdict on 3–4 steps between
runs. These results are why the extension suggests gemma4:e2b only from 16 GB of RAM and gemma4 on
Ollama cloud below.
