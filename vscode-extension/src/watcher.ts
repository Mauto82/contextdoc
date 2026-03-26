import * as vscode from 'vscode';
import { execFile } from 'child_process';

export interface DriftEntry {
  filePath: string;
  reason: string;
}

export function checkDrift(
  changedFile: string,
  workspaceRoot: string
): Promise<DriftEntry[]> {
  return new Promise((resolve, reject) => {
    const config = vscode.workspace.getConfiguration('contextdoc');
    const ctxWatchPath = config.get<string>('ctxWatchPath', 'ctx-watch');

    const args = ['status', '.', '--changed-files', changedFile, '--no-color'];

    execFile(ctxWatchPath, args, { cwd: workspaceRoot }, (error, stdout, _stderr) => {
      const entries: DriftEntry[] = [];

      for (const line of stdout.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        // Match lines like: ⚠  src/utils.py  (.ctx is 2m 15s older than source)
        // or: ⚠  src/utils.py  (no .ctx file)
        const driftMatch = trimmed.match(/[⚠!]\s+(.+?)\s+\((.+)\)/);
        if (driftMatch) {
          entries.push({ filePath: driftMatch[1], reason: driftMatch[2] });
        }
      }

      resolve(entries);
    });
  });
}

export function checkFullDrift(workspaceRoot: string): Promise<DriftEntry[]> {
  return new Promise((resolve, reject) => {
    const config = vscode.workspace.getConfiguration('contextdoc');
    const ctxWatchPath = config.get<string>('ctxWatchPath', 'ctx-watch');

    const args = ['status', '.', '--no-color'];

    execFile(ctxWatchPath, args, { cwd: workspaceRoot }, (error, stdout, _stderr) => {
      const entries: DriftEntry[] = [];

      for (const line of stdout.split('\n')) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        const driftMatch = trimmed.match(/[⚠!]\s+(.+?)\s+\((.+)\)/);
        if (driftMatch) {
          entries.push({ filePath: driftMatch[1], reason: driftMatch[2] });
        }
      }

      resolve(entries);
    });
  });
}
