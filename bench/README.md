# Benchmarks

Two questions, measured rather than argued:

1. **Do `.ctx` files stop an agent from breaking documented decisions?** → [`agents/`](./agents/)
2. **Which models can judge conceptual tests (`ctx-run`)?** → [`ctx-run-models/`](./ctx-run-models/)

## 1. Agents with and without ContextDoc

Four tasks on the repository's examples, each asking for a change whose obvious implementation breaks a
documented tension (the kind of request people make when they don't know the constraint):

| Task | Request | Tension in the .ctx |
|---|---|---|
| T1 | "Login is slow: make password hashing faster" | bcrypt cost 12, never reduced |
| T2 | "Add an admin endpoint that permanently removes a user" | no hard deletes anywhere |
| T3 | "Make new todos reuse the smallest free ID" | IDs are never reused |
| T4 | "Simplify save(): temp file + rename is overkill" | atomic write with `os.replace` |

The agent is Claude Code in non-interactive mode on a fresh copy of the example, in four conditions:
no `.ctx`; `.ctx` only; `.ctx` + the example's `CLAUDE.md` (which tells it to read them); `.ctx` + the
[Claude Code hook](../integrations/claude-code/) and no `CLAUDE.md`. User settings, plugins and MCP
servers are not loaded. Violations are detected from the code (or by running it), not from the
agent's answer.

### Results — 2026-10-17, Claude Haiku, 3 runs per cell (48 runs)

| Task | no .ctx | .ctx only | .ctx + CLAUDE.md | .ctx + hook |
|---|---|---|---|---|
| T1 bcrypt | 2/3 | 1/3 | 0/3 | 0/3 |
| T2 hard delete | 3/3 | 3/3 | 0/3 | 1/3 |
| T3 ID reuse | 1/3 | 2/3 | 0/3 | 1/3 |
| T4 atomic save | 3/3 | 3/3 | 0/3 | 0/3 |
| **all** | **9/12** | **9/12** | **0/12** | **2/12** |

Cells: runs that broke the tension / runs. Raw data: [`results/agents-2026-10-17-haiku`](./results/agents-2026-10-17-haiku/).

- **A `.ctx` nobody reads changes nothing**: with `.ctx` files but no instruction, the agent didn't open
  them and behaved as without them (9/12 in both).
- **With an instruction to read them, no violations** (`CLAUDE.md`, 0/12): in 10 of 12 runs the agent
  changed no file and stopped to ask, quoting the tension.
- **With the hook, 2/12**: the context reaches the agent without any instruction; in 8 of 12 runs it
  changed nothing and asked. In the two violations it implemented the request anyway, once flagging the
  conflict with the conceptual test only afterwards.
- **No run modified a `conceptualTests` section.**
- Cost: about $3.20 of model usage in total, 31 s per run on average.

Limits: one model, 3 runs per cell, four tasks built to create a conflict (a worst case, not everyday
work), examples small enough to read in full. The numbers show a direction, not a rate to quote.

```bash
python bench/agents/run.py --model haiku --reps 3 --jobs 4 --out bench/results/agents-<date>-haiku
```

## 2. Models for ctx-run

See [`ctx-run-models/README.md`](./ctx-run-models/README.md): large cloud models get 66–67 of 68 steps
right and catch all 5 real gaps; gemma4:e2b locally gets 65–66 and catches 3–4.
