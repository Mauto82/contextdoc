# ContextDoc for VS Code

Run conceptual tests and detect `.ctx` drift directly in VS Code — no Python installation required.

## Quick Start

1. Install the extension from the [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=Mauto.contextdoc)
2. Open a project that contains `.ctx` files
3. The setup wizard will prompt you to choose an LLM provider and model
4. Click **▶ Run Tests** above any `conceptualTests:` section

## Features

### Setup Wizard

On first launch, a guided setup asks **where the model should run**. No model is set until you pick one (drift detection works without a model). Two suggestions come first, ordered by your machine's RAM:

| Choice | Model | Runs | Cost |
|---|---|---|---|
| **gemma4:e2b on this machine** — suggested with 16 GB of RAM or more | `ollama/gemma4:e2b` | locally: 7.5 GB download, about 9 GB of RAM while tests run | free, offline, private, no account; a bit less accurate than large models |
| **gemma4 on Ollama cloud** — suggested below 16 GB of RAM | `ollama/gemma4:cloud` | on Ollama's servers, nothing to download | free tier with usage limits; needs an Ollama account (`ollama signin`) |
| Another Ollama model | any installed model | locally or on Ollama cloud | listed with its size and estimated RAM; models over half your RAM are flagged and need confirmation |
| A paid API | Anthropic, OpenAI, OpenRouter | provider's servers | billed per call; cheapest models suggested first |

On the repository's examples (68 steps, 5 real bugs), gemma4:e2b got 65–66 steps right and caught 3–4 bugs, against 67 and 5 for large cloud models; a run took about 3 minutes.

If a suggested model isn't installed in Ollama, the wizard offers to pull it (with progress, cancellable). API keys go to VS Code's SecretStorage, or are read from the environment. The wizard ends with a tiny test call, so a wrong key or model shows up immediately instead of at the first test.

The model in use is always shown in the status bar: click it to change. Re-run anytime via `ContextDoc: Setup LLM Provider`.

### Cost control

- **Cache**: a scenario's result is reused while the scenario, the source file and the model are unchanged. Clear it with `ContextDoc: Clear Test Results Cache`.
- **Confirmation**: before running the whole workspace (or with a model heavy for this machine) the extension shows how many LLM calls the run will make, how many results are cached, and where the model runs. Turn it off with `contextdoc.confirmRuns`.
- **Cancel**: every run can be stopped from its notification; the request in flight is aborted too, so a local model stops working immediately.

### Local models and RAM

Ollama models are called through Ollama's native API with a context sized to the prompt (source file + scenario), not the model's maximum: gemma4:12b took 16 GB of RAM through the OpenAI-compatible endpoint and about 8 GB this way. After a run, if the loaded model still takes more than half of your RAM, the extension says so once and offers to change model.

### Run Conceptual Tests

- **CodeLens**: a "Run Tests" button appears above `conceptualTests:` in any `.ctx` file
- **Command palette**: `ContextDoc: Run Tests` (all files) or `ContextDoc: Run Tests on This File`
- Results appear in the sidebar panel and as notifications

### Drift Detection

Built in, same rules as `ctx-watch` (no Python, no CLI): a source file drifts when its `.ctx` companion is older than the source. `.ctxignore` patterns are honoured.

- **When the workspace opens**: a full scan
- **On save**: saving a source file or its `.ctx` re-checks that file only; the other warnings stay
- **Manual**: `ContextDoc: Check Drift` from the command palette
- Drifted files appear as warnings in the Problems panel
- Status bar shows the current drift count

Unlike `ctx-watch`, files without a `.ctx` are not reported: ContextDoc expects a `.ctx` only where it adds value.

### Native LLM Runner

The extension includes a built-in LLM runner — it calls provider APIs directly via HTTP. No need to install Python or `ctx-run`.

If you already have `ctx-run` installed, the extension falls back to the CLI when no model is configured in settings.

## Supported Providers

| Provider | Models | API Key |
|----------|--------|---------|
| **OpenAI** | gpt-4o-mini, gpt-4o, o3-mini, ... | `OPENAI_API_KEY` or setup wizard |
| **Anthropic** | claude-haiku-5-5, claude-sonnet-5-5, claude-opus-5-5, ... | `ANTHROPIC_API_KEY` or setup wizard |
| **Ollama** | gemma4:e2b, gemma4:cloud, any installed model (native API, context sized to the prompt) | Not required |
| **OpenRouter** | Any model via OpenRouter | `OPENROUTER_API_KEY` or setup wizard |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `contextdoc.model` | `""` | LLM model (e.g. `gpt-4o-mini`, `ollama/llama3`) |
| `contextdoc.watchEnabled` | `true` | Drift detection on save and when the workspace opens |
| `contextdoc.ctxRunPath` | `ctx-run` | Path to external ctx-run CLI, used only when no model is configured |
| `contextdoc.timeout` | `120` | Seconds to wait for each LLM answer |
| `contextdoc.confirmRuns` | `true` | Ask before running the whole workspace or with a heavy model |

## Commands

| Command | Description |
|---------|-------------|
| `ContextDoc: Run Tests` | Run all conceptual tests in the workspace |
| `ContextDoc: Run Tests on This File` | Run tests for the current `.ctx` file |
| `ContextDoc: Check Drift` | Scan for drifted `.ctx` files |
| `ContextDoc: Setup LLM Provider` | Run the setup wizard |
| `ContextDoc: Clear Test Results Cache` | Forget cached results, so the next run calls the model again |

## What is ContextDoc?

ContextDoc is a documentation standard for AI-assisted development. `.ctx` files are small YAML companions that capture what code can't say about itself: architectural tensions, workflows, and conceptual tests.

Learn more at [github.com/Mauto82/contextdoc](https://github.com/Mauto82/contextdoc).

## License

MIT
