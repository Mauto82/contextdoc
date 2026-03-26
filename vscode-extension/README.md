# ContextDoc for VS Code

Run conceptual tests and detect `.ctx` drift directly in VS Code — no Python installation required.

## Quick Start

1. Install the extension from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Mauto.contextdoc)
2. Open a project that contains `.ctx` files
3. The setup wizard will prompt you to choose an LLM provider and model
4. Click **▶ Run Tests** above any `conceptualTests:` section

## Features

### Setup Wizard

On first launch, a guided setup walks you through:

1. **Choose provider** — OpenAI, Anthropic, Ollama (local), or OpenRouter
2. **Choose model** — pick from presets or enter a custom model ID
3. **API key** — stored securely in VS Code's SecretStorage (or use environment variables)

Re-run anytime via the command palette: `ContextDoc: Setup LLM Provider`

### Run Conceptual Tests

- **CodeLens**: a "Run Tests" button appears above `conceptualTests:` in any `.ctx` file
- **Command palette**: `ContextDoc: Run Tests` (all files) or `ContextDoc: Run Tests on This File`
- Results appear in the sidebar panel and as notifications

### Drift Detection

- **On save**: automatically checks if source files have changed without their `.ctx` being updated
- **Manual**: `ContextDoc: Check Drift` from the command palette
- Drifted files appear as warnings in the Problems panel
- Status bar shows the current drift count

### Native LLM Runner

The extension includes a built-in LLM runner — it calls provider APIs directly via HTTP. No need to install Python or `ctx-run`.

If you already have `ctx-run` installed, the extension falls back to the CLI when no model is configured in settings.

## Supported Providers

| Provider | Models | API Key |
|----------|--------|---------|
| **OpenAI** | gpt-4o-mini, gpt-4o, o3-mini, ... | `OPENAI_API_KEY` or setup wizard |
| **Anthropic** | claude-haiku, claude-sonnet, claude-opus, ... | `ANTHROPIC_API_KEY` or setup wizard |
| **Ollama** | llama3, mistral, codellama, ... | Not required (local) |
| **OpenRouter** | Any model via OpenRouter | `OPENROUTER_API_KEY` or setup wizard |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `contextdoc.model` | `""` | LLM model (e.g. `gpt-4o-mini`, `ollama/llama3`) |
| `contextdoc.watchEnabled` | `true` | Enable drift detection on save |
| `contextdoc.ctxRunPath` | `ctx-run` | Path to external ctx-run CLI (fallback) |
| `contextdoc.ctxWatchPath` | `ctx-watch` | Path to external ctx-watch CLI |

## Commands

| Command | Description |
|---------|-------------|
| `ContextDoc: Run Tests` | Run all conceptual tests in the workspace |
| `ContextDoc: Run Tests on This File` | Run tests for the current `.ctx` file |
| `ContextDoc: Check Drift` | Scan for drifted `.ctx` files |
| `ContextDoc: Setup LLM Provider` | Run the setup wizard |

## What is ContextDoc?

ContextDoc is a documentation standard for AI-assisted development. `.ctx` files are small YAML companions that capture what code can't say about itself: architectural tensions, workflows, and conceptual tests.

Learn more at [github.com/Mauto82/contextdoc](https://github.com/Mauto82/contextdoc).

## License

MIT
