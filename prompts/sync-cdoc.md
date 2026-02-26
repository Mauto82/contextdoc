# Prompt: Sync .cdoc after code changes

Use this prompt after modifying a source file to check whether its `.cdoc` companion needs updating.

---

## Prompt

```
I've just modified `<FILE>`. Read both the updated file and its companion `<FILE>.cdoc`.

Check each section of the `.cdoc`:

- `tensions`: are any tensions now inaccurate, obsolete, or missing?
- `workflows`: do the described flows still match the implementation?
- `conceptualTests`: are any scenarios now impossible, incomplete, or missing given the changes?
- `todos`: have any todos been resolved by this change?

For each section, tell me:
1. What (if anything) needs to change in the `.cdoc`
2. The exact updated content to replace it with

Do not add content that wasn't already there unless a gap is critical.
Keep the same minimal style — no verbosity.
```

---

## Example usage

> "I've just modified `services/todo_service.py` to add priority support. Read the updated file and `services/todo_service.py.cdoc` and tell me what needs updating in the `.cdoc`."

---

## Notes

- Run this as a habit after any non-trivial change
- It's faster to sync incrementally than to rewrite a stale `.cdoc` from scratch
- If the diff is large and the `.cdoc` is mostly wrong, rewrite from scratch using the file as source
