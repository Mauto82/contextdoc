# Working on this project

## Before touching any file

Read the `.ctx` companion before modifying a source file. It contains tensions (constraints that must not be broken), workflows (intended flows), and conceptual tests (the spec).

```
todo_app.py          → todo_app.py.ctx
models/todo_item.py  → models/todo_item.py.ctx
services/todo_service.py    → services/todo_service.py.ctx
services/storage_service.py → services/storage_service.py.ctx
```

## Tensions are hard constraints

If a tension says "don't do X", don't do X — even if it looks like an improvement. Tensions exist because someone already considered and rejected that path. If you think a tension should change, discuss it before touching the code.

## Workflows define the expected flow

When implementing or modifying a feature, follow the workflow defined in the `.ctx`. Deviations need explicit justification.

## Conceptual tests are the spec

When writing or generating tests, use the `conceptualTests` section of the relevant `.ctx` as the specification. Each scenario must be covered. The framework is pytest.

To generate tests for a file:
> "Implement the conceptualTests from `<file>.ctx` as pytest tests in `tests/test_<file>.py`"

## Never modify `.ctx` files without permission

Do not edit any `.ctx` file — especially `conceptualTests` — without explicit human approval. If your code doesn't satisfy a conceptual test, fix the code, not the test. If a test seems wrong or impossible to satisfy, ask before changing it.

## After modifying code

If your change affects a tension, workflow, or makes a conceptual test outdated — flag it and ask before updating the `.ctx`.

## TODOs in `.ctx` files

These are known future work items. Do not implement them unless explicitly asked.

## Stack

- Python 3.8+
- No external dependencies
- Storage: JSON file via StorageService (atomic writes)
- Tests: pytest
