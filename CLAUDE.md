# Working on ConceptDoc

## What this project is

ConceptDoc is a documentation standard. The main deliverables are:
- `schema/README.md` — the schema spec (current version: 0.2.0)
- `README.md` — the project overview and philosophy
- `examples/` — reference implementations showing the standard in practice

## Schema principles (don't drift from these)

- Format is YAML, not JSON
- All sections are optional
- A `.cdoc` file should never exceed ~60 lines — if it does, it's probably over-documented
- Document only what would surprise an AI or new developer reading the code cold
- `tensions` is the most important section
- `conceptualTests` is the most unique section — it's what differentiates ConceptDoc from existing tools

## When modifying the schema

- Update `schema/README.md`
- Bump the version (semver)
- Update the example in the root `README.md`
- Update the examples in `examples/` to reflect the new format

## When adding examples

- Each example lives in `examples/project-N/`
- Every `.py` file must have a corresponding `.cdoc`
- Include a `CLAUDE.md` in the example project — it demonstrates how ConceptDoc and operational instructions work together
- Include a `README.md` explaining the example

## What not to do

- Don't add verbose sections back (components, dependencies, metadata, testFixtures, aiNotes)
- Don't make sections mandatory
- Don't add runtime enforcement or tooling that couples `.cdoc` to a specific language
