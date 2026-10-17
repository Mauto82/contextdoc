/**
 * Result cache shared with ctx-run: same file ($XDG_CACHE_HOME/ctx-run/cache.json, or
 * ~/.cache/ctx-run/cache.json), same entry format and same key, as defined in the runner spec.
 * A result computed by the CLI is reused by the extension and vice versa.
 * Key: sha256 of canonical JSON of the scenario (Python's json.dumps(sort_keys=True)) + source + model.
 */

import * as crypto from 'crypto';
import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';
import { ScenarioResult } from './runner';
import { SPEC } from './spec';

const MAX_ENTRIES = 5000;

export function defaultCachePath(): string {
  const base = process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
  return path.join(base, 'ctx-run', 'cache.json');
}

// Python json.dumps(..., sort_keys=True): ", " and ": " separators, every char outside ' '..'~' escaped
function pyString(s: string): string {
  return JSON.stringify(s).replace(/[^\x20-\x7e]/g, (c) => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
}

export function canonicalJson(value: unknown): string {
  if (value === null || value === undefined) { return 'null'; }
  if (typeof value === 'string') { return pyString(value); }
  if (typeof value === 'boolean') { return value ? 'true' : 'false'; }
  if (typeof value === 'number') { return String(value); }
  if (Array.isArray(value)) { return `[${value.map(canonicalJson).join(', ')}]`; }
  const obj = value as Record<string, unknown>;
  return `{${Object.keys(obj).sort().map((k) => `${pyString(k)}: ${canonicalJson(obj[k])}`).join(', ')}}`;
}

export function cacheKey(scenario: unknown, sourceContent: string | null, model: string): string {
  return crypto.createHash('sha256').update(canonicalJson(scenario) + (sourceContent ?? '') + model, 'utf8').digest('hex');
}

interface Entry {
  timestamp: string;
  result: {
    name: string;
    overall_passed: boolean;
    error: string | null;
    steps: Array<{ action: string; expect: string; passed: boolean; explanation: string }>;
  };
}

function readEntries(file: string): Record<string, Entry> {
  try {
    const data = JSON.parse(fs.readFileSync(file, 'utf-8'));
    return data.version === SPEC.cache.version ? (data.entries ?? {}) : {};
  } catch {
    return {}; // missing or corrupt: an empty cache
  }
}

export class ResultCache {
  private entries: Record<string, Entry>;
  private added: Record<string, Entry> = {};

  /** FILE: the cache file, null for an in-memory cache (tests), undefined for the one shared with ctx-run. */
  constructor(private file: string | null = defaultCachePath()) {
    this.entries = file ? readEntries(file) : {};
  }

  get(key: string): ScenarioResult | undefined {
    const e = this.added[key] ?? this.entries[key];
    if (!e) { return undefined; }
    return {
      name: e.result.name,
      overall_passed: e.result.overall_passed,
      error: e.result.error ?? null,
      from_cache: true,
      fix_suggestion: null,
      steps: e.result.steps.map((s) => ({ ...s })),
    };
  }

  has(key: string): boolean {
    return key in this.added || key in this.entries;
  }

  set(key: string, result: ScenarioResult): void {
    this.added[key] = {
      timestamp: new Date().toISOString(),
      result: {
        name: result.name,
        overall_passed: result.overall_passed,
        error: result.error,
        steps: result.steps.map((s) => ({ action: s.action, expect: s.expect, passed: s.passed, explanation: s.explanation })),
      },
    };
  }

  get size(): number {
    return Object.keys({ ...this.entries, ...this.added }).length;
  }

  clear(): void {
    this.entries = {};
    this.added = {};
    if (this.file && fs.existsSync(this.file)) { fs.rmSync(this.file); }
  }

  /** Writes the new results, merged with what ctx-run may have written meanwhile. Atomic (tmp + rename). */
  save(): void {
    if (!this.file || Object.keys(this.added).length === 0) { return; }
    const merged = { ...readEntries(this.file), ...this.added };
    const kept = Object.entries(merged)
      .sort((a, b) => (b[1].timestamp ?? '').localeCompare(a[1].timestamp ?? ''))
      .slice(0, MAX_ENTRIES);
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    const tmp = `${this.file}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify({ version: SPEC.cache.version, entries: Object.fromEntries(kept) }, null, 2));
    fs.renameSync(tmp, this.file);
    this.entries = Object.fromEntries(kept);
    this.added = {};
  }
}
