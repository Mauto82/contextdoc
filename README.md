# ConceptDoc

ConceptDoc is a lightweight documentation standard for the AI-assisted development era. It provides structured context to AI coding agents — and human developers — through small YAML companion files that live alongside source code.

## The Problem

Source code tells you *what* the system does. It rarely tells you *why* specific constraints exist, *what* the intended behavior is across full workflows, or *what* the expected behavior is in edge cases. When an AI assistant (or a new developer) reads your code cold, this missing context leads to subtle mistakes: removing a constraint that looks redundant but isn't, or generating code that passes unit tests but violates business rules.

## The Approach

ConceptDoc files (`.cdoc`) capture only what the code cannot say about itself:

- **Tensions** — architectural decisions that look wrong but are intentional
- **Workflows** — key flows expressed as readable sequences
- **Conceptual tests** — declarative, language-agnostic test scenarios
- **TODOs** — pending work in the context of a specific file
- **Refs** — links to deeper documentation when needed

Everything else — signatures, dependencies, obvious behavior — stays in the code where it belongs.

## Example

```yaml
# user_service.py.cdoc
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

**Non-binding.** ConceptDoc files are documentation, not configuration. There is no runtime enforcement, no mandatory schema validation. Use the sections that add value, skip the ones that don't.

**Minimal.** The right amount of content is the minimum needed. A file with one `tensions` entry and three `conceptualTests` is better than a comprehensive file that nobody keeps up to date.

**Survive refactors.** Conceptual tests describe *intent*, not implementation. They don't break when you rename a method or switch a library.

**AI-first, human-readable.** The format is designed to be consumed by AI coding agents as context, but written and maintained by humans.

## Getting Started

1. Check out the [schema specification](./schema/README.md)
2. Look at the [examples](./examples/) directory

## Current State

The project is in **active design phase**. The schema is at v0.2.0.

Contributions welcome — especially: real-world examples, feedback on the schema, and tooling ideas (linters, IDE plugins, git hooks to flag stale `.cdoc` files).

## License

MIT
