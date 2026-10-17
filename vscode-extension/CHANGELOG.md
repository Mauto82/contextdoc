# Changelog

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
