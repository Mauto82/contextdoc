/**
 * Native drift detection: no Python, no ctx-watch CLI. Same rules as `ctx-watch status`:
 * - inside a git repository, from the history: a source drifts when commits after the last commit
 *   that touched its .ctx changed it, or when it has uncommitted changes and its .ctx doesn't
 *   (mtimes say nothing after a clone, checkout or rebase);
 * - outside git, from modification times: the .ctx is older than the source.
 * .ctxignore patterns and the same skipped directories and extensions apply. Files without a .ctx
 * are not reported: ContextDoc expects a .ctx only where it adds value.
 */

import { execFile } from 'child_process';
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

function git(cwd: string, args: string[]): Promise<string | null> {
  return new Promise((resolve) => {
    execFile('git', args, { cwd, maxBuffer: 16 * 1024 * 1024 }, (err, stdout) => resolve(err ? null : stdout));
  });
}

/** Top folder of the git repository containing DIR, or null outside git (or without git installed). */
export async function gitToplevel(dir: string): Promise<string | null> {
  const out = await git(dir, ['rev-parse', '--show-toplevel']);
  return out ? fs.realpathSync(out.trim()) : null;
}

/** Drift reason from git history, for a source whose .ctx exists. */
async function gitDrift(source: string, ctx: string, top: string): Promise<string | null> {
  const rel = (p: string): string => path.relative(top, fs.realpathSync(p)).split(path.sep).join('/');
  const src = rel(source);
  const doc = rel(ctx);
  const status = (await git(top, ['status', '--porcelain=v1', '-z', '--no-renames', '--untracked-files=all', '--', src, doc])) ?? '';
  const dirty = new Set(status.split('\0').filter((e) => e.length > 3).map((e) => e.slice(3)));
  if (dirty.has(doc)) { return null; }  // the .ctx is being updated alongside
  if (dirty.has(src)) { return "source has uncommitted changes, .ctx doesn't"; }

  const log = (await git(top, ['log', '--topo-order', '--no-renames', '--name-only', '--format=%x00%H', '--', src, doc])) ?? '';
  const commits = log.split('\0').filter((b) => b.trim()).map((b) => b.split('\n').slice(1).filter(Boolean));
  const ctxIndex = commits.findIndex((files) => files.includes(doc));
  if (ctxIndex < 0) { return null; }
  const newer = commits.slice(0, ctxIndex).filter((files) => files.includes(src)).length;
  return newer > 0 ? `.ctx not updated in ${newer} commit(s) that changed the source` : null;
}

function mtimeDrift(source: string, ctx: string): string | null {
  const srcTime = fs.statSync(source).mtimeMs;
  const ctxTime = fs.statSync(ctx).mtimeMs;
  return ctxTime >= srcTime ? null : `.ctx is ${fmtElapsed((srcTime - ctxTime) / 1000)} older than source`;
}

/** Drift of one source file, or null (no .ctx, up to date, ignored, not a watched file).
 *  GIT_TOP: the repository's top folder, or null to use modification times. */
export async function driftOf(source: string, root: string, patterns: string[], gitTop: string | null): Promise<DriftEntry | null> {
  if (!isWatchedSource(source, root) || isIgnored(source, root, patterns)) { return null; }
  const ctx = source + '.ctx';
  if (!fs.existsSync(source) || !fs.existsSync(ctx)) { return null; }
  const reason = gitTop ? await gitDrift(source, ctx, gitTop) : mtimeDrift(source, ctx);
  return reason ? { filePath: source, reason } : null;
}

/** Every source file in the workspace that drifted from its .ctx. */
export async function scanDrift(root: string): Promise<DriftEntry[]> {
  const patterns = loadIgnorePatterns(root);
  const gitTop = await gitToplevel(root);
  const sources: string[] = [];
  const walk = (dir: string): void => {
    let items: fs.Dirent[];
    try { items = fs.readdirSync(dir, { withFileTypes: true }); } catch { return; }
    for (const item of items) {
      const full = path.join(dir, item.name);
      if (item.isDirectory()) {
        if (!SKIP_DIRS.has(item.name)) { walk(full); }
      } else if (item.isFile() && item.name.endsWith('.ctx')) {
        sources.push(sourceFor(full));
      }
    }
  };
  walk(root);
  const entries: DriftEntry[] = [];
  for (const source of sources) {
    const drift = await driftOf(source, root, patterns, gitTop);
    if (drift) { entries.push(drift); }
  }
  return entries.sort((a, b) => a.filePath.localeCompare(b.filePath));
}
