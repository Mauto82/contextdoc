import * as vscode from 'vscode';
import { RunResult, FileResult, ScenarioResult, StepResult } from './runner';

type TreeItem = FileItem | ScenarioItem | StepItem;

class FileItem extends vscode.TreeItem {
  constructor(public readonly file: FileResult) {
    const failed = file.scenarios.some(s => !s.overall_passed);
    const icon = file.error ? 'error' : failed ? 'close' : 'check';
    super(file.ctx_path, vscode.TreeItemCollapsibleState.Expanded);
    this.iconPath = new vscode.ThemeIcon(icon);
    if (file.error) {
      this.description = file.error;
    }
  }
}

class ScenarioItem extends vscode.TreeItem {
  constructor(
    public readonly scenario: ScenarioResult,
    public readonly sourcePath: string | null
  ) {
    super(scenario.name, vscode.TreeItemCollapsibleState.Expanded);
    const icon = scenario.error ? 'error' : scenario.overall_passed ? 'check' : 'close';
    this.iconPath = new vscode.ThemeIcon(icon);
    if (scenario.from_cache) {
      this.description = '(cached)';
    }
    if (scenario.error) {
      this.description = scenario.error;
    }
  }
}

class StepItem extends vscode.TreeItem {
  constructor(
    public readonly step: StepResult,
    public readonly sourcePath: string | null
  ) {
    super(step.action, vscode.TreeItemCollapsibleState.None);
    this.iconPath = new vscode.ThemeIcon(step.passed ? 'check' : 'close');
    this.description = step.expect;
    this.tooltip = step.explanation;
    if (sourcePath) {
      this.command = {
        command: 'vscode.open',
        title: 'Open Source',
        arguments: [vscode.Uri.file(sourcePath)]
      };
    }
  }
}

export class TestResultsProvider implements vscode.TreeDataProvider<TreeItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<TreeItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private result: RunResult | null = null;

  update(result: RunResult): void {
    this.result = result;
    this._onDidChangeTreeData.fire(undefined);
  }

  clear(): void {
    this.result = null;
    this._onDidChangeTreeData.fire(undefined);
  }

  getTreeItem(element: TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: TreeItem): TreeItem[] {
    if (!this.result) {
      return [];
    }
    if (!element) {
      return this.result.results.map(f => new FileItem(f));
    }
    if (element instanceof FileItem) {
      return element.file.scenarios.map(
        s => new ScenarioItem(s, element.file.source_path)
      );
    }
    if (element instanceof ScenarioItem) {
      return element.scenario.steps.map(
        st => new StepItem(st, element.sourcePath)
      );
    }
    return [];
  }
}
