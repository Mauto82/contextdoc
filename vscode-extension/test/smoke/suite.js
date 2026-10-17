/**
 * Runs inside VS Code (see run.js). Throws on the first failed check, which fails the run.
 */
const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const check = (cond, msg) => { if (!cond) { throw new Error(msg); } console.log(`  ✓ ${msg}`); };
const driftFiles = () => vscode.languages.getDiagnostics()
  .filter(([, d]) => d.some((x) => x.source === 'ContextDoc'))
  .map(([u]) => path.basename(u.fsPath))
  .sort();

async function until(fn, ms = 10000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { if (await fn()) { return true; } await wait(200); }
  return false;
}

exports.run = async () => {
  const ext = vscode.extensions.getExtension('Mauto.contextdoc');
  check(!!ext, 'extension is installed');
  await ext.activate();
  check(ext.isActive, `extension ${ext.packageJSON.version} activates`);

  const commands = await vscode.commands.getCommands(true);
  for (const c of ['contextdoc.runTests', 'contextdoc.runTestsOnFile', 'contextdoc.checkDrift', 'contextdoc.setup', 'contextdoc.clearCache']) {
    check(commands.includes(c), `command ${c} is registered`);
  }

  // startup scan: coupon.py and store.py are newer than their .ctx
  await until(() => driftFiles().length === 2);
  check(JSON.stringify(driftFiles()) === '["coupon.py","store.py"]', 'startup scan reports coupon.py and store.py');

  // saving store.py.ctx clears store.py only
  const root = vscode.workspace.workspaceFolders[0].uri.fsPath;
  const doc = await vscode.workspace.openTextDocument(path.join(root, 'store.py.ctx'));
  const editor = await vscode.window.showTextDocument(doc);
  await editor.edit((b) => b.insert(new vscode.Position(0, 0), '# reviewed\n'));
  await doc.save();
  await until(() => driftFiles().length === 1);
  check(JSON.stringify(driftFiles()) === '["coupon.py"]', 'saving store.py.ctx clears its drift and keeps the others');

  const lenses = await vscode.commands.executeCommand('vscode.executeCodeLensProvider', doc.uri);
  check((lenses || []).some((l) => l.command && l.command.command === 'contextdoc.runTestsOnFile'), 'Run Tests CodeLens on conceptualTests');

  if (process.env.CONTEXTDOC_TEST_MODEL) {
    await vscode.commands.executeCommand('contextdoc.runTestsOnFile');
    const cache = path.join(process.env.CONTEXTDOC_SMOKE_USER_DATA, 'User', 'globalStorage', 'mauto.contextdoc', 'results-cache.json');
    check(fs.existsSync(cache), `Run Tests with ${process.env.CONTEXTDOC_TEST_MODEL} completes and caches results`);
  } else {
    console.log('  - LLM run skipped (set CONTEXTDOC_TEST_MODEL to enable)');
  }
};
