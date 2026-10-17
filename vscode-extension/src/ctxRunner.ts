/**
 * Native TypeScript ctx-run: parses .ctx YAML, runs conceptual tests via LLM.
 * Replaces the Python ctx-run CLI for the VS Code extension.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'yaml';
import { resolveProvider, LlmMessage, CancelledError } from './llm';
import { ResultCache, cacheKey } from './cache';
import { SPEC, fill } from './spec';
import { RunResult, FileResult, ScenarioResult, StepResult } from './runner';

// ---------------------------------------------------------------------------
// Language map (from the shared runner spec)
// ---------------------------------------------------------------------------

const LANG_MAP: Record<string, string> = SPEC.languages;

const SKIP_DIRS = new Set(['.git', '.venv', '__pycache__', 'node_modules', '.mypy_cache']);

// ---------------------------------------------------------------------------
// File discovery
// ---------------------------------------------------------------------------

export function collectCtxFiles(target: string): string[] {
  const stat = fs.statSync(target);

  if (stat.isFile()) {
    if (!target.endsWith('.ctx')) {
      throw new Error(`File must end in .ctx: ${target}`);
    }
    return [target];
  }

  if (stat.isDirectory()) {
    const paths: string[] = [];
    walkDir(target, paths);
    if (paths.length === 0) {
      throw new Error(`No .ctx files found in: ${target}`);
    }
    return paths.sort();
  }

  throw new Error(`Path not found: ${target}`);
}

function walkDir(dir: string, results: string[]): void {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (!SKIP_DIRS.has(entry.name)) {
        walkDir(path.join(dir, entry.name), results);
      }
    } else if (entry.isFile() && entry.name.endsWith('.ctx')) {
      results.push(path.join(dir, entry.name));
    }
  }
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

function loadCtx(ctxPath: string): Record<string, unknown> {
  const content = fs.readFileSync(ctxPath, 'utf-8');
  return (yaml.parse(content) as Record<string, unknown>) ?? {};
}

function resolveSource(ctxPath: string): { sourcePath: string | null; sourceContent: string | null; warning: string | null } {
  if (!ctxPath.endsWith('.ctx')) {
    return { sourcePath: null, sourceContent: null, warning: 'cannot derive source path' };
  }
  const sourcePath = ctxPath.slice(0, -4);
  if (!fs.existsSync(sourcePath)) {
    return { sourcePath, sourceContent: null, warning: `source file not found: ${sourcePath}` };
  }
  const sourceContent = fs.readFileSync(sourcePath, 'utf-8');
  return { sourcePath, sourceContent, warning: null };
}

function detectLanguage(sourcePath: string | null): string {
  if (!sourcePath) { return ''; }
  const ext = path.extname(sourcePath).toLowerCase();
  return LANG_MAP[ext] ?? '';
}

// ---------------------------------------------------------------------------
// Prompt construction: templates from the shared runner spec, same assembly as ctx_run.py
// (the parity tests in test/unit check that both produce identical prompts)
// ---------------------------------------------------------------------------

interface TestStep {
  action?: string;
  expect?: string;
}

interface TestScenario {
  name?: string;
  steps?: TestStep[];
}

export function buildSystemPrompt(): string {
  return SPEC.evaluate.system;
}

function sourceBlock(template: string, sourcePath: string | null, sourceContent: string, language: string): string {
  const fence = language ? '```' + language : '```';
  return fill(template, { label: sourcePath ?? 'unknown', fence, source: sourceContent });
}

export function buildUserMessage(
  scenario: TestScenario,
  sourcePath: string | null,
  sourceContent: string | null,
  sourceWarning: string | null,
  language: string,
): string {
  const t = SPEC.evaluate;
  const parts: string[] = [];
  if (sourceContent) {
    parts.push(sourceBlock(t.source, sourcePath, sourceContent, language));
  } else {
    parts.push(fill(t.sourceMissing, { note: sourceWarning ?? t.sourceMissingDefaultNote }));
    parts.push(t.sourceMissingInstruction);
  }
  parts.push(fill(t.scenario, { name: scenario.name ?? 'unnamed' }));
  parts.push(t.stepsHeader);
  (scenario.steps ?? []).forEach((step, i) => {
    parts.push(fill(t.step, { n: i + 1, action: step.action ?? '', expect: step.expect ?? '' }));
  });
  parts.push(t.instructions);
  return parts.join('\n');
}

/** Prompt for a fix suggestion (ctx-run --fix): the failing steps and the source. */
export function buildFixPrompt(
  scenario: TestScenario,
  failedSteps: Array<{ action: string; expect: string; explanation: string }>,
  sourcePath: string | null,
  sourceContent: string | null,
  language: string,
): string {
  const t = SPEC.fix;
  const parts: string[] = [];
  parts.push(sourceContent ? sourceBlock(t.source, sourcePath, sourceContent, language) : t.sourceMissing);
  parts.push(fill(t.header, { name: scenario.name ?? 'unnamed' }));
  for (const step of failedSteps) {
    parts.push(fill(t.step, { action: step.action, expect: step.expect }));
    if (step.explanation) { parts.push(fill(t.analysis, { explanation: step.explanation })); }
  }
  parts.push(t.instructions);
  return parts.join('\n');
}

