# ContextDoc
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![CI](https://github.com/Mauto82/contextdoc/actions/workflows/ci.yml/badge.svg)](https://github.com/Mauto82/contextdoc/actions/workflows/ci.yml)

ContextDoc is a lightweight documentation standard for the AI-assisted development era. It provides structured context to AI coding agents — and human developers — through small YAML companion files that live alongside source code.

📄 **Paper:** [ContextDoc: Minimal Context and Verifiable Specifications for Development with AI Agents](https://mautoblog.com/en/docs/contextdoc-en/) ([Italiano](https://mautoblog.com/docs/contextdoc-it/)) — the format, the tools, a case study and the known limitations, in one place.

## The Problem

Source code tells you *what* the system does. It rarely tells you *why* specific constraints exist, *what* the intended behavior is across full workflows, or *what* the expected behavior is in edge cases. When an AI assistant (or a new developer) reads your code cold, this missing context leads to subtle mistakes: removing a constraint that looks redundant but isn't, or generating code that passes unit tests but violates business rules.

## The Approach

ContextDoc files (`.ctx`) capture only what the code cannot say about itself:

- **Tensions** — architectural decisions that look wrong but are intentional
- **Workflows** — key flows expressed as readable sequences
- **Conceptual tests** — declarative, language-agnostic test scenarios
- **TODOs** — pending work in the context of a specific file
- **Refs** — links to deeper documentation when needed

Everything else — signatures, dependencies, obvious behavior — stays in the code where it belongs.

## Example

```yaml
# user_service.py.ctx
purpose: "Manages user authentication and session lifecycle"

tensions:
  - "Tokens are stateless JWT — no revocation list, sessions cannot be forcibly terminated"
  - "bcrypt cost factor is 12 — intentionally slow, do not reduce for performance"
  - "Email is immutable after registration — downstream systems use it as a stable identifier"

workflows:
  registration: "validate input → hash password → persist (status: unverified) → send verification email"
  login: "validate credentials → check status is active → issue JWT"

conceptualTests:
  - name: "Registration and activation flow"
    steps:
      - action: "register with valid email and strong password"
        expect: "user created with status 'unverified'"
      - action: "verify email with valid token"
        expect: "user status becomes 'active'"
      - action: "login before email verification"
        expect: "error: account not active"
```

## Design Principles

**Non-binding.** ContextDoc files are documentation, not configuration. There is no runtime enforcement, no mandatory schema validation. Use the sections that add value, skip the ones that don't.

**Minimal.** The right amount of content is the minimum needed. A file with one `tensions` entry and three `conceptualTests` is better than a comprehensive file that nobody keeps up to date.

**Survive refactors.** Conceptual tests describe *intent*, not implementation. They don't break when you rename a method or switch a library.

**AI-first, human-readable.** The format is designed to be consumed by AI coding agents as context, but written and maintained by humans.

## Why "ContextDoc"?

The project started as **ConceptDoc** — a structured way to document *concepts* behind a codebase. Early iterations used verbose JSON schemas with sections for components, dependencies, metadata, and AI notes.

Over time it became clear that comprehensive documentation isn't what AI agents need. What they need is *context*: the small, high-signal pieces of information that the code itself cannot express — why a constraint exists, what an edge case means, what the intended behavior is.

The rename reflects this shift:

- From documenting *concepts* (formal, comprehensive) → to providing *context* (minimal, targeted)
- From `.cdoc` files → to `.ctx` files (shorter, editor-friendlier, accurately named)
- From JSON → to YAML (human-writable, no ceremony)
- From "describe everything" → to "document only what the code can't say"

**ContextDoc** is what the format actually is: lightweight context that makes AI-assisted development safer and more predictable.

The original 2025 ConceptDoc paper is still available as a snapshot of the starting point: [English](https://mautoblog.com/en/docs/conceptdoc-en/), [Italiano](https://mautoblog.com/docs/conceptdoc-it/).

## Does it work?

Measured on the repository's examples ([`bench/`](./bench/)): asked for changes that break a documented
decision, Claude Haiku broke it in **9 of 12** runs without ContextDoc, **0 of 12** with `.ctx` files and a
`CLAUDE.md` telling it to read them, and **2 of 12** with `.ctx` files and the Claude Code hook. With `.ctx`
files alone and no instruction it didn't read them (9 of 12). One model, three runs per case: a direction,
not a rate.

## Install the tools

```bash
pipx install contextdoc                 # ctx-run, ctx-watch, ctx-lint, ctx-mcp
pipx install "contextdoc[mcp]"          # with the MCP server's SDK
pipx install "git+https://github.com/Mauto82/contextdoc"   # latest from main
```

The examples below run the tools from a checkout (`python tools/<tool>/<tool>.py …`); once installed, the same commands are `ctx-run …`, `ctx-watch …`, `ctx-lint …`, `ctx-mcp`.

## Getting Started

1. Check out the [schema specification](./schema/README.md)
2. Look at the [examples](./examples/) directory
3. The repository includes `.vscode/settings.json` with the YAML schema pre-configured — syntax highlighting and autocomplete work in VS Code, Trae, Cursor, Windsurf, and other forks out of the box. Requires the [YAML extension by Red Hat](https://marketplace.visualstudio.com/items?itemName=redhat.vscode-yaml) (recommended automatically via `.vscode/extensions.json`).

   The key settings are `files.associations` (tells the editor `.ctx` is YAML, enabling syntax highlighting) and `yaml.schemas` (applies the ContextDoc schema for autocomplete). Both are needed:
   ```json
   {
     "files.associations": { "*.ctx": "yaml" },
     "yaml.schemas": {
       "https://raw.githubusercontent.com/Mauto82/contextdoc/main/schema/contextdoc.schema.json": "**/*.ctx"
     }
   }
   ```

   If you have a file ending in `.ctx` that is *not* a ContextDoc YAML companion (e.g. a dotenv config named `.env.ctx` used as `--env-file` in Docker), override the association for that specific file — more specific patterns take precedence over globs:
   ```json
   "files.associations": {
     "*.ctx": "yaml",
     ".env.ctx": "properties"
   }
   ```
   Also add it to `.ctxignore` to exclude it from ctx-watch checks:
   ```
   # .ctxignore
   .env.ctx
   ```

   For editors without `.vscode/` support, add this comment at the top of any `.ctx` file:
   ```yaml
   # yaml-language-server: $schema=https://raw.githubusercontent.com/Mauto82/contextdoc/main/schema/contextdoc.schema.json
   ```

## Using ContextDoc with AI agents

`.ctx` files provide per-file context. For the full picture, pair them with three additional elements:

**`project.ctx` at the project root** — project-level context in the same YAML format. Captures cross-cutting architectural decisions, project-scope workflows, and high-level conceptual tests. Unlike `CLAUDE.md`, it is tool-agnostic: any agent or developer reading the repo cold gets the same constraints regardless of IDE or model.

```yaml
# project.ctx
purpose: "FastAPI user management service"

tensions:
  - "Soft delete is a project-wide constraint — no hard deletes anywhere; all new resource types must follow the same pattern"
  - "Authentication is stateless JWT — no shared session store; horizontal scaling works without sticky sessions"

workflows:
  agent_reads: "read project.ctx (cross-cutting constraints) → read file.ctx for target file → respect tensions"
```

**`CLAUDE.md` (or `.cursorrules`) at the project root** — operational instructions that tell the agent *how to behave*: read the `.ctx` before modifying a file, never violate a tension without discussion, use `conceptualTests` as the spec when generating tests. Separate from context: `project.ctx` says what the system is; `CLAUDE.md` says how to work with it.

**Reusable prompts** for recurring operations — see the [`prompts/`](./prompts/) directory:

| Prompt | When to use |
|---|---|
| [`generate-tests`](./prompts/generate-tests.md) | Implement `conceptualTests` as real tests in your framework |
| [`review-tensions`](./prompts/review-tensions.md) | Verify code doesn't violate architectural constraints |
| [`sync-ctx`](./prompts/sync-ctx.md) | After a code change, check if the `.ctx` needs updating |
| [`intent-first`](./prompts/intent-first.md) | Implement code from a `.ctx` spec — enforces the "never modify the spec" contract |

See [`examples/project-0/CLAUDE.md`](./examples/project-0/CLAUDE.md) for a concrete example of the full setup.

**`ctx-lint`** — [`tools/ctx-lint`](./tools/ctx-lint/): warns about `.ctx` files that are too long, copy the code, use sections outside the schema, repeat `project.ctx`, over-specify input validation or have steps without an observable `expect`. Warnings only (`--strict` for CI); the VS Code extension shows the same warnings.

**Claude Code hook** — [`integrations/claude-code`](./integrations/claude-code/): a `PreToolUse` hook that adds `project.ctx` and the file's `.ctx` to Claude's context when it reads or edits a documented file, with no instruction needed, and asks *you* before an edit changes `conceptualTests`.

**MCP server** — [`tools/ctx-mcp`](./tools/ctx-mcp/): `get_context`, `list_tensions`, `list_scenarios` and `check_drift` for any MCP-capable agent (Claude Code, Claude Desktop, Cursor…).

**Git hook** to warn when source files are committed without updating their `.ctx` — see the [`hooks/`](./hooks/) directory:

```bash
# Install in your project
bash /path/to/concept-doc/hooks/install.sh
```

The hook warns but never blocks commits — consistent with ContextDoc's non-binding philosophy.

**`ctx-run`** — LLM-powered runner for `conceptualTests` (prompts and cache rules in [`spec/runner`](./spec/runner/), shared with the VS Code extension: the two use the same result cache). Reads `.ctx` files, sends source code + scenarios to an LLM, reports pass/fail per step. Supports Anthropic, OpenAI, and Ollama via [LiteLLM](https://github.com/BerriAI/litellm) — see the [`tools/ctx-run/`](./tools/ctx-run/) directory:

```bash
pip install -r tools/ctx-run/requirements.txt

# Run against a single file or a whole directory
python tools/ctx-run/ctx_run.py run examples/project-1/auth.py.ctx --model ollama/llama3
python tools/ctx-run/ctx_run.py run examples/ --model claude-haiku-5-5
```

For Python sources `ctx-run` can also **generate real pytest tests** from the `conceptualTests` and keep them in sync (`ctx-run generate`, `ctx-run verify`, `ctx-run generate --check` for CI): deterministic, free to re-run, and regenerated only when a scenario changes. See the [ctx-run README](./tools/ctx-run/README.md#executable-tests-generate-and-verify).

**`ctx-watch`** — file watcher that warns when source files change without their `.ctx` companion being updated. Catches drift earlier than the git hook — at save time, not commit time. See the [`tools/ctx-watch/`](./tools/ctx-watch/) directory:

```bash
pip install -r tools/ctx-watch/requirements.txt

# Watch a directory (blocking, Ctrl+C to stop)
python tools/ctx-watch/ctx_watch.py watch . --grace 300

# One-shot scan: every source that drifted from its .ctx
python tools/ctx-watch/ctx_watch.py status .

# CI: only the files changed in this branch (a missing .ctx is reported too)
python tools/ctx-watch/ctx_watch.py status . --base origin/main

# Intent-first mode: find .ctx specs without a corresponding source file
python tools/ctx-watch/ctx_watch.py status . --reverse
```

Two distinct signals: `⚠` means drift — source changed, `.ctx` not updated. `→` means spec without implementation — the intent-first case.

Inside a git repository, `status` measures drift from the **history**, so it gives the same answer locally, in CI and after a fresh clone: a source drifts when commits after the last commit that touched its `.ctx` changed it, or when it has uncommitted changes and its `.ctx` doesn't. Outside git (or with `--mtime`) it compares file modification times, limited to the last `--since` seconds. `watch` reports activity at save time and doesn't use git. The VS Code extension follows the same rules as `status`.

To exclude files or paths from all ctx-watch checks, add a `.ctxignore` file at the project root. Patterns use `fnmatch` glob syntax — patterns without `/` match on filename only, patterns with `/` match on the relative path from root:

```
# .ctxignore
__init__.py
src/generated/*.py
*.min.js
```

**Docker:** if the project is mounted as `./:/workspace`, the `.ctxignore` at the project root is automatically available at `/workspace/.ctxignore` — no extra configuration needed. ctx-watch reads it from the directory it scans:

```bash
# Inside the Docker container (e.g. via Makefile)
python /opt/contextdoc/tools/ctx-watch/ctx_watch.py status /workspace
# → reads /workspace/.ctxignore automatically
```

**Intent-first development** — a workflow pattern where the `.ctx` is written *before* the source file exists, mirroring TDD's red-green cycle. The `.ctx` is the red state: tensions define the constraints the implementation must respect, `conceptualTests` define the expected behavior, `workflows` define the intended flow. The AI starts from a complete spec rather than an empty file and a vague prompt.

**Critical rule:** in intent-first mode, the `.ctx` file is the spec — not a suggestion. The AI must adapt the code to satisfy the `conceptualTests`, never modify the tests to match its code. If a test seems wrong or impossible to satisfy, the AI must ask rather than rewrite the spec. This is the single most important contract in ContextDoc-driven development.

```bash
# Write notification_service.py.ctx first — source doesn't exist yet
python tools/ctx-watch/ctx_watch.py status . --reverse
# → notification_service.py.ctx: source not found  (exit 1 — usable in CI)
```

See `examples/project-3` for a complete intent-first example: a notification service fully specified in `.ctx` with the source intentionally absent.

## Real-world examples

- [notebook-lm-downloader](https://github.com/Mauto82/notebook-lm-downloader) — a Python CLI tool for downloading content from NotebookLM. Single-file project: one `.ctx` with tensions (including a third-party library monkey-patch), workflows, and conceptual tests.

## VS Code Extension

The **ContextDoc** extension brings conceptual tests and drift detection directly into VS Code — no Python installation required.

Install from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Mauto.contextdoc) or search "ContextDoc" in the Extensions panel.

**Features (0.2.0):**
- **Run conceptual tests** with a single click (CodeLens on `conceptualTests:`), cancellable, with a cost confirmation before a whole-workspace run
- **Setup wizard** — where the model runs (local gemma4:e2b from 16 GB of RAM, gemma4 on Ollama cloud below, any Ollama model with RAM warnings, or a paid API), ending with a test call
- **Result cache shared with `ctx-run`** — unchanged scenario, source and model: no new call, from the CLI or the editor
- **Drift detection**, built in, same rules as `ctx-watch status` (git history) — on save and when the workspace opens
- **Lint** of `.ctx` files in the Problems panel, same rules as `ctx-lint`
- **Native LLM runner** — no Python needed; Ollama through its native API with a context sized to the prompt
- **Sidebar panel** with test results, **status bar** with the model and the drift count

See [`vscode-extension/README.md`](./vscode-extension/README.md) for details.

## Current State

**ContextDoc 0.4** — `pipx install contextdoc` ([PyPI](https://pypi.org/project/contextdoc/)).

- Schema: v0.3.0 — YAML, all sections optional, IDE autocomplete via JSON Schema; `project.ctx` for project-level context
- Tools: `ctx-run` (LLM evaluation of `conceptualTests`, plus `generate` / `verify` for real pytest tests kept in sync), `ctx-watch` (drift from git history, intent-first `--reverse`), `ctx-lint`, `ctx-mcp`; the Claude Code hook; the VS Code extension 0.2.0
- Shared specs: `spec/runner` and `spec/lint`, used by the Python tools and the extension and checked by parity tests
- Examples: four reference projects (`project-0` CLI, `project-1` FastAPI async, `project-2` TDD demo with generated tests, `project-3` intent-first), each with a `project.ctx`
- Benchmarks: [`bench/`](./bench/) — agents with and without `.ctx`, and models for `ctx-run`
- Real-world: [notebook-lm-downloader](https://github.com/Mauto82/notebook-lm-downloader)

Contributions welcome — especially real-world examples, feedback on the schema, and more benchmark runs (other models, other tasks).

## Development

CI (`.github/workflows/ci.yml`) runs on every push and pull request:

- `pytest` for `tools/ctx-run`, `tools/ctx-watch`, `tools/ctx-mcp`, `tools/ctx-lint` and `integrations/claude-code` (Python 3.11 and 3.13), `ctx-lint --strict` on the repository's `.ctx` files, `ctx-run generate --check` on `examples/project-2`
- the Python package: wheel built, installed in a clean venv, commands run outside the checkout
- the VS Code extension: type-check, unit and parity tests, packaging, and a smoke test of the **packaged** `.vsix` in a real VS Code (`vscode-extension/test/smoke`)

Run the same locally:

```bash
for d in tools/ctx-run tools/ctx-watch tools/ctx-mcp tools/ctx-lint integrations/claude-code; do (cd $d && python -m pytest -q); done
cd vscode-extension && npm ci && npm run test:unit && npm run test:smoke
```

`CONTEXTDOC_TEST_MODEL=ollama/gemma4:e2b npm run test:smoke` also runs the conceptual tests through the model (not done in CI, to keep it free and deterministic). Releases: `vX.Y.Z` tags publish the Python package to PyPI (`.github/workflows/release.yml`).

## License

MIT
