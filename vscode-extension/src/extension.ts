import * as vscode from 'vscode';
import * as path from 'path';
import { runCtxTests, RunResult } from './runner';
import { runCtxTestsNative } from './ctxRunner';
import { resolveProvider, getApiKey } from './llm';
import { TestResultsProvider } from './testResultsView';
import { checkDrift, checkFullDrift } from './watcher';
import { updateDiagnostics } from './diagnostics';
import { StatusBarManager } from './statusBar';
import { isConfigured, runSetupWizard } from './setupWizard';

let debounceTimer: ReturnType<typeof setTimeout> | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const outputChannel = vscode.window.createOutputChannel('ContextDoc');
  const diagnosticCollection = vscode.languages.createDiagnosticCollection('contextdoc');
  const statusBar = new StatusBarManager();
  const testResultsProvider = new TestResultsProvider();

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

      const entries = await checkFullDrift(root);
      updateDiagnostics(diagnosticCollection, entries, root);
      statusBar.setDriftCount(entries.length);

      if (entries.length === 0) {
        vscode.window.showInformationMessage('ContextDoc: no drift detected.');
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

      debounceTimer = setTimeout(async () => {
        const relativePath = path.relative(root, doc.uri.fsPath);
        const entries = await checkDrift(relativePath, root);
        updateDiagnostics(diagnosticCollection, entries, root);
        statusBar.setDriftCount(entries.length);
      }, 2000);
    })
  );

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
    vscode.window.withProgress(
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
