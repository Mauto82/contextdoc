# Project 2: Coupon Service — ContextDoc as a TDD Spec

A minimal coupon/discount system demonstrating how ContextDoc `.ctx` files work as a **TDD specification**: scenarios are written before the implementation is complete, and `ctx-run` reports what's done and what's left.

## The demo

`coupon.py` is fully implemented. `store.py` is partially implemented — the integration between `Cart` and `Coupon.validate()` has not been wired up yet.

Running `ctx-run` produces a mixed pass/fail report:

```
examples/project-2/coupon.py.ctx
  scenario: Percentage discount
    [PASS] call apply_discount(100.0) on a 20% coupon
    [PASS] call apply_discount(100.0) on a 100% coupon
    [PASS] call apply_discount(50.0) on a 200% coupon

  scenario: Fixed discount
    [PASS] call apply_discount(50.0) on a $15 fixed coupon
    [PASS] call apply_discount(10.0) on a $60 fixed coupon

  scenario: Validation guards
    [PASS] call validate() on a coupon with active=False
    [PASS] call validate() on a coupon with max_uses=2, used_count=2
    [PASS] call validate() on a coupon with min_order_amount=50.0, order_total=30.0
    [PASS] call validate() on a coupon with expires_at 1 hour in the past
    [PASS] call validate() on a coupon with max_uses=None and used_count=999

examples/project-2/store.py.ctx
  scenario: Basic cart and checkout
    [PASS] add two items: $30 + $20, check subtotal
    [PASS] apply a 10% coupon, call checkout()
    [PASS] call checkout() with no coupon attached

  scenario: Coupon validation enforced on apply
    [FAIL] try to apply the exhausted coupon to a new cart via apply_coupon()
           apply_coupon() does not call coupon.validate() — it attaches
           the coupon unconditionally regardless of exhaustion state.

  scenario: used_count incremented after checkout
    [FAIL] coupon.used_count is 1 after checkout
           checkout() calls apply_discount() but never increments used_count.

  scenario: Minimum order enforced on apply
    [FAIL] raises ValueError: order does not meet minimum
           apply_coupon() does not call coupon.validate(self.subtotal),
           so the min_order_amount guard is never reached.

──────────────────────────────────────────────────────
  2 files   7 scenarios   13/16 steps passed
  3 scenarios FAILED
```

## What to implement next

Two changes in `store.py` close all three failing scenarios:

1. **`apply_coupon()`** — add `coupon.validate(self.subtotal)` before attaching the coupon
2. **`checkout()`** — add `coupon.used_count += 1` after computing the discounted total

The `.ctx` files are the spec. The code is the work in progress.

## File structure

```
./
├── coupon.py        # Coupon model + discount math + validation guards (complete)
├── coupon.py.ctx
├── store.py         # Cart + checkout (partial — 2 TODOs remaining)
└── store.py.ctx
```

## Running ctx-run on this project

```bash
# From the repo root
python tools/ctx-run/ctx_run.py run examples/project-2/ --model ollama/llama3
```

Expected: 13/16 steps pass, 3 scenarios fail — until the TODOs in `store.py` are implemented.

## Contrast with the other examples

| Project | Focus | Expected result |
|---|---|---|
| project-0 | Sync CLI app, tensions documented | All PASS |
| project-1 | Async FastAPI, security tensions | All PASS |
| **project-2** | **Partial implementation as TDD spec** | **Mixed PASS/FAIL** |

The key insight: `ctx-run` failures are not test infrastructure problems — they are a precise, readable list of work remaining.