// ---------------------------------------------------------------------------
// Response parsing (3-layer like Python version)
// ---------------------------------------------------------------------------

export function parseLlmResponse(raw: string): Record<string, unknown> | null {
  // Layer 1: direct parse
  try { return JSON.parse(raw); } catch {}

  // Layer 2: strip markdown fences
  const stripped = raw.trim().replace(/^```(?:json)?\s*/m, '').replace(/\s*```$/m, '');
  try { return JSON.parse(stripped); } catch {}

  // Layer 3: extract outermost {...}
  const match = raw.match(/\{[\s\S]*\}/);
  if (match) {
    try { return JSON.parse(match[0]); } catch {}
  }

  return null;
}

export function buildScenarioResult(
  scenario: TestScenario,
  rawResponse: string,
  parsed: Record<string, unknown> | null,
): ScenarioResult {
  const name = scenario.name ?? 'unnamed';
  const expectedSteps = scenario.steps ?? [];

  if (parsed === null) {
    return {
      name,
      overall_passed: false,
      error: fill(SPEC.results.unparsable, { raw: rawResponse.slice(0, SPEC.results.unparsableRawChars) }),
      from_cache: false,
      fix_suggestion: null,
      steps: [],
    };
  }

  const llmSteps = (parsed.steps as Array<Record<string, unknown>>) ?? [];
  const stepResults: StepResult[] = [];

  for (let i = 0; i < expectedSteps.length; i++) {
    const expected = expectedSteps[i];
    if (i < llmSteps.length) {
      const llmStep = llmSteps[i];
      stepResults.push({
        action: expected.action ?? '',
        expect: expected.expect ?? '',
        passed: Boolean(llmStep.passed),
        explanation: String(llmStep.explanation ?? ''),
      });
    } else {
      stepResults.push({
        action: expected.action ?? '',
        expect: expected.expect ?? '',
        passed: false,
        explanation: SPEC.results.stepMissing,
      });
    }
  }

  const overallPassed = stepResults.every((s) => s.passed);

  return {
    name,
    overall_passed: overallPassed,
    error: null,
    from_cache: false,
    fix_suggestion: null,
    steps: stepResults,
  };
}

// ---------------------------------------------------------------------------
// Runner
// ---------------------------------------------------------------------------

async function runScenario(
  model: string,
  scenario: TestScenario,
  sourcePath: string | null,
  sourceContent: string | null,
  sourceWarning: string | null,
  language: string,
  apiKey: string,
  timeout: number,
  cache: ResultCache | undefined,
  signal: AbortSignal | undefined,
): Promise<ScenarioResult> {
  const key = cacheKey(scenario, sourceContent, model);
  const cached = cache?.get(key);
  if (cached) {
    return { ...cached, from_cache: true };
  }

  const { provider, modelName } = resolveProvider(model);

  const messages: LlmMessage[] = [
    { role: 'system', content: buildSystemPrompt() },
    { role: 'user', content: buildUserMessage(scenario, sourcePath, sourceContent, sourceWarning, language) },
  ];

  try {
    const response = await provider.call(messages, modelName, apiKey, timeout, signal);
    const parsed = parseLlmResponse(response.content);
    const result = buildScenarioResult(scenario, response.content, parsed);
    // only real answers go in the cache: errors are retried next time
    if (!result.error && sourceContent !== null) { cache?.set(key, result); }
    return result;
  } catch (err) {
    if (err instanceof CancelledError) { throw err; }
    return {
      name: scenario.name ?? 'unnamed',
      overall_passed: false,
      error: fill(SPEC.results.llmError, { error: err instanceof Error ? err.message : String(err) }),
      from_cache: false,
      fix_suggestion: null,
      steps: [],
    };
  }
}

