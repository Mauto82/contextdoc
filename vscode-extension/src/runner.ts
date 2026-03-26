import * as vscode from 'vscode';
import { execFile } from 'child_process';

export interface StepResult {
  action: string;
  expect: string;
  passed: boolean;
  explanation: string;
}

export interface ScenarioResult {
  name: string;
  overall_passed: boolean;
  error: string | null;
  from_cache: boolean;
  fix_suggestion: string | null;
  steps: StepResult[];
}

export interface FileResult {
  ctx_path: string;
  source_path: string | null;
  skipped: boolean;
  error: string | null;
  scenarios: ScenarioResult[];
}

export interface RunResult {
  summary: {
    files: number;
    scenarios: number;
    steps_passed: number;
    steps_total: number;
    failed_scenarios: number;
  };
  results: FileResult[];
}

export function runCtxTests(
  ctxPath: string,
  workspaceRoot: string,
  outputChannel: vscode.OutputChannel
): Promise<RunResult> {
  return new Promise((resolve, reject) => {
    const config = vscode.workspace.getConfiguration('contextdoc');
    const ctxRunPath = config.get<string>('ctxRunPath', 'ctx-run');
    const model = config.get<string>('model', '');

    const args = ['run', ctxPath, '--output', 'json', '--no-color'];
    if (model) {
      args.push('--model', model);
    }

    outputChannel.appendLine(`> ${ctxRunPath} ${args.join(' ')}`);

    execFile(ctxRunPath, args, { cwd: workspaceRoot, maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
      if (stderr) {
        outputChannel.appendLine(stderr);
      }

      if (!stdout.trim()) {
        reject(new Error(stderr || 'ctx-run produced no output'));
        return;
      }

      try {
        const result: RunResult = JSON.parse(stdout);
        resolve(result);
      } catch (e) {
        outputChannel.appendLine(`Failed to parse ctx-run output: ${stdout}`);
        reject(new Error(`Failed to parse ctx-run JSON output: ${e}`));
      }
    });
  });
}
