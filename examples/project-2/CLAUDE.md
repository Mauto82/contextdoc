# Working on this project

## What this project demonstrates

This is a **TDD demo** — the `.ctx` files were written before the implementation was complete.
`coupon.py` is fully implemented. `store.py` is partially implemented.

Running `ctx-run` will show:
- `coupon.py.ctx` — all scenarios green ✓
- `store.py.ctx` — first scenario green, three scenarios red ✗ (TODOs not yet wired up)

This is the intended state. The failing conceptual tests are the spec for what to implement next.

## File map

```
coupon.py      → coupon.py.ctx   (complete — do not regress)
store.py       → store.py.ctx    (partial — see todos in store.py.ctx)
```

## Constraints

- **Never make checkout() stateful** — it must remain a pure computation, no side effects beyond incrementing used_count
- **One coupon per cart** — do not add multi-coupon stacking without updating the tension in store.py.ctx
- **validate() lives on Coupon, not Cart** — Cart calls it, but the guard logic stays in coupon.py

## Implementing the TODOs

The two missing pieces in `store.py`:

1. In `apply_coupon()`: call `coupon.validate(self.subtotal)` before assigning `self._coupon`
2. In `checkout()`: after computing the total, call `coupon.used_count += 1`

After implementing, run `ctx-run run store.py.ctx --model <your-model>` to verify all scenarios pass.

## Stack

- Python 3.11+ (stdlib only — no external dependencies)
