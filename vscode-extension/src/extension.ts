import * as vscode from 'vscode';
import { runCtxTests, RunResult } from './runner';
import * as path from 'path';
import * as os from 'os';
import { runCtxTestsNative, planRun } from './ctxRunner';
import { resolveProvider, getApiKey, listOllamaModels, isHeavyForThisMachine, estimatedRamBytes, loadedOllamaModels, formatGB, formatRam } from './llm';
import { ResultCache } from './cache';
import { TestResultsProvider } from './testResultsView';
import { DriftEntry, driftOf, gitToplevel, loadIgnorePatterns, scanDrift, sourceFor } from './watcher';
import { updateDiagnostics } from './diagnostics';
import { StatusBarManager, ModelStatusBar } from './statusBar';
import { isConfigured, runSetupWizard } from './setupWizard';

let debounceTimer: ReturnType<typeof setTimeout> | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const outputChannel = vscode.window.createOutputChannel('ContextDoc');
  const diagnosticCollection = vscode.languages.createDiagnosticCollection('contextdoc');
  const statusBar = new StatusBarManager();
  const testResultsProvider = new TestResultsProvider();
  const modelBar = new ModelStatusBar();
  const cache = new ResultCache(path.join(context.globalStorageUri.fsPath, 'results-cache.json'));

  // drift per source file (absolute path): a save updates only the file it touches
  const drift = new Map<string, DriftEntry>();
  const showDrift = (root: string): void => {
    updateDiagnostics(diagnosticCollection, [...drift.values()], root);
    statusBar.setDriftCount(drift.size);
  };
  const rescan = async (root: string): Promise<DriftEntry[]> => {
    const entries = await scanDrift(root);
    drift.clear();
    for (const entry of entries) { drift.set(entry.filePath, entry); }
    showDrift(root);
    return entries;
  };

  vscode.window.registerTreeDataProvider('contextdoc.testResults', testResultsProvider);

  // --- First-run setup prompt ---

  if (!isConfigured() && !context.globalState.get<boolean>('contextdoc.skipSetupPrompt')) {
    vscode.window
      .showInformationMessage(
        'ContextDoc: choose a model to run conceptual tests (drift detection works without one).',
        'Set Up',
        'Later',
        "Don't Ask Again"
      )
      .then((choice) => {
        if (choice === 'Set Up') {
          runSetupWizard(context.secrets);
        } else if (choice === "Don't Ask Again") {
          context.globalState.update('contextdoc.skipSetupPrompt', true);
        }
      });
  }

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('contextdoc.model')) { modelBar.refresh(); }
    })
  );

  // --- Commands ---

  context.subscriptions.push(
    vscode.commands.registerCommand('contextdoc.setup', () => {
      runSetupWizard(context.secrets);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('contextdoc.runTests', async () => {
      const root = getWorkspaceRoot();
      if (!root) return;

      const ctxFiles = await vscode.workspace.findFiles('**/*.ctx', '**/node_modules/**');
      if (ctxFiles.length === 0) {
        vscode.window.showInformationMessage('No .ctx files found in workspace.');
        return;
      }

      await runAndShow(root, root, outputChannel, testResultsProvider, context, cache, true);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('contextdoc.clearCache', () => {
      const n = cache.size;
      cache.clear();
      vscode.window.showInformationMessage(`ContextDoc: cleared ${n} cached result(s).`);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('contextdoc.runTestsOnFile', async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;

      const filePath = editor.document.uri.fsPath;
      if (!filePath.endsWith('.ctx')) {
        vscode.window.showWarningMessage('Current file is not a .ctx file.');
        return;
      }

      const root = getWorkspaceRoot();
      if (!root) return;

      await runAndShow(filePath, root, outputChannel, testResultsProvider, context, cache, false);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('contextdoc.checkDrift', async () => {
      const root = getWorkspaceRoot();
      if (!root) return;

      const entries = await rescan(root);
      if (entries.length === 0) {
        vscode.window.showInformationMessage('ContextDoc: no drift detected.');
      } else {
        vscode.window.showWarningMessage(`ContextDoc: ${entries.length} file(s) changed after their .ctx.`);
      }
    })
  );

  // --- CodeLens ---

  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider(
      { pattern: '**/*.ctx' },
      new CtxCodeLensProvider()
    )
  );

  // --- On-save drift detection ---

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const config = vscode.workspace.getConfiguration('contextdoc');
      if (!config.get<boolean>('watchEnabled', true)) return;
      if (doc.uri.scheme !== 'file') return;

      const root = getWorkspaceRoot();
      if (!root) return;

      if (debounceTimer) clearTimeout(debounceTimer);

      // saving a source or its .ctx: recompute the drift of that source only
      const source = sourceFor(doc.uri.fsPath);
      debounceTimer = setTimeout(async () => {
        const entry = await driftOf(source, root, loadIgnorePatterns(root), await gitToplevel(root));
        if (entry) { drift.set(source, entry); } else { drift.delete(source); }
        showDrift(root);
      }, 1000);
    })
  );

  // initial scan, after activation so it doesn't delay the editor
  if (vscode.workspace.getConfiguration('contextdoc').get<boolean>('watchEnabled', true)) {
    const folders = vscode.workspace.workspaceFolders;
    if (folders && folders.length > 0) {
      const root = folders[0].uri.fsPath;
      setTimeout(() => rescan(root), 500);
    }
  }

  context.subscriptions.push(diagnosticCollection);
  context.subscriptions.push(statusBar);
  context.subscriptions.push(modelBar);
  context.subscriptions.push(outputChannel);
}

export function deactivate(): void {}

// --- Helpers ---

function getWorkspaceRoot(): string | undefined {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) {
    vscode.window.showErrorMessage('No workspace folder open.');
    return undefined;
  }
  return folders[0].uri.fsPath;
}

async function apiKeyFor(model: string, context: vscode.ExtensionContext): Promise<string> {
  const { provider } = resolveProvider(model);
  return (await context.secrets.get(`contextdoc.apiKey.${provider.id}`)) ?? getApiKey(provider.id);
}

/** Where the model runs and what a run costs, in words, for the confirmation. */
async function describeCost(model: string): Promise<{ text: string; warning: string | null }> {
  const { provider, modelName } = resolveProvider(model);
  if (provider.id !== 'ollama') {
    return { text: `billed by ${provider.name} to your API key`, warning: null };
  }
  const installed = (await listOllamaModels()) ?? [];
  const m = installed.find((x) => x.name === modelName || x.name === `${modelName}:latest`);
  if (m?.cloud || /[:-]cloud$/.test(modelName)) {
    return { text: "on Ollama cloud, counted against your account's usage limits", warning: null };
  }
  if (m && isHeavyForThisMachine(m, os.totalmem())) {
    return {
      text: 'on this machine, free',
      warning: `${modelName} takes about ${formatGB(estimatedRamBytes(m))} of RAM on a machine with ${formatRam(os.totalmem())}: it may slow everything down.`,
    };
  }
  return { text: 'on this machine, free', warning: null };
}

async function runAndShow(
  targetPath: string,
  workspaceRoot: string,
  outputChannel: vscode.OutputChannel,
  provider: TestResultsProvider,
  context: vscode.ExtensionContext,
  cache: ResultCache,
  wholeWorkspace: boolean,
): Promise<void> {
  const config = vscode.workspace.getConfiguration('contextdoc');
  const model = config.get<string>('model', '');

  try {
    // no model: the external ctx-run CLI, if installed (it has its own model and cache)
    if (!model) {
      outputChannel.appendLine('[cli] No model configured, using external ctx-run');
      const result = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'Running conceptual tests (ctx-run)…' },
        () => runCtxTests(targetPath, workspaceRoot, outputChannel)
      );
      showResult(result, provider);
      return;
    }

    const apiKey = await apiKeyFor(model, context);
    const { provider: llm } = resolveProvider(model);
    if (llm.id !== 'ollama' && !apiKey) {
      const choice = await vscode.window.showErrorMessage(
        `ContextDoc: no API key for ${llm.name}.`, 'Set Up'
      );
      if (choice === 'Set Up') { runSetupWizard(context.secrets); }
      return;
    }

    // how many calls this run makes, before making them
    const plan = planRun(targetPath, model, cache);
    if (plan.scenarios === 0) {
      vscode.window.showInformationMessage('ContextDoc: no conceptualTests to run.');
      return;
    }
    const cost = await describeCost(model);
    const mustConfirm = plan.llmCalls > 0 && config.get<boolean>('confirmRuns', true) && (wholeWorkspace || cost.warning !== null);
    if (mustConfirm) {
      const detail =
        `${plan.scenarios} scenario(s) in ${plan.files} file(s), ${plan.cached} already cached.\n` +
        `${plan.llmCalls} call(s) to ${model}, ${cost.text}.` +
        (cost.warning ? `\n\n${cost.warning}` : '');
      const go = await vscode.window.showWarningMessage(
        `Run ${plan.llmCalls} LLM call(s)?`, { modal: true, detail }, 'Run'
      );
      if (go !== 'Run') { return; }
    }

    const timeout = Math.max(10, config.get<number>('timeout', 120)) * 1000;
    outputChannel.appendLine(`[native] model=${model}, ${plan.llmCalls} call(s), ${plan.cached} cached`);

    const result = await vscode.window.withProgress(
      {
        location: vscode.ProgressLocation.Notification,
        title: `ContextDoc: ${model}`,
        cancellable: true,
      },
      async (progress, token) => {
        const abort = new AbortController();
        token.onCancellationRequested(() => abort.abort());
        let last = 0;
        return runCtxTestsNative(targetPath, {
          model, apiKey, timeout, cache, signal: abort.signal,
          onProgress: (done, total) => {
            progress.report({ message: `scenario ${done}/${total}`, increment: ((done - last) / total) * 100 });
            last = done;
          },
        });
      }
    );
    showResult(result, provider);
    if (llm.id === 'ollama') { await warnIfModelTooBig(model, context); }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    vscode.window.showErrorMessage(`ContextDoc: ${msg}`);
    outputChannel.appendLine(`Error: ${msg}`);
  }
}

