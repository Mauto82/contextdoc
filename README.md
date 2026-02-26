# ContextDoc

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

## Using ContextDoc with AI agents

`.ctx` files provide per-file context. For the full picture, pair them with two additional elements:

**`CLAUDE.md` (or `.cursorrules`) at the project root** — operational instructions that tell the agent how to behave: read the `.ctx` before modifying a file, never violate a tension without discussion, use `conceptualTests` as the spec when generating tests.

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

## Real-world examples

- [notebook-lm-downloader](https://github.com/Mauto82/notebook-lm-downloader) — a Python CLI tool for downloading content from NotebookLM. Single-file project: one `.ctx` with tensions (including a third-party library monkey-patch), workflows, and conceptual tests.

## Current State

The project is in **active design phase**. The schema is at v0.2.0.

Contributions welcome — especially: real-world examples, feedback on the schema, and tooling ideas (linters, IDE plugins, git hooks to flag stale `.ctx` files).

## License

MIT
