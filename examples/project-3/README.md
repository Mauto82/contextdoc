# Project 3: Intent-First Development

This example demonstrates **intent-first development** with ContextDoc: write the `.ctx` spec before the source file exists, then let the spec drive the implementation.

## The pattern

Traditional TDD: write a failing test → implement → test passes.
Intent-first: write a `.ctx` spec → implement → `ctx-watch --reverse` goes green, `ctx-run` goes green.

The `.ctx` file is the red state. The implementation is the green state.

## What's in this directory

```
project-3/
├── project.ctx                    ← project-level context and workflow
├── notification_service.py.ctx    ← full spec for the notification service
└── notification_service.py        ← intentionally missing
```

`notification_service.py` does not exist. `ctx-watch status --reverse` detects this:

```bash
$ python tools/ctx-watch/ctx_watch.py status examples/project-3 --reverse
1 spec(s) without implementation:
  →  notification_service.py  (source file does not exist)
```

## The exercise

Read `notification_service.py.ctx`, implement the service, verify with ctx-watch and ctx-run.

See `CLAUDE.md` for constraints and the exact verification commands.

## Why this matters

- An AI agent reading this directory gets a precise, unambiguous spec before touching any code
- The spec survives refactors — it describes intent, not implementation
- `ctx-watch --reverse` closes the loop: the toolchain tells you when the spec is satisfied
- Compare with `project-2`: there, code exists and tests partially fail. Here, code doesn't exist yet — a different phase of the same workflow
