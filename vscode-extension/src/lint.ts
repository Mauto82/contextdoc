/**
 * ctx-lint in the editor: the same rules as tools/ctx-lint (spec/lint/lint-spec.json, copied into out/
 * by `npm run compile`), checked against the same fixtures (test/unit/lint.test.js). Warnings only.
 * L007 (invalid YAML) reports the parser's own message, which differs between Python and JavaScript.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'yaml';

interface LintSpec {
  sections: string[];
  legacySections: string[];
  maxLines: number;
  purposeMaxChars: number;
  vagueExpects: string[];
  signaturePatterns: Record<string, string>;
  minSignatureChars: number;
  validation: { action: string; expect: string; minSteps: number; minShare: number };
  messages: Record<string, string>;
}

function loadSpec(): LintSpec {
  for (const file of [
    process.env.CTX_LINT_SPEC,
    path.join(__dirname, 'lint-spec.json'),
    path.join(__dirname, '..', '..', 'spec', 'lint', 'lint-spec.json'),
  ]) {
    if (file && fs.existsSync(file)) { return JSON.parse(fs.readFileSync(file, 'utf-8')); }
  }
  throw new Error('lint-spec.json not found');
}

const SPEC = loadSpec();

export interface Finding { line: number; code: string; message: string }

const msg = (code: string, values: Record<string, string | number> = {}): string =>
  SPEC.messages[code].replace(/\$\{(\w+)\}/g, (m, k: string) => (k in values ? String(values[k]) : m));

const norm = (text: unknown): string => String(text).replace(/\s+/g, ' ').trim();

function splitLines(text: string): string[] {
  const lines = text.split(/\r\n|\r|\n/);
  if (lines.length && lines[lines.length - 1] === '') { lines.pop(); }
  return lines;
}

class Lines {
  constructor(readonly lines: string[]) {}

  of(needle: string, start = 1): number {
    const probe = norm(needle).slice(0, 40);
    if (probe) {
      for (let i = start - 1; i < this.lines.length; i++) {
        if (norm(this.lines[i]).includes(probe)) { return i + 1; }
      }
    }
    return start;
  }

  key(name: string): number {
    const re = new RegExp(`^${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*:`);
    const i = this.lines.findIndex((l) => re.test(l));
    return i >= 0 ? i + 1 : 1;
  }
}

function strings(value: unknown): string[] {
  if (typeof value === 'string') { return [value]; }
  if (Array.isArray(value)) { return value.flatMap(strings); }
  if (value && typeof value === 'object') { return Object.values(value as object).flatMap(strings); }
  return [];
}

function items(data: Record<string, unknown>, key: string): string[] {
  const v = data[key];
  if (Array.isArray(v)) { return v.map(String); }
  if (v && typeof v === 'object') { return Object.values(v as object).map(String); }
  return [];
}

function projectCtx(ctxPath: string, root: string): string | null {
  let d = path.dirname(path.resolve(ctxPath));
  const top = path.resolve(root);
  for (;;) {
    const candidate = path.join(d, 'project.ctx');
    if (fs.existsSync(candidate) && path.resolve(candidate) !== path.resolve(ctxPath)) { return candidate; }
    if (d === top || path.dirname(d) === d || !d.startsWith(top)) { return null; }
    d = path.dirname(d);
  }
}

export function lintText(ctxPath: string, text: string, root: string): Finding[] {
  const lines = new Lines(splitLines(text));
  let data: unknown;
  try {
    data = yaml.parse(text) ?? {};
  } catch (err) {
    const pos = (err as { linePos?: Array<{ line: number }> }).linePos?.[0]?.line ?? 1;
    return [{ line: pos, code: 'L007', message: msg('L007', { error: norm((err as Error).message.split('\n')[0]) }) }];
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return [{ line: 1, code: 'L007', message: msg('L007', { error: 'the top level must be a mapping of sections' }) }];
  }
  const doc = data as Record<string, unknown>;
  const findings: Finding[] = [];
  const add = (line: number, code: string, message: string): void => { findings.push({ line, code, message }); };

  if (lines.lines.length > SPEC.maxLines) {
    add(1, 'L001', msg('L001', { lines: lines.lines.length, max: SPEC.maxLines }));
  }

  for (const key of Object.keys(doc)) {
    if (!SPEC.sections.includes(key)) {
      const hint = SPEC.legacySections.includes(key) ? msg('L003legacy') : msg('L003unknown');
      add(lines.key(key), 'L003', msg('L003', { key, allowed: SPEC.sections.join(', '), hint }));
    }
  }

  const purpose = doc.purpose;
  if (typeof purpose === 'string' && (purpose.length > SPEC.purposeMaxChars || purpose.trim().includes('\n'))) {
    add(lines.key('purpose'), 'L008', msg('L008', { chars: purpose.trim().length }));
  }

  const source = ctxPath.slice(0, -4);
  const pattern = SPEC.signaturePatterns[path.extname(source).toLowerCase()];
  if (pattern && fs.existsSync(source)) {
    const code = fs.readFileSync(source, 'utf-8');
    const sigs = new Set<string>();
    for (const m of code.matchAll(new RegExp(pattern, 'gm'))) { sigs.add(norm(m[0])); }
    const signatures = [...sigs].filter((s) => s.length >= SPEC.minSignatureChars);
    const allowedOnly = Object.fromEntries(Object.entries(doc).filter(([k]) => SPEC.sections.includes(k)));
    const reported = new Set<string>();
    for (const s of strings(allowedOnly)) {
      for (const sig of signatures) {
        if (norm(s).includes(sig) && !reported.has(sig)) {
          reported.add(sig);
          add(lines.of(sig), 'L002', msg('L002', { signature: sig }));
        }
      }
    }
  }

  if (path.basename(ctxPath) !== 'project.ctx') {
    const project = projectCtx(ctxPath, root);
    if (project) {
      let pdata: unknown = {};
      try { pdata = yaml.parse(fs.readFileSync(project, 'utf-8')) ?? {}; } catch { pdata = {}; }
      if (pdata && typeof pdata === 'object' && !Array.isArray(pdata)) {
        const p = pdata as Record<string, unknown>;
        const theirs = new Set(['tensions', 'workflows'].flatMap((k) => items(p, k)).map(norm));
        for (const k of ['tensions', 'workflows']) {
          for (const s of items(doc, k)) {
            if (theirs.has(norm(s))) {
              add(lines.of(s), 'L004', msg('L004', { other: path.relative(path.dirname(path.resolve(ctxPath)), project) }));
            }
          }
        }
      }
    }
  }

  const actionRe = new RegExp(SPEC.validation.action, 'i');
  const expectRe = new RegExp(SPEC.validation.expect, 'i');
  const vague = new Set(SPEC.vagueExpects.map((v) => v.toLowerCase()));
  const testsLine = lines.key('conceptualTests');
  let validationSteps = 0;
  let totalSteps = 0;
  const tests = Array.isArray(doc.conceptualTests) ? doc.conceptualTests : [];
  for (const scenario of tests) {
    if (!scenario || typeof scenario !== 'object' || Array.isArray(scenario)) { continue; }
    const steps = (scenario as { steps?: unknown }).steps;
    for (const step of Array.isArray(steps) ? steps : []) {
      if (!step || typeof step !== 'object' || Array.isArray(step)) { continue; }
      totalSteps++;
      const s = step as { action?: unknown; expect?: unknown };
      const action = s.action === undefined || s.action === null ? '' : String(s.action);
      const at = action ? lines.of(action, testsLine) : testsLine;
      if (s.expect === undefined || s.expect === null || !String(s.expect).trim()) {
        add(at, 'L006', msg('L006missing'));
        continue;
      }
      const expect = String(s.expect);
      if (vague.has(expect.trim().replace(/^[.!]+|[.!]+$/g, '').toLowerCase())) {
        add(lines.of(expect, at), 'L006', msg('L006vague', { expect: expect.trim() }));
      }
      if (actionRe.test(action) && expectRe.test(expect)) { validationSteps++; }
    }
  }
  if (validationSteps >= SPEC.validation.minSteps && validationSteps >= SPEC.validation.minShare * totalSteps) {
    add(testsLine, 'L005', msg('L005', { count: validationSteps, total: totalSteps }));
  }

  // same order as Python's sorted() on (line, code, message): plain code-point comparison
  const cmp = (x: string, y: string): number => (x < y ? -1 : x > y ? 1 : 0);
  return findings.sort((a, b) => a.line - b.line || cmp(a.code, b.code) || cmp(a.message, b.message));
}

export function lintFile(ctxPath: string, root: string): Finding[] {
  return lintText(ctxPath, fs.readFileSync(ctxPath, 'utf-8'), root);
}
