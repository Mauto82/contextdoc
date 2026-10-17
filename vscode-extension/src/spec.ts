/**
 * The runner spec shared with ctx-run (spec/runner/runner-spec.json in the repository):
 * prompts, languages, result texts and cache rules. `npm run compile` copies it into out/.
 */

import * as fs from 'fs';
import * as path from 'path';

export interface RunnerSpec {
  version: number;
  llm: { temperature: number; maxTokens: number };
  languages: Record<string, string>;
  evaluate: {
    system: string; source: string; sourceMissing: string; sourceMissingDefaultNote: string;
    sourceMissingInstruction: string; scenario: string; stepsHeader: string; step: string; instructions: string;
  };
  fix: {
    system: string; source: string; sourceMissing: string; header: string; step: string; analysis: string; instructions: string;
  };
  results: { unparsable: string; unparsableRawChars: number; llmError: string; stepMissing: string };
  cache: { version: number };
}

function load(): RunnerSpec {
  const candidates = [
    process.env.CTX_RUNNER_SPEC,
    path.join(__dirname, 'runner-spec.json'),                            // packaged extension
    path.join(__dirname, '..', '..', 'spec', 'runner', 'runner-spec.json'), // repository checkout
  ];
  for (const file of candidates) {
    if (file && fs.existsSync(file)) { return JSON.parse(fs.readFileSync(file, 'utf-8')); }
  }
  throw new Error('runner-spec.json not found');
}

export const SPEC: RunnerSpec = load();

/** Replace ${name} placeholders in one pass: inserted values are never scanned again. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\$\{(\w+)\}/g, (match, key: string) => (key in values ? String(values[key]) : match));
}
