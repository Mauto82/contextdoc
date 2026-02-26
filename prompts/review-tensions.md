# Prompt: Review code against tensions

Use this prompt to verify that a file (or a proposed change) does not violate the architectural constraints defined in the `.cdoc`.

---

## Prompt

```
Read `<FILE>` and its companion `<FILE>.cdoc`.

For each item in `tensions`:
1. Check whether the current code respects the constraint
2. If a violation exists, describe it precisely (line number, what it does, what the tension requires)
3. If no violation exists, confirm it with a one-line note

Then check `workflows`: does the implementation match the described flow? Flag any divergence.

Do not suggest style improvements or refactors unrelated to tensions and workflows.
Output format: one section per tension, verdict (OK / VIOLATION), explanation if needed.
```

---

## Example usage

> "Read `services/storage_service.py` and `services/storage_service.py.cdoc`. For each tension, check whether the code respects the constraint."

---

## Notes

- Run this after significant refactors or when onboarding a new contributor
- A violation is not always a bug — it may mean the tension needs updating
- If a tension is consistently violated and the code works correctly, consider removing or rewriting the tension
