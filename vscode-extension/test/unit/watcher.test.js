// Drift detection of the extension (out/watcher.js), same cases as tools/ctx-watch/tests/test_git_drift.py.
// Run with `npm run test:unit` (compiles first)
const { test } = require('node:test');
const assert = require('node:assert');
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { scanDrift } = require('../../out/watcher.js');

const env = { ...process.env, GIT_AUTHOR_NAME: 't', GIT_AUTHOR_EMAIL: 't@example.com', GIT_COMMITTER_NAME: 't', GIT_COMMITTER_EMAIL: 't@example.com' };
const git = (cwd, ...args) => execFileSync('git', args, { cwd, env, stdio: 'pipe' }).toString();
const commit = (cwd, msg) => { git(cwd, 'add', '-A'); git(cwd, 'commit', '-q', '-m', msg); };
const write = (dir, name, text) => fs.writeFileSync(path.join(dir, name), text);
const reasons = async (dir) => (await scanDrift(dir)).map((e) => `${path.basename(e.filePath)}: ${e.reason}`);

function repo() {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ctxdrift-')));
  git(dir, 'init', '-q', '-b', 'main');
  write(dir, 'app.py', 'x = 1\n');
  write(dir, 'app.py.ctx', 'purpose: "app"\n');
  commit(dir, 'initial');
  return dir;
}

test('git: synced pair has no drift', async () => {
  assert.deepStrictEqual(await reasons(repo()), []);
});

test('git: source committed after the .ctx drifts, counting commits', async () => {
  const dir = repo();
  for (const n of [2, 3]) { write(dir, 'app.py', `x = ${n}\n`); commit(dir, `change ${n}`); }
  assert.deepStrictEqual(await reasons(dir), ['app.py: .ctx not updated in 2 commit(s) that changed the source']);
});

test('git: updating the .ctx clears the drift', async () => {
  const dir = repo();
  write(dir, 'app.py', 'x = 2\n'); commit(dir, 'source');
  write(dir, 'app.py.ctx', 'purpose: "app, reviewed"\n'); commit(dir, 'ctx');
  assert.deepStrictEqual(await reasons(dir), []);
});

test('git: mtimes are ignored', async () => {
  const dir = repo();
  fs.utimesSync(path.join(dir, 'app.py.ctx'), new Date('2001-01-01'), new Date('2001-01-01'));
  assert.deepStrictEqual(await reasons(dir), []);
});

test('git: uncommitted source change drifts, unless the .ctx changes too', async () => {
  const dir = repo();
  write(dir, 'app.py', 'x = 2\n');
  assert.deepStrictEqual(await reasons(dir), ["app.py: source has uncommitted changes, .ctx doesn't"]);
  write(dir, 'app.py.ctx', 'purpose: "app, reviewed"\n');
  assert.deepStrictEqual(await reasons(dir), []);
});

test('git: files without a .ctx are not reported', async () => {
  const dir = repo();
  write(dir, 'new.py', 'y = 1\n');
  assert.deepStrictEqual(await reasons(dir), []);
});

test('no git: falls back to modification times', async () => {
  const dir = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'ctxdrift-')));
  write(dir, 'app.py', 'x = 1\n');
  write(dir, 'app.py.ctx', 'purpose: "app"\n');
  fs.utimesSync(path.join(dir, 'app.py.ctx'), new Date('2001-01-01'), new Date('2001-01-01'));
  const r = await reasons(dir);
  assert.strictEqual(r.length, 1);
  assert.match(r[0], /^app\.py: \.ctx is .* older than source$/);
});
