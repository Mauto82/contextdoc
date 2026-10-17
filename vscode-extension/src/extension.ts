import * as vscode from 'vscode';
import { runCtxTests, RunResult } from './runner';
import { runCtxTestsNative } from './ctxRunner';
import { resolveProvider, getApiKey } from './llm';
import { TestResultsProvider } from './testResultsView';
import { DriftEntry, driftOf, loadIgnorePatterns, scanDrift, sourceFor } from './watcher';
import { updateDiagnostics } from './diagnostics';
import { StatusBarManager } from './statusBar';
import { isConfigured, runSetupWizard } from './setupWizard';

let debounceTimer: ReturnType<typeof setTimeout> | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const outputChannel = vscode.window.createOutputChannel('ContextDoc');
  const diagnosticCollection = vscode.languages.createDiagnosticCollection('contextdoc');
  const statusBar = new StatusBarManager();
  const testResultsProvider = new TestResultsProvider();

  // drift per source file (absolute path): a save updates only the file it touches
  const drift = new Map<string, DriftEntry>();
  const showDrift = (root: string): void => {
    updateDiagnostics(diagnosticCollection, [...drift.values()], root);
    statusBar.setDriftCount(drift.size);
  };
  const rescan = (root: string): DriftEntry[] => {
    drift.clear();
    for (const entry of scanDrift(root)) { drift.set(entry.filePath, entry); }
    showDrift(root);
    return [...drift.values()];
  };

  vscode.window.registerTreeDataProvider('contextdoc.testResults', testResultsProvider);

  // --- First-run setup prompt ---

  if (!isConfigured()) {
    vscode.window
      .showInformationMessage(
        'ContextDoc: no LLM model configured. Run setup wizard?',
        'Setup Now',
        'Later'
      )
      .then((choice) => {
        if (choice === 'Setup Now') {
          runSetupWizard(context.secrets);
        }
      });
  }

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

      await runAndShow(root, root, outputChannel, testResultsProvider, context);
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

      await runAndShow(filePath, root, outputChannel, testResultsProvider, context);
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand('contextdoc.checkDrift', async () => {
      const root = getWorkspaceRoot();
      if (!root) return;

      const entries = rescan(root);
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
      debounceTimer = setTimeout(() => {
        const entry = driftOf(source, root, loadIgnorePatterns(root));
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

/**
 * Try native runner first. If model/key not configured, fall back to CLI.
 */
async function resolveRunner(
  targetPath: string,
  workspaceRoot: string,
  outputChannel: vscode.OutputChannel,
  context: vscode.ExtensionContext,
): Promise<RunResult> {
  const config = vscode.workspace.getConfiguration('contextdoc');
  const model = config.get<string>('model', '');

  if (model) {
    // Native runner
    const { provider } = resolveProvider(model);
    let apiKey = '';

    // Try secrets store
    const stored = await context.secrets.get(`contextdoc.apiKey.${provider.id}`);
    if (stored) {
      apiKey = stored;
    } else {
      apiKey = getApiKey(provider.id);
    }

    if (provider.id === 'ollama' || apiKey) {
      outputChannel.appendLine(`[native] Running with model=${model}, provider=${provider.id}`);
      return runCtxTestsNative(targetPath, { model, apiKey });
    }

    outputChannel.appendLine(`[native] No API key for ${provider.id}, falling back to CLI`);
  }

  // Fallback to CLI
  outputChannel.appendLine('[cli] Using external ctx-run');
  return runCtxTests(targetPath, workspaceRoot, outputChannel);
}

async function runAndShow(
  targetPath: string,
  workspaceRoot: string,
  outputChannel: vscode.OutputChannel,
  provider: TestResultsProvider,
  context: vscode.ExtensionContext,
): Promise<void> {
  try {
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'Running conceptual tests...' },
      async () => {
        const result = await resolveRunner(targetPath, workspaceRoot, outputChannel, context);
        provider.update(result);

        const { steps_passed, steps_total, failed_scenarios } = result.summary;
        if (failed_scenarios === 0) {
          vscode.window.showInformationMessage(
            `ContextDoc: ${steps_passed}/${steps_total} steps passed.`
          );
        } else {
          vscode.window.showWarningMessage(
            `ContextDoc: ${failed_scenarios} scenario(s) failed. ${steps_passed}/${steps_total} steps passed.`
          );
        }
      }
    );
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    vscode.window.showErrorMessage(`ContextDoc: ${msg}`);
    outputChannel.appendLine(`Error: ${msg}`);
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
