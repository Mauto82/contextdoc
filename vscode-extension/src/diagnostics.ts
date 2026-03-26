import * as vscode from 'vscode';
import * as path from 'path';
import { DriftEntry } from './watcher';

const SOURCE = 'ContextDoc';

export function updateDiagnostics(
  collection: vscode.DiagnosticCollection,
  entries: DriftEntry[],
  workspaceRoot: string
): void {
  collection.clear();

  const byFile = new Map<string, vscode.Diagnostic[]>();

  for (const entry of entries) {
    const absPath = path.isAbsolute(entry.filePath)
      ? entry.filePath
      : path.join(workspaceRoot, entry.filePath);
    const uri = vscode.Uri.file(absPath);
    const key = uri.toString();

    const diag = new vscode.Diagnostic(
      new vscode.Range(0, 0, 0, 0),
      `${entry.reason}`,
      vscode.DiagnosticSeverity.Warning
    );
    diag.source = SOURCE;

    if (!byFile.has(key)) {
      byFile.set(key, []);
    }
    byFile.get(key)!.push(diag);
  }

  for (const [uriStr, diags] of byFile) {
    collection.set(vscode.Uri.parse(uriStr), diags);
  }
}
