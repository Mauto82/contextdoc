# Prompt: Intent-first implementation

Use this prompt when a `.ctx` spec exists but the source file does not yet (or is incomplete). The `.ctx` is the specification — your job is to implement code that satisfies it.

---

## Prompt

```
Read `<FILE>.ctx`. This is the specification — do not modify it.

Implement `<FILE>` so that:

1. Every `conceptualTest` scenario passes — each step's `expect` must hold
2. Every `tension` is respected — these are hard constraints, not suggestions
3. Every `workflow` is followed — the described flow is the intended design

If you cannot satisfy a conceptual test:
- Stop and explain why
- Do NOT modify the `.ctx` to make your code pass
- Ask how to proceed

The `.ctx` is the "red" in TDD. Your implementation is the "green". You do not get to redefine what green means.
```

---

## Example usage

> "Read `notification_service.py.ctx` and implement `notification_service.py` so that all conceptual tests pass. Do not modify the `.ctx` file."

---

## Notes

- This prompt enforces the core contract: specs are human-authored, implementations are agent-authored
- If the agent modifies the `.ctx` anyway, that is a violation — flag it and revert
- Pair with `ctx-run` after implementation to verify: `ctx-run run <file>.ctx --model <model>`
- For partial implementations (like `examples/project-2`), the same rule applies: fix the code, not the tests
