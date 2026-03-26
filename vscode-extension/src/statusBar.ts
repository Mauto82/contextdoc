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
