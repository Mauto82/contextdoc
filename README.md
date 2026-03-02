# ContextDoc
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

ContextDoc is a lightweight documentation standard for the AI-assisted development era. It provides structured context to AI coding agents — and human developers — through small YAML companion files that live alongside source code.

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

## Getting Started

1. Check out the [schema specification](./schema/README.md)
2. Look at the [examples](./examples/) directory
3. Enable IDE autocomplete by adding to VS Code `settings.json`:
   ```json
   "yaml.schemas": {
     "https://raw.githubusercontent.com/Mauto82/contextdoc/main/schema/contextdoc.schema.json": "**/*.ctx"
   }
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

See [`examples/project-0/CLAUDE.md`](./examples/project-0/CLAUDE.md) for a concrete example of the full setup.

**Git hook** to warn when source files are committed without updating their `.ctx` — see the [`hooks/`](./hooks/) directory:

```bash
# Install in your project
bash /path/to/concept-doc/hooks/install.sh
```

The hook warns but never blocks commits — consistent with ContextDoc's non-binding philosophy.

**`ctx-run`** — LLM-powered runner for `conceptualTests`. Reads `.ctx` files, sends source code + scenarios to an LLM, reports pass/fail per step. Supports Anthropic, OpenAI, and Ollama via [LiteLLM](https://github.com/BerriAI/litellm) — see the [`tools/ctx-run/`](./tools/ctx-run/) directory:

```bash
pip install -r tools/ctx-run/requirements.txt

# Run against a single file or a whole directory
python tools/ctx-run/ctx_run.py run examples/project-1/auth.py.ctx --model ollama/llama3
python tools/ctx-run/ctx_run.py run examples/ --model claude-haiku-20240307
```

**`ctx-watch`** — file watcher that warns when source files change without their `.ctx` companion being updated. Catches drift earlier than the git hook — at save time, not commit time. See the [`tools/ctx-watch/`](./tools/ctx-watch/) directory:

```bash
pip install -r tools/ctx-watch/requirements.txt

# Watch a directory (blocking, Ctrl+C to stop)
python tools/ctx-watch/ctx_watch.py watch . --grace 300

# One-shot scan of recently modified files without .ctx updates
python tools/ctx-watch/ctx_watch.py status . --since 3600

# Intent-first mode: find .ctx specs without a corresponding source file
python tools/ctx-watch/ctx_watch.py status . --reverse
```

## Real-world examples

- [notebook-lm-downloader](https://github.com/Mauto82/notebook-lm-downloader) — a Python CLI tool for downloading content from NotebookLM. Single-file project: one `.ctx` with tensions (including a third-party library monkey-patch), workflows, and conceptual tests.

## Current State

The project is at **v0.3.0**.

- Schema: v0.3.0 — YAML, all sections optional, IDE autocomplete via JSON Schema; `project.ctx` convention for project-level context
- Examples: four reference projects (`project-0` CLI, `project-1` FastAPI async, `project-2` TDD demo, `project-3` intent-first — spec before code), each with a `project.ctx`
- Tools: `ctx-run` — LLM-powered conceptual test runner (Anthropic / OpenAI / Ollama); `ctx-watch` — real-time drift detector with intent-first support (`--reverse`)
- Real-world: [notebook-lm-downloader](https://github.com/Mauto82/notebook-lm-downloader)

Contributions welcome — especially: real-world examples, feedback on the schema, and tooling ideas (linters, IDE plugins, CI integrations).

## License

MIT
