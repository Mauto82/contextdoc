# Prompt: Sync .ctx after code changes

Use this prompt after modifying a source file to check whether its `.ctx` companion needs updating.

---

## Prompt

```
I've just modified `<FILE>`. Read both the updated file and its companion `<FILE>.ctx`.

Check each section of the `.ctx`:

- `tensions`: are any tensions now inaccurate, obsolete, or missing?
- `workflows`: do the described flows still match the implementation?
- `conceptualTests`: **do NOT suggest changes to make tests match the code.** Only flag if a scenario has become genuinely impossible due to a requirement change (not an implementation choice). If a conceptual test no longer passes, the code is likely wrong — not the test.
- `todos`: have any todos been resolved by this change?

For each section, tell me:
1. What (if anything) needs to change in the `.ctx`
2. The exact updated content to replace it with

**Important:** `conceptualTests` are the specification. Never modify them to accommodate the implementation. If you believe a test is wrong, explain why and wait for confirmation — do not rewrite it.

Do not add content that wasn't already there unless a gap is critical.
Keep the same minimal style — no verbosity.
```

---

## Example usage

> "I've just modified `services/todo_service.py` to add priority support. Read the updated file and `services/todo_service.py.ctx` and tell me what needs updating in the `.ctx`."

---

## Notes

- Run this as a habit after any non-trivial change
- It's faster to sync incrementally than to rewrite a stale `.ctx` from scratch
- If the diff is large and the `.ctx` is mostly wrong, rewrite from scratch using the file as source