/** After a run with a local model: what Ollama actually loaded, compared with this machine's RAM.
 *  Warns once per model when it takes more than half of it. */
async function warnIfModelTooBig(model: string, context: vscode.ExtensionContext): Promise<void> {
  const name = resolveProvider(model).modelName;
  const loaded = await loadedOllamaModels();
  const bytes = loaded.get(name) ?? loaded.get(`${name}:latest`);
  const ram = os.totalmem();
  const key = `contextdoc.warnedHeavy.${name}`;
  if (!bytes || bytes <= ram * 0.5 || context.globalState.get<boolean>(key)) { return; }
  await context.globalState.update(key, true);
  const choice = await vscode.window.showWarningMessage(
    `ContextDoc: ${name} is using ${formatGB(bytes)} of this machine's ${formatRam(ram)} of RAM. ` +
      'If your computer slows down, choose a lighter model or one on Ollama cloud.',
    'Change Model'
  );
  if (choice === 'Change Model') { vscode.commands.executeCommand('contextdoc.setup'); }
}

function showResult(result: RunResult, provider: TestResultsProvider): void {
  provider.update(result);
  const { steps_passed, steps_total, failed_scenarios } = result.summary;
  const cached = result.results.reduce((n, f) => n + f.scenarios.filter((s) => s.from_cache).length, 0);
  const cachedNote = cached ? ` (${cached} from cache)` : '';
  if (result.cancelled) {
    vscode.window.showWarningMessage(`ContextDoc: cancelled. ${steps_passed}/${steps_total} steps passed so far${cachedNote}.`);
  } else if (failed_scenarios === 0) {
    vscode.window.showInformationMessage(`ContextDoc: ${steps_passed}/${steps_total} steps passed${cachedNote}.`);
  } else {
    vscode.window.showWarningMessage(
      `ContextDoc: ${failed_scenarios} scenario(s) failed. ${steps_passed}/${steps_total} steps passed${cachedNote}.`
    );
  }
}

// --- CodeLens ---

class CtxCodeLensProvider implements vscode.CodeLensProvider {
  provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    const lenses: vscode.CodeLens[] = [];

    for (let i = 0; i < document.lineCount; i++) {
      const line = document.lineAt(i);
      if (line.text.match(/^conceptualTests\s*:/)) {
        const range = new vscode.Range(i, 0, i, line.text.length);
        lenses.push(
          new vscode.CodeLens(range, {
            title: '$(beaker) Run Tests',
            command: 'contextdoc.runTestsOnFile',
            arguments: []
          })
        );
        break;
      }
    }

    return lenses;
  }
}
