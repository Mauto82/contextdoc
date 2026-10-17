# Runner spec

`runner-spec.json` is the single source of truth for the conceptual-test runner, shared by:

- `tools/ctx-run` (Python, the reference implementation)
- the VS Code extension (`vscode-extension`, TypeScript; `npm run compile` copies the spec into `out/`)

It holds the system and user prompts for evaluating a scenario, the `--fix` prompt, the language map
for code fences, the LLM settings (temperature, max tokens), the result texts and the cache rules.
Templates use `${name}` placeholders, replaced in a single pass (inserted values are never scanned
again), and their parts are joined with newlines.

## Cache

Both runners use the same cache: `$XDG_CACHE_HOME/ctx-run/cache.json` (or `~/.cache/ctx-run/cache.json`),
same entry format and same key, so a result computed by the CLI is reused by the extension and vice versa.
The key is the SHA-256 of the scenario as canonical JSON (Python's `json.dumps(sort_keys=True)`:
sorted keys, `", "` and `": "` separators, non-ASCII escaped as `\uXXXX`) + the source content + the model.

## Changing it

1. Edit `runner-spec.json` (or the runner code).
2. Regenerate the expected outputs with ctx-run: `python spec/runner/fixtures/generate.py`.
3. Run both parity suites, which compare their prompts, cache keys and parsed results with
   `fixtures/expected.json`:
   - `python -m pytest -q` in `tools/ctx-run` (`tests/test_runner_spec_parity.py`)
   - `npm run test:unit` in `vscode-extension` (`test/unit/parity.test.js`)

Add a case to `fixtures/cases.json` for any new behavior (encodings, malformed answers, missing source…).