async function runCtxFile(
  ctxPath: string,
  options: NativeRunOptions,
  onScenarioDone: () => void,
): Promise<FileResult> {
  const { model, apiKey } = options;
  const failFast = options.failFast ?? false;
  const timeout = options.timeout ?? 60000;
  let ctx: Record<string, unknown>;
  try {
    ctx = loadCtx(ctxPath);
  } catch (err) {
    return {
      ctx_path: ctxPath,
      source_path: null,
      skipped: false,
      error: String(err),
      scenarios: [],
    };
  }

  const conceptualTests = ctx.conceptualTests as TestScenario[] | undefined;
  if (!conceptualTests || conceptualTests.length === 0) {
    return {
      ctx_path: ctxPath,
      source_path: null,
      skipped: true,
      error: null,
      scenarios: [],
    };
  }

  const { sourcePath, sourceContent, warning } = resolveSource(ctxPath);
  const language = detectLanguage(sourcePath);

  const scenarios: ScenarioResult[] = [];
  for (const scenario of conceptualTests) {
    const result = await runScenario(
      model, scenario, sourcePath, sourceContent, warning, language, apiKey, timeout,
      options.cache, options.signal
    );
    scenarios.push(result);
    onScenarioDone();
    if (failFast && !result.overall_passed) {
      break;
    }
  }

  return {
    ctx_path: ctxPath,
    source_path: sourcePath,
    skipped: false,
    error: null,
    scenarios,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface NativeRunOptions {
  model: string;
  apiKey: string;
  failFast?: boolean;
  timeout?: number;
  cache?: ResultCache;
  signal?: AbortSignal;
  onProgress?: (done: number, total: number) => void;
}

export interface RunPlan {
  files: number;
  scenarios: number;
  cached: number;   // scenarios with a cached result for this model
  llmCalls: number; // scenarios that will call the model
}

/** What a run would do, before doing it: how many scenarios, how many already cached. */
export function planRun(targetPath: string, model: string, cache?: ResultCache): RunPlan {
  const plan: RunPlan = { files: 0, scenarios: 0, cached: 0, llmCalls: 0 };
  for (const ctxPath of collectCtxFiles(targetPath)) {
    let tests: TestScenario[] | undefined;
    try {
      tests = loadCtx(ctxPath).conceptualTests as TestScenario[] | undefined;
    } catch {
      continue;
    }
    if (!tests || tests.length === 0) { continue; }
    plan.files++;
    const { sourceContent } = resolveSource(ctxPath);
    for (const scenario of tests) {
      plan.scenarios++;
      if (cache?.has(cacheKey(scenario, sourceContent, model))) { plan.cached++; } else { plan.llmCalls++; }
    }
  }
  return plan;
}

/**
 * Run conceptual tests natively (no Python/CLI dependency).
 * Drop-in replacement for the CLI-based runCtxTests.
 */
export async function runCtxTestsNative(
  targetPath: string,
  options: NativeRunOptions,
): Promise<RunResult> {
  const ctxFiles = collectCtxFiles(targetPath);
  const total = planRun(targetPath, options.model).scenarios;
  let done = 0;
  const tick = (): void => { done++; options.onProgress?.(done, total); };

  const results: FileResult[] = [];
  let cancelled = false;
  try {
    for (const ctxPath of ctxFiles) {
      const result = await runCtxFile(ctxPath, options, tick);
      results.push(result);
      if (options.failFast && result.scenarios.some((s) => !s.overall_passed)) {
        break;
      }
    }
  } catch (err) {
    if (!(err instanceof CancelledError)) { throw err; }
    cancelled = true;
  } finally {
    options.cache?.save();
  }

  // Build summary
  const filesRun = results.filter((r) => !r.skipped && !r.error).length;
  const scenariosTotal = results.reduce((n, r) => n + r.scenarios.length, 0);
  const stepsPassed = results.reduce(
    (n, r) => n + r.scenarios.reduce((m, s) => m + s.steps.filter((st) => st.passed).length, 0),
    0
  );
  const stepsTotal = results.reduce(
    (n, r) => n + r.scenarios.reduce((m, s) => m + s.steps.length, 0),
    0
  );
  const failedScenarios = results.reduce(
    (n, r) => n + r.scenarios.filter((s) => !s.overall_passed).length,
    0
  );

  return {
    cancelled,
    summary: {
      files: filesRun,
      scenarios: scenariosTotal,
      steps_passed: stepsPassed,
      steps_total: stepsTotal,
      failed_scenarios: failedScenarios,
    },
    results,
  };
}
