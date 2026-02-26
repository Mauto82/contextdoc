# ContextDoc Schema Specification

ContextDoc files (`.ctx`) are lightweight YAML companions to source files. They capture what the code *cannot* say about itself: architectural tensions, intended workflows, and declarative tests.

**Philosophy:** write only what would genuinely surprise or mislead an AI (or a new developer) reading the code cold. Less is more.

## Format

YAML. Files live alongside the source: `service.py` → `service.py.ctx`.

## Sections

All sections are optional. Use only what adds value.

---

### `purpose`

One line. What this file *does*, not how.

```yaml
purpose: "CLI entry point for the todo management system"
```

---

### `tensions`

The most important section. Document architectural decisions that look wrong but are intentional, or constraints that must not be broken without careful reconsideration. Think of these as inline ADRs.

```yaml
tensions:
  - "StorageService is injected, not a singleton — keeps the app testable, don't make it global"
  - "Command parsing is intentionally naive — see @ref: docs/adr/001-cli-design.md before replacing"
  - "IDs are never reused after deletion — billing audit trail depends on this"
```

---

### `todos`

Pending work that lives in the context of this specific file, not in a task tracker.

```yaml
todos:
  - "Add priority support to TodoItem"
  - "Consider argparse if commands grow beyond current set"
```

---

### `workflows`

Key flows expressed as readable sequences. Not exhaustive — only flows that are non-obvious or span multiple components.

```yaml
workflows:
  add_todo: "input title → validate → TodoService.create → StorageService.save → display"
  complete_todo: "parse id → TodoService.complete → StorageService.save"
  error_path: "any ValueError from service → print message → return to main loop (never crash)"
```

---

### `conceptualTests`

Declarative, language-agnostic test scenarios. These describe *what the system should do*, not *how to test it*. They survive refactors and work across implementations.

```yaml
conceptualTests:
  - name: "Basic todo lifecycle"
    steps:
      - action: "add todo with valid title"
        expect: "todo created with status 'active', assigned an ID"
      - action: "complete <id>"
        expect: "todo status becomes 'completed'"
      - action: "delete <id>"
        expect: "todo no longer appears in any listing"

  - name: "Input validation"
    steps:
      - action: "add todo with empty title"
        expect: "error message shown, no todo created"
      - action: "complete with non-integer id"
        expect: "error message 'Invalid ID format', no state change"
      - action: "complete with valid integer but non-existent id"
        expect: "error message 'No todo found with ID X', no state change"
```

---

### `ref`

Links to external documents for context too large to inline.

```yaml
ref:
  - "docs/adr/001-cli-design.md"
  - "docs/state-model.md"
```

---

## Full example

```yaml
purpose: "Manages user authentication and session lifecycle"

tensions:
  - "Tokens are stateless JWT — no revocation list, sessions cannot be forcibly terminated"
  - "bcrypt cost factor is 12 — intentionally slow, do not reduce for performance"
  - "Email is immutable after registration — downstream systems use it as a stable identifier"

todos:
  - "Add refresh token rotation"

workflows:
  registration: "validate input → hash password → persist user (status: unverified) → send verification email"
  login: "validate credentials → check status (must be active) → issue JWT"
  verification: "validate token → check expiry → set status to active → invalidate token"

conceptualTests:
  - name: "Registration and activation flow"
    steps:
      - action: "register with valid email and strong password"
        expect: "user created with status 'unverified'"
      - action: "verify email with valid token"
        expect: "user status becomes 'active'"
      - action: "login with correct credentials"
        expect: "JWT returned"
      - action: "login before email verification"
        expect: "error: account not active"

  - name: "Password security"
    steps:
      - action: "register with password shorter than 8 chars"
        expect: "WeakPasswordError, no user created"
      - action: "register with valid password, inspect stored value"
        expect: "stored value is a bcrypt hash, never plaintext"

ref:
  - "docs/adr/002-auth-strategy.md"
```

---

## What NOT to put in a `.ctx`

- Method signatures and parameters (readable from the code)
- Dependency lists (visible from imports)
- Version and author metadata (that's what git is for)
- Obvious pre/postconditions that any developer would assume
- Anything you'd have to update every time the implementation changes

---

## Operational layer

The schema defines the format of `.ctx` files. To use them effectively with AI agents, pair them with:

- A `CLAUDE.md` at the project root with operational instructions (when to read `.ctx`, how to handle tensions, how to generate tests)
- Reusable prompts for common operations: generating tests from `conceptualTests`, reviewing tensions, syncing `.ctx` after code changes
- A git pre-commit hook that warns when source files are modified without updating their `.ctx` companion

See the [`prompts/`](../prompts/) directory, [`hooks/`](../hooks/) directory, and [`examples/project-0/CLAUDE.md`](../examples/project-0/CLAUDE.md) for reference.

---

## Versioning

ContextDoc schema version: **0.2.0**
