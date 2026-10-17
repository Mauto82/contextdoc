// ctx-lint parity: the extension must report what tools/ctx-lint (the reference) reports on
// spec/lint/fixtures. For L007 (invalid YAML) only the code is compared: the message is the parser's.
const { test } = require('node:test');
const assert = require('node:assert');
const fs = require('fs');
const path = require('path');
const { lintFile } = require('../../out/lint.js');

const dir = path.join(__dirname, '..', '..', '..', 'spec', 'lint', 'fixtures');
const project = path.join(dir, 'project');
const expected = JSON.parse(fs.readFileSync(path.join(dir, 'expected.json'), 'utf-8'));

for (const [name, findings] of Object.entries(expected)) {
  test(`lint parity: ${name}`, () => {
    const actual = lintFile(path.join(project, name), project).map((f) => [f.line, f.code, f.message]);
    const strip = (list) => list.map(([line, code, message]) => (code === 'L007' ? [code] : [line, code, message]));
    assert.deepStrictEqual(strip(actual), strip(findings));
  });
}
