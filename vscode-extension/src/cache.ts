/**
 * Result cache for conceptual tests, as in ctx-run: the key is a hash of the scenario,
 * the source code and the model, so a result is reused only while none of the three changes.
 * Stored as JSON in the extension's global storage; unlike ctx-run it is not shared with the CLI.
 */

import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { ScenarioResult } from './runner';

const VERSION = 1;
const MAX_ENTRIES = 2000;

// JSON with sorted keys, like Python's json.dumps(sort_keys=True)
function stableStringify(value: unknown): string {
  if (Array.isArray(value)) { return `[${value.map(stableStringify).join(',')}]`; }
  if (value && typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    return `{${Object.keys(obj).sort().map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

export function cacheKey(scenario: unknown, sourceContent: string | null, model: string): string {
  return crypto.createHash('sha256')
    .update(stableStringify(scenario) + (sourceContent ?? '') + model)
    .digest('hex');
}

interface Entry {
  result: ScenarioResult;
  at: number;
}

export class ResultCache {
  private entries = new Map<string, Entry>();

  constructor(private file: string | null) {
    if (!file || !fs.existsSync(file)) { return; }
    try {
      const data = JSON.parse(fs.readFileSync(file, 'utf-8'));
      if (data.version === VERSION) {
        for (const [k, v] of Object.entries(data.entries ?? {})) { this.entries.set(k, v as Entry); }
      }
    } catch {
      // a corrupt cache is just an empty cache
    }
  }

  get(key: string): ScenarioResult | undefined {
    return this.entries.get(key)?.result;
  }

  has(key: string): boolean {
    return this.entries.has(key);
  }

  set(key: string, result: ScenarioResult): void {
    this.entries.set(key, { result, at: Date.now() });
  }

  get size(): number {
    return this.entries.size;
  }

  clear(): void {
    this.entries.clear();
    this.save();
  }

  save(): void {
    if (!this.file) { return; }
    // keep the most recent entries only
    const sorted = [...this.entries.entries()].sort((a, b) => b[1].at - a[1].at).slice(0, MAX_ENTRIES);
    fs.mkdirSync(path.dirname(this.file), { recursive: true });
    fs.writeFileSync(this.file, JSON.stringify({ version: VERSION, entries: Object.fromEntries(sorted) }));
  }
}
