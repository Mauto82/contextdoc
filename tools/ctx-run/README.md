# ctx-run

LLM-powered runner for [ContextDoc](../../README.md) conceptual tests.

Reads `.ctx` files, sends source code + `conceptualTests` to an LLM, reports pass/fail per step.

## How it works

ContextDoc's `conceptualTests` are declarative, language-agnostic scenarios:

```yaml
conceptualTests:
  - name: "Password hashing"
    steps:
      - action: "call hash_password('secret123')"
        expect: "returns a string that is not 'secret123'"
      - action: "call verify_password('wrong', the hash)"
        expect: "returns False"
```

`ctx-run` sends the source file + each scenario to an LLM, which reasons about whether the code correctly implements the described behavior. The output is a pass/fail report per step.

This is **static analysis via LLM**, not code execution. Treat failures as signals to investigate, not verdicts.

## Prerequisites

- Python 3.11+
- An LLM provider (Anthropic, OpenAI, or Ollama running locally)

## Installation

```bash
pip install -r tools/ctx-run/requirements.txt
```

## Usage

```bash
# Run a single .ctx file
python tools/ctx-run/ctx_run.py run examples/project-1/auth.py.ctx

# Run all .ctx files in a directory
python tools/ctx-run/ctx_run.py run examples/project-1/

# Use a specific model
python tools/ctx-run/ctx_run.py run examples/ --model ollama/llama3

# JSON output (useful for CI)
python tools/ctx-run/ctx_run.py run examples/ --output json

# Verbose: show explanations for passing steps too
python tools/ctx-run/ctx_run.py run examples/ --verbose

# After a FAIL, ask the LLM to suggest a fix
python tools/ctx-run/ctx_run.py run examples/ --fix

# Set a longer timeout for slow local models
python tools/ctx-run/ctx_run.py run examples/ --model ollama/llama3 --timeout 120

# Skip cache and always re-run
python tools/ctx-run/ctx_run.py run examples/ --no-cache

# Clear the local result cache
python tools/ctx-run/ctx_run.py clear-cache
```

## Supported providers

| Provider | Model string example | API key env var |
|---|---|---|
| Anthropic | `claude-haiku-20240307` | `ANTHROPIC_API_KEY` |
| OpenAI | `gpt-4o-mini` | `OPENAI_API_KEY` |
| Ollama (local) | `ollama/llama3`, `ollama/codellama` | — |

The model defaults to `$CTX_MODEL` env var, or `claude-haiku-20240307` if not set.

```bash
# Set model via env var
export CTX_MODEL=ollama/llama3
python tools/ctx-run/ctx_run.py run examples/
```

For Ollama, make sure the Ollama server is running (`ollama serve`) and the model is pulled (`ollama pull llama3`).

## Options

```
--model TEXT          LiteLLM model string
--fail-fast           Stop after the first failing scenario
--no-color            Disable ANSI colors (auto-disabled when stdout is not a TTY)
--output [text|json]  Output format (default: text)
--verbose             Show LLM explanations for passing steps too
--timeout INT         LLM call timeout in seconds (default: 60)
--no-cache            Always call the LLM, even if a cached result exists
--fix                 After a failing scenario, ask the LLM to suggest a fix
```

Results are cached in `~/.cache/ctx-run/cache.json` by default. The cache key is a hash of the scenario definition, source code, and model — so the cache invalidates automatically when any of these change. Use `ctx-run clear-cache` to wipe it manually.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All scenarios passed (or only skipped files) |
| `1` | One or more scenarios failed |
| `2` | Tool-level error (bad path, no .ctx files found) |

## Example output

```
examples/project-1/auth.py.ctx
  scenario: Password hashing
    [PASS] call hash_password('secret123')
    [PASS] call verify_password('secret123', the hash)
    [PASS] call verify_password('wrong', the hash)

  scenario: Token lifecycle
    [PASS] create token with payload {sub: '42'}
    [PASS] decode the token immediately
    [FAIL] decode a token signed with a different key
           The except block catches JWTError but raises HTTP 401, not re-raises JWTError directly.
    [PASS] decode a token with exp in the past

──────────────────────────────────────────────────
  1 file   2 scenarios   7/8 steps passed
  1 scenario FAILED
```

## Limitations

- LLM reasoning is not code execution. False positives (PASS when the code is wrong) and false negatives (FAIL when the code is correct) are possible.
- Conceptual tests are intentionally high-level. The LLM may interpret an ambiguous step differently than the author intended.
- Complex multi-file interactions are harder to analyze than single-file behavior.

Use `ctx-run` as a first-pass sanity check, not as a replacement for a real test suite. The `generate-tests` prompt in `prompts/` generates actual pytest tests from the same `conceptualTests`.
