# Project 3: Intent-First Development

This example demonstrates the intent-first workflow: the `.ctx` spec is written before the source file exists.

## Reading order

1. `project.ctx` — project-level context and workflow
2. `notification_service.py.ctx` — full spec: purpose, tensions, conceptual tests

`notification_service.py` does not exist yet. That is intentional.

## Your task

Implement `notification_service.py` so that all `conceptualTests` in `notification_service.py.ctx` pass.

**Constraints (from tensions — treat these as hard requirements):**
- Single `NotificationService` class, one `send()` interface for all channels
- Every send creates a trackable status record — no fire-and-forget
- Retry logic must use exponential backoff, not fixed intervals
- `max_retries` must be a parameter, not a hard-coded constant
- Adding a new channel must not require modifying existing channel logic

## Verification

```bash
# Before implementing: should report 1 unimplemented spec
python tools/ctx-watch/ctx_watch.py status . --reverse

# After implementing: should go green
python tools/ctx-watch/ctx_watch.py status . --reverse

# Run conceptual tests against your implementation
python tools/ctx-run/ctx_run.py run examples/project-3/notification_service.py.ctx --model <your-model>
```

## What success looks like

```
ctx-watch status . --reverse
✓  No unimplemented specs found.

ctx-run run notification_service.py.ctx
✓ Successful email send       3/3 steps passed
✓ Successful SMS send         2/2 steps passed
✓ Retry on transient failure  2/2 steps passed
✓ Unknown channel             1/1 steps passed
✓ Status isolation            1/1 steps passed
```
