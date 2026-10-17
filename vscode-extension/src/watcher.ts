/**
 * Native drift detection: no Python, no ctx-watch CLI.
 * Same rules as tools/ctx-watch: a source file drifts when its .ctx companion is older than
 * the source; .ctxignore patterns and the same skipped directories and extensions apply.
 * Unlike the CLI, files without a .ctx are not reported: in the editor that would flag every
 * file, while ContextDoc expects a .ctx only where it adds value.
 */

import * as fs from 'fs';
import * as path from 'path';

export const DEFAULT_EXTENSIONS = new Set(['py', 'js', 'ts', 'go', 'rb', 'java', 'rs', 'php']);
const SKIP_DIRS = new Set(['.git', '.venv', '__pycache__', 'node_modules', '.mypy_cache']);

export interface DriftEntry {
  filePath: string; // absolute path of the source file
  reason: string;
}

export function fmtElapsed(seconds: number): string {
  const s = Math.floor(seconds);
  if (s < 60) { return `${s}s`; }
  if (s < 3600) { return `${Math.floor(s / 60)}m ${s % 60}s`; }
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

// fnmatch-style glob, as in Python: * and ? also match "/"
function globToRegExp(pattern: string): RegExp {
  let re = '';
  for (let i = 0; i < pattern.length; i++) {
    const ch = pattern[i];
    if (ch === '*') { re += '.*'; }
    else if (ch === '?') { re += '.'; }
    else if (ch === '[') {
      const end = pattern.indexOf(']', i + 1);
      if (end === -1) { re += '\\['; continue; }
      let set = pattern.slice(i + 1, end);
      if (set.startsWith('!')) { set = '^' + set.slice(1); }
      re += `[${set.replace(/\\/g, '\\\\')}]`;
      i = end;
    } else { re += ch.replace(/[.+^${}()|\\/]/g, '\\$&'); }
  }
  return new RegExp(`^${re}$`);
}

export function loadIgnorePatterns(root: string): string[] {
  const file = path.join(root, '.ctxignore');
  if (!fs.existsSync(file)) { return []; }
  return fs.readFileSync(file, 'utf-8')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('#'));
}

export function isIgnored(file: string, root: string, patterns: string[]): boolean {
  const rel = path.relative(root, file).split(path.sep).join('/');
  const name = path.basename(file);
  return patterns.some((p) => globToRegExp(p).test(rel) || (!p.includes('/') && globToRegExp(p).test(name)));
}

/** The source file a path refers to: itself, or the source of a .ctx companion. */
export function sourceFor(file: string): string {
  return file.endsWith('.ctx') ? file.slice(0, -4) : file;
}

export function isWatchedSource(file: string, root: string): boolean {
  const ext = path.extname(file).slice(1);
  if (!DEFAULT_EXTENSIONS.has(ext)) { return false; }
  const rel = path.relative(root, file);
  if (rel.startsWith('..') || path.isAbsolute(rel)) { return false; }
  return !rel.split(path.sep).some((part) => SKIP_DIRS.has(part));
}

/** Drift of one source file, or null (no .ctx, .ctx up to date, ignored, not a watched file). */
export function driftOf(source: string, root: string, patterns: string[]): DriftEntry | null {
  if (!isWatchedSource(source, root) || isIgnored(source, root, patterns)) { return null; }
  const ctx = source + '.ctx';
  let srcTime: number;
  let ctxTime: number;
  try {
    srcTime = fs.statSync(source).mtimeMs;
    ctxTime = fs.statSync(ctx).mtimeMs;
  } catch {
    return null;
  }
  if (ctxTime >= srcTime) { return null; }
  return { filePath: source, reason: `.ctx is ${fmtElapsed((srcTime - ctxTime) / 1000)} older than source` };
}

/** Every source file in the workspace whose .ctx is older than the source. */
export function scanDrift(root: string): DriftEntry[] {
  const patterns = loadIgnorePatterns(root);
  const entries: DriftEntry[] = [];
  const walk = (dir: string): void => {
    let items: fs.Dirent[];
    try { items = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const item of items) {
      const full = path.join(dir, item.name);
      if (item.isDirectory()) {
        if (!SKIP_DIRS.has(item.name)) { walk(full); }
      } else if (item.isFile() && item.name.endsWith('.ctx')) {
        const drift = driftOf(sourceFor(full), root, patterns);
        if (drift) { entries.push(drift); }
      }
    }
  };
  walk(root);
  return entries.sort((a, b) => a.filePath.localeCompare(b.filePath));
}
