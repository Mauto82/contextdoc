/**
 * Smoke test of the PACKAGED extension: builds the .vsix (or takes one as argument), unpacks it
 * and runs it in a clean VS Code on a copy of examples/project-2. Catches what a run from the
 * sources can't: missing runtime dependencies, broken .vscodeignore, activation errors.
 *
 *   node test/smoke/run.js [path/to/contextdoc.vsix]
 *
 * Optional LLM run: set CONTEXTDOC_TEST_MODEL (e.g. ollama/gemma4:e2b) to also run the conceptual tests.
 * On Linux, run it under xvfb-run.
 */
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { runTests } = require('@vscode/test-electron');

const extRoot = path.resolve(__dirname, '../..');
const repoRoot = path.resolve(extRoot, '..');
// short base dir: VS Code's IPC socket path must stay under ~103 characters on macOS
const base = fs.mkdtempSync(path.join(fs.existsSync('/tmp') ? '/tmp' : os.tmpdir(), 'ctxsmoke-'));

function main() {
  let vsix = process.argv[2];
  if (!vsix) {
    vsix = path.join(base, 'contextdoc.vsix');
    execFileSync('npx', ['vsce', 'package', '--out', vsix], { cwd: extRoot, stdio: 'inherit' });
  }
  const unpacked = path.join(base, 'vsix');
  execFileSync('unzip', ['-q', path.resolve(vsix), '-d', unpacked]);

  // workspace: a copy of examples/project-2 with two sources newer than their .ctx (drift)
  const ws = path.join(base, 'ws');
  fs.cpSync(path.join(repoRoot, 'examples', 'project-2'), ws, { recursive: true });
  fs.rmSync(path.join(ws, '__pycache__'), { recursive: true, force: true });
  const old = new Date('2026-01-01T00:00:00Z');
  for (const f of fs.readdirSync(ws).filter((f) => f.endsWith('.ctx'))) { fs.utimesSync(path.join(ws, f), old, old); }
  const settings = { 'contextdoc.confirmRuns': false };
  if (process.env.CONTEXTDOC_TEST_MODEL) { settings['contextdoc.model'] = process.env.CONTEXTDOC_TEST_MODEL; }
  fs.mkdirSync(path.join(ws, '.vscode'));
  fs.writeFileSync(path.join(ws, '.vscode', 'settings.json'), JSON.stringify(settings));

  const userData = path.join(base, 'ud');
  return runTests({
    version: process.env.VSCODE_TEST_VERSION || 'stable',
    extensionDevelopmentPath: path.join(unpacked, 'extension'),
    extensionTestsPath: path.join(__dirname, 'suite.js'),
    // the result cache is shared with ctx-run under $XDG_CACHE_HOME: keep it inside the test folder
    extensionTestsEnv: { XDG_CACHE_HOME: path.join(base, 'cache'), CONTEXTDOC_TEST_MODEL: process.env.CONTEXTDOC_TEST_MODEL || '' },
    launchArgs: [ws, '--disable-extensions', '--skip-welcome', '--disable-workspace-trust',
      `--user-data-dir=${userData}`, `--extensions-dir=${path.join(base, 'ext')}`],
  });
}

main()
  .then(() => { console.log('smoke test passed'); })
  .catch((err) => { console.error('smoke test FAILED:', err && err.message ? err.message : err); process.exitCode = 1; })
  .finally(() => fs.rmSync(base, { recursive: true, force: true }));
