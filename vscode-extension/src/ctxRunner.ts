/**
 * Native TypeScript ctx-run: parses .ctx YAML, runs conceptual tests via LLM.
 * Replaces the Python ctx-run CLI for the VS Code extension.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as yaml from 'yaml';
import { resolveProvider, getApiKey, LlmMessage } from './llm';
import { RunResult, FileResult, ScenarioResult, StepResult } from './runner';

// ---------------------------------------------------------------------------
// Language map
// ---------------------------------------------------------------------------

const LANG_MAP: Record<string, string> = {
  '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
  '.go': 'go', '.rb': 'ruby', '.rs': 'rust', '.java': 'java',
  '.cs': 'csharp', '.php': 'php', '.swift': 'swift', '.kt': 'kotlin',
};

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
// Prompt construction (mirrors ctx_run.py exactly)
// ---------------------------------------------------------------------------

function buildSystemPrompt(): string {
  return (
    'You are a code behavior analyzer. ' +
    'Your job is to reason about whether source code correctly implements described behaviors — ' +
    'without executing the code.\n\n' +
    'You will be given source code and a test scenario with sequential steps (action + expected outcome). ' +
    'For each step, reason about whether the source code, as written, would produce the expected outcome.\n\n' +
    'Respond with valid JSON only. No explanation outside the JSON object. No markdown fences.'
  );
}

interface TestStep {
  action?: string;
  expect?: string;
}

interface TestScenario {
  name?: string;
  steps?: TestStep[];
}

function buildUserMessage(
  scenario: TestScenario,
  sourcePath: string | null,
  sourceContent: string | null,
  sourceWarning: string | null,
  language: string,
): string {
  const parts: string[] = [];

  if (sourceContent) {
    const label = sourcePath ?? 'unknown';
    const fence = language ? '```' + language : '```';
    parts.push(`Source file: ${label}\n${fence}\n${sourceContent}\n\`\`\``);
  } else {
    const note = sourceWarning ?? 'source file unavailable';
    parts.push(`Source file: NOT AVAILABLE (${note})`);
    parts.push(
      'Note: since source is unavailable, mark all steps as failed ' +
      "with explanation 'source code not available for analysis'."
    );
  }

  const name = scenario.name ?? 'unnamed';
  const steps = scenario.steps ?? [];
  parts.push(`\nScenario: "${name}"`);
  parts.push('Steps:');
  steps.forEach((step, i) => {
    parts.push(
      `${i + 1}. action: "${step.action ?? ''}"\n` +
      `   expect: "${step.expect ?? ''}"`
    );
  });

  parts.push(
    '\nFor each step, evaluate whether the source code produces the expected outcome.\n\n' +
    'Respond with this exact JSON structure:\n' +
    '{\n' +
    '  "overall": true or false,\n' +
    '  "steps": [\n' +
    '    {\n' +
    '      "action": "the action text",\n' +
    '      "passed": true or false,\n' +
    '      "explanation": "one sentence, max 25 words"\n' +
    '    }\n' +
    '  ]\n' +
    '}\n\n' +
    'Rules:\n' +
    '- "overall" must be true only if ALL steps pass\n' +
    '- Include one entry per step, in the same order\n' +
    '- "explanation" is always required, even for passing steps\n' +
    '- Do not include any text outside the JSON object'
  );

  return parts.join('\n');
}

// ---------------------------------------------------------------------------
// Response parsing (3-layer like Python version)
// ---------------------------------------------------------------------------

function parseLlmResponse(raw: string): Record<string, unknown> | null {
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

function buildScenarioResult(
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
      error: `LLM response could not be parsed. Raw: ${rawResponse.slice(0, 200)}`,
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
        explanation: 'Step missing from LLM response',
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
  timeout: number = 60000,
): Promise<ScenarioResult> {
  const { provider, modelName } = resolveProvider(model);

  const messages: LlmMessage[] = [
    { role: 'system', content: buildSystemPrompt() },
    { role: 'user', content: buildUserMessage(scenario, sourcePath, sourceContent, sourceWarning, language) },
  ];

  try {
    const response = await provider.call(messages, modelName, apiKey, timeout);
    const parsed = parseLlmResponse(response.content);
    return buildScenarioResult(scenario, response.content, parsed);
  } catch (err) {
    return {
      name: scenario.name ?? 'unnamed',
      overall_passed: false,
      error: `LLM error: ${err instanceof Error ? err.message : String(err)}`,
      from_cache: false,
      fix_suggestion: null,
      steps: [],
    };
  }
}

async function runCtxFile(
  ctxPath: string,
  model: string,
  apiKey: string,
  failFast: boolean = false,
  timeout: number = 60000,
): Promise<FileResult> {
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
      model, scenario, sourcePath, sourceContent, warning, language, apiKey, timeout
    );
    scenarios.push(result);
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

  const results: FileResult[] = [];
  for (const ctxPath of ctxFiles) {
    const result = await runCtxFile(
      ctxPath,
      options.model,
      options.apiKey,
      options.failFast ?? false,
      options.timeout ?? 60000,
    );
    results.push(result);
    if (options.failFast && result.scenarios.some((s) => !s.overall_passed)) {
      break;
    }
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
