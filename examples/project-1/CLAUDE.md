# Working on this project

## Before touching any file

Read the `.ctx` companion before modifying a source file.

```
main.py      → main.py.ctx
auth.py      → auth.py.ctx
models.py    → models.py.ctx
database.py  → database.py.ctx
```

## Tensions are hard constraints

If a tension says "don't do X", don't do X — even if it looks like an improvement. If you think a tension should change, discuss it before touching the code.

Key constraints to keep in mind:
- **Never hard-delete users** — `is_deleted=True` only
- **Never add password fields to output schemas** — `UserOut` and any future output schema must exclude credentials
- **Never change `is_active` default to True** — new users must go through an activation flow
- **Never reduce bcrypt rounds or replace with a faster hasher** — security tradeoff, not a performance optimization opportunity

## Conceptual tests are the spec

When generating tests, use the `conceptualTests` sections as the specification. Use pytest + httpx (async client).

To generate tests for a file:
> "Implement the conceptualTests from `<file>.ctx` as pytest tests. Use httpx.AsyncClient with the FastAPI app."

## After modifying code

If your change affects a tension, workflow, or makes a conceptual test outdated — update the `.ctx`.

## TODOs in `.ctx` files

Known future work. Do not implement unless explicitly asked.

## Stack

- Python 3.11+
- FastAPI + SQLAlchemy (async) + aiosqlite
- Auth: python-jose (JWT) + passlib (bcrypt)
- Tests: pytest + httpx
