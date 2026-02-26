# Prompt: Generate tests from .ctx

Use this prompt to generate concrete tests from the `conceptualTests` section of a `.ctx` file.

---

## Prompt

```
Read `<FILE>.ctx` and implement every scenario in `conceptualTests` as tests in `tests/test_<FILE>.<EXT>`.

Rules:
- One test function per scenario step, or one test class per scenario
- Test names must reflect the scenario and step (e.g. `test_add_todo_with_empty_title_raises_error`)
- Do not test implementation details — test the behavior described in `expect`
- If a scenario requires setup from a previous step, use fixtures or setUp
- Cover all edge cases mentioned in `expect` fields
- Do not add tests that are not in `conceptualTests` unless a gap is obvious and critical

Framework: [pytest / jest / unittest / ...]
```

---

## Example usage

> "Read `services/todo_service.py.ctx` and implement every scenario in `conceptualTests` as pytest tests in `tests/test_todo_service.py`."

---

## Notes

- Run the generated tests immediately after generation to verify they pass
- If a test fails, check whether the bug is in the code or the test before fixing either
- Scenarios in `conceptualTests` describe *intended behavior* — a failing test may reveal a real bug
