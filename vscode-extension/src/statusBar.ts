import * as vscode from 'vscode';

export class StatusBarManager {
  private item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
    this.item.command = 'workbench.actions.view.problems';
    this.setDriftCount(0);
    this.item.show();
  }

  setDriftCount(count: number): void {
    if (count === 0) {
      this.item.text = '$(check) ctx: 0 drift';
      this.item.backgroundColor = undefined;
    } else {
      this.item.text = `$(warning) ctx: ${count} drift`;
      this.item.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
    }
  }

  dispose(): void {
    this.item.dispose();
  }
}

/** The model in use, always visible: a click opens the setup to change it. */
export class ModelStatusBar {
  private item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 49);
    this.item.command = 'contextdoc.setup';
    this.refresh();
    this.item.show();
  }

  refresh(): void {
    const model = vscode.workspace.getConfiguration('contextdoc').get<string>('model', '');
    this.item.text = model ? `$(beaker) ${model}` : '$(beaker) ctx: no model';
    this.item.tooltip = model ? 'ContextDoc model: click to change' : 'ContextDoc: click to choose a model';
  }

  dispose(): void {
    this.item.dispose();
  }
}
