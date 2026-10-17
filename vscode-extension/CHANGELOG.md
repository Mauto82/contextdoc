# Changelog

## Unreleased

- **Lint of .ctx files** in the Problems panel, same rules as `ctx-lint` (`spec/lint`): L001–L008.

- **Drift from git history** inside a repository, like `ctx-watch status`: a source drifts when commits after the last `.ctx` commit changed it, or when it has uncommitted changes and its `.ctx` doesn't. Modification times only outside git (they say nothing after a clone or checkout).
- **One runner spec with ctx-run** (`spec/runner`): same prompts, language map, LLM settings and result texts; parity tests in both suites.
- **Result cache shared with ctx-run** (`~/.cache/ctx-run/cache.json`, same format and key): a result computed by the CLI is reused by the extension and vice versa. The extension's own cache file is no longer used.

## 0.1.2

- **Setup wizard rewritten around where the model runs.** No model is set until you pick one. Two suggestions first, by RAM: `ollama/gemma4:e2b` locally from 16 GB (7.5 GB download, ~9 GB of RAM in use, free and offline, a bit less accurate), `ollama/gemma4:cloud` below (nothing to download, needs an Ollama account). Missing models can be pulled from the wizard, with progress and cancel. Other Ollama models are listed with size and estimated RAM; models over half your RAM are flagged and need confirmation. Paid APIs are a separate, clearly labelled choice, cheapest models first. The wizard ends with a test call.
- **Ollama through its native API, with a context sized to the prompt**: the OpenAI-compatible endpoint made Ollama reserve the model's full context (gemma4:12b: 16 GB of RAM, now about 8). After a run, a one-time warning if the loaded model still takes more than half of the RAM.
- **Result cache**, as in ctx-run: unchanged scenario + source + model = no new call. New command `ContextDoc: Clear Test Results Cache`.
- **Cost confirmation** before running the whole workspace or with a heavy local model: number of LLM calls, cached results, where the model runs (`contextdoc.confirmRuns` to turn it off).
- **Cancellable runs**: the request in flight is aborted, so a local model stops at once. Progress shows the scenario count.
- New `contextdoc.timeout` setting (default 120 s per answer).
- The model in use is shown in the status bar; click to change it.
- The setup prompt can be silenced with "Don't Ask Again".

## 0.1.1

- **Fix: the extension did not activate.** The `yaml` library was left out of the 0.1.0 package (`.vscodeignore` excluded `node_modules`), so activation failed with `Cannot find module 'yaml'` and no command was available.
- **Drift detection is now built in**: no Python and no `ctx-watch` CLI needed (0.1.0 called `ctx-watch` and, when it wasn't installed, silently reported no drift). Same rules as `ctx-watch`, `.ctxignore` included; full scan when the workspace opens; files without a `.ctx` are not reported.
- Saving a file updates the drift warning of that file only, instead of clearing the others.
- Errors while running tests are shown (they were swallowed); a clear message when no model is configured and `ctx-run` is not installed.
- `max_tokens` raised to 4096: reasoning models used up the 1500-token budget and returned empty answers.
- OpenRouter: `openrouter/auto` was sent as `auto`; router ids now keep their prefix.
- Setup wizard: current Anthropic model ids (the old `claude-haiku-20240307` was not a valid id); outdated OpenRouter presets removed.
- Removed the `contextdoc.ctxWatchPath` setting (no longer used).
- `vscode:prepublish` compiles before packaging.

## 0.1.0

- First release: Run Tests via CodeLens and command palette, drift detection, setup wizard, native LLM runner (OpenAI, Anthropic, Ollama, OpenRouter).
