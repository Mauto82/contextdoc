# ctx-lint

Warns about `.ctx` files that drift from ContextDoc's principles. Warnings only: it never fails unless
you ask with `--strict` (for CI).

| Code | Warns about |
|---|---|
| L001 | a `.ctx` longer than ~60 lines: it is probably repeating the code |
| L002 | function or class signatures copied from the source |
| L003 | sections outside the schema (`purpose`, `tensions`, `workflows`, `conceptualTests`, `todos`, `ref`), with a hint for ConceptDoc-era ones (`dependencies`, `components`…) |
| L004 | tensions or workflows repeated from `project.ctx` |
| L005 | many steps expecting an error for a missing or invalid input (≥ 2 and ≥ 30% of the steps): it makes code defensive and verbose |
| L006 | steps without an `expect`, or with a vague one (`works`, `as expected`, `funziona`…) |
| L007 | invalid YAML |
| L008 | a `purpose` longer than one line |

```bash
pipx install contextdoc                             # the ctx-lint command
pip install -r tools/ctx-lint/requirements.txt      # or, from a checkout:
python tools/ctx-lint/ctx_lint.py src/              # text report
python tools/ctx-lint/ctx_lint.py src/ --strict     # exit 1 on warnings (CI)
python tools/ctx-lint/ctx_lint.py src/ --format json
```

The rules live in [`spec/lint/lint-spec.json`](../../spec/lint/lint-spec.json), shared with the VS Code
extension, which shows the same warnings in the Problems panel. Both are checked against
`spec/lint/fixtures` (regenerate with `python spec/lint/fixtures/generate.py`).
