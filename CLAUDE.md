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

## When modifying tools/ctx-run/

- `ctx_run.py` must have a corresponding `ctx_run.py.ctx` — keep it in sync
- The tool must remain provider-agnostic (no hardcoded Anthropic-only logic)
- Do not add a `--temperature` flag — determinism at 0 is intentional
- Keep the tool as a single file (`ctx_run.py`); split only if it exceeds ~500 lines

## What not to do

- Don't add verbose sections back (components, dependencies, metadata, testFixtures, aiNotes)
- Don't make sections mandatory
- Don't add runtime enforcement or tooling that couples `.ctx` to a specific language
