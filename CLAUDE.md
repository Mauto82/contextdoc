# Working on ContextDoc

## What this project is

ContextDoc is a documentation standard. The main deliverables are:
- `schema/README.md` — the schema spec (current version: 0.3.0)
- `README.md` — the project overview and philosophy
- `examples/` — reference implementations showing the standard in practice
- `tools/ctx-run/` — LLM-powered runner for `conceptualTests` (multi-provider via LiteLLM)

## Schema principles (don't drift from these)

- Format is YAML, not JSON
- All sections are optional
- A `.ctx` file should never exceed ~60 lines — if it does, it's probably over-documented
- Document only what would surprise an AI or new developer reading the code cold
- `tensions` is the most important section
- `conceptualTests` is the most unique section — it's what differentiates ContextDoc from existing tools

## When modifying the schema

- Update `schema/README.md`
- Bump the version (semver)
- Update the example in the root `README.md`
- Update the examples in `examples/` to reflect the new format

## When adding examples

- Each example lives in `examples/project-N/`
- Every `.py` file must have a corresponding `.ctx`
- Include a `CLAUDE.md` in the example project — it demonstrates how ContextDoc and operational instructions work together
- Include a `README.md` explaining the example

## Packaging

- One Python package, `contextdoc` (root `pyproject.toml`, hatchling). The tools stay in `tools/<name>/`; the wheel maps each module to the top level and the shared specs to `contextdoc_spec/`
- A new tool module or spec file must be added to `[tool.hatch.build.targets.wheel.force-include]`, or the installed commands won't find it (CI builds the wheel and runs the commands from a clean venv)
- Releases: bump `version` in `pyproject.toml`, push a `vX.Y.Z` tag; `.github/workflows/release.yml` publishes to PyPI (trusted publishing)

## Benchmarks

- `bench/agents`: Claude Code on tasks that conflict with tensions, with and without `.ctx` (costs model usage: run it on purpose, not in CI)
- `bench/ctx-run-models`: how well a model judges conceptual tests; `ground_truth.json` must change if the examples change

## Before committing

- Python tools: `python -m pytest -q` in `tools/ctx-run`, `tools/ctx-watch`, `tools/ctx-mcp`, `tools/ctx-lint` and `integrations/claude-code`; `.ctx` files must pass `ctx_lint.py --strict`
- VS Code extension: `npm run test:smoke` in `vscode-extension` — it tests the packaged `.vsix`, not the sources (0.1.0 shipped without its `yaml` dependency and never activated)
- CI runs both on every push and pull request

## When modifying the runner (ctx-run or the extension's runner)

- Prompts, language map, LLM settings, result texts and cache rules live in `spec/runner/runner-spec.json`, shared by both runners — never copy them into code
- After a change: `python spec/runner/fixtures/generate.py`, then both parity suites (`pytest` in `tools/ctx-run`, `npm run test:unit` in `vscode-extension`)

## When modifying tools/ctx-run/

- `ctx_run.py` must have a corresponding `ctx_run.py.ctx` — keep it in sync
- The tool must remain provider-agnostic (no hardcoded Anthropic-only logic)
- Do not add a `--temperature` flag — determinism at 0 is intentional
- `ctx_run.py` is past ~500 lines: new features go in their own module (`ctx_generate.py` for generate / verify), each with its `.ctx`

## What not to do

- Don't add verbose sections back (components, dependencies, metadata, testFixtures, aiNotes)
- Don't make sections mandatory
- Don't add runtime enforcement or tooling that couples `.ctx` to a specific language
