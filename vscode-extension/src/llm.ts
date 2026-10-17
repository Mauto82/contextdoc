/**
 * Multi-provider LLM client.
 * Supports OpenAI-compatible APIs (OpenAI, Ollama, etc.) and Anthropic natively.
 * No Python dependency — pure HTTP calls.
 */

import * as https from 'https';
import * as http from 'http';
import { URL } from 'url';

export interface LlmMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface LlmResponse {
  content: string;
}

export interface LlmProvider {
  id: string;
  name: string;
  call(messages: LlmMessage[], model: string, apiKey: string, timeout?: number, signal?: AbortSignal): Promise<LlmResponse>;
}

export const OLLAMA_URL = 'http://localhost:11434';

export class CancelledError extends Error {
  constructor() {
    super('Cancelled');
    this.name = 'CancelledError';
  }
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

function httpRequest(
  url: string,
  body: string | null,
  headers: Record<string, string>,
  timeoutMs: number = 60000,
  signal?: AbortSignal
): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new CancelledError());
      return;
    }
    const parsed = new URL(url);
    const isHttps = parsed.protocol === 'https:';
    const lib = isHttps ? https : http;

    const req = lib.request(
      {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: body === null ? 'GET' : 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        timeout: timeoutMs,
      },
      (res) => {
        const chunks: Buffer[] = [];
        res.on('data', (chunk: Buffer) => chunks.push(chunk));
        res.on('end', () => {
          const data = Buffer.concat(chunks).toString('utf-8');
          if (res.statusCode && res.statusCode >= 400) {
            reject(new Error(`HTTP ${res.statusCode}: ${data.slice(0, 500)}`));
          } else {
            resolve(data);
          }
        });
      }
    );

    // cancelling a run aborts the request in flight, so a slow local model stops working too
    const onAbort = (): void => {
      req.destroy();
      reject(new CancelledError());
    };
    signal?.addEventListener('abort', onAbort, { once: true });
    req.on('close', () => signal?.removeEventListener('abort', onAbort));

    req.on('error', (err) => reject(signal?.aborted ? new CancelledError() : err));
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`));
    });

    if (body !== null) { req.write(body); }
    req.end();
  });
}

// ---------------------------------------------------------------------------
// OpenAI-compatible provider (works for OpenAI, Ollama, OpenRouter, etc.)
// ---------------------------------------------------------------------------

export class OpenAIProvider implements LlmProvider {
  id = 'openai';
  name = 'OpenAI-compatible';

  constructor(
    private baseUrl: string = 'https://api.openai.com/v1',
    id?: string,
    name?: string
  ) {
    if (id) { this.id = id; }
    if (name) { this.name = name; }
  }

  async call(
    messages: LlmMessage[],
    model: string,
    apiKey: string,
    timeout: number = 60000,
    signal?: AbortSignal
  ): Promise<LlmResponse> {
    const url = `${this.baseUrl}/chat/completions`;
    const headers: Record<string, string> = {};
    if (apiKey) {
      headers['Authorization'] = `Bearer ${apiKey}`;
    }

    const body = JSON.stringify({
      model,
      messages,
      temperature: 0,
      // room for reasoning models, whose thinking counts against the limit
      max_tokens: 4096,
    });

    const raw = await httpRequest(url, body, headers, timeout, signal);
    const parsed = JSON.parse(raw);
    const content = parsed?.choices?.[0]?.message?.content ?? '';
    return { content };
  }
}

// ---------------------------------------------------------------------------
// Ollama provider: native /api/chat, so the context window can be sized to the prompt.
// Through the OpenAI-compatible endpoint Ollama reserves the model's full context
// (gemma4:12b took 16 GB of RAM instead of ~9), which is what froze machines.
// ---------------------------------------------------------------------------

/** Context window for a prompt: room for the prompt plus the answer, rounded up to a power of two. */
export function contextFor(messages: LlmMessage[]): number {
  const chars = messages.reduce((n, m) => n + m.content.length, 0);
  const needed = Math.ceil(chars / 3) + 4096; // ~3 characters per token, plus the answer
  let ctx = 8192;
  while (ctx < needed && ctx < 131072) { ctx *= 2; }
  return ctx;
}

export class OllamaProvider implements LlmProvider {
  id = 'ollama';
  name = 'Ollama';

  async call(
    messages: LlmMessage[],
    model: string,
    _apiKey: string,
    timeout: number = 60000,
    signal?: AbortSignal
  ): Promise<LlmResponse> {
    const body = JSON.stringify({
      model,
      messages,
      stream: false,
      options: { temperature: 0, num_ctx: contextFor(messages), num_predict: 4096 },
    });
    const raw = await httpRequest(`${OLLAMA_URL}/api/chat`, body, {}, timeout, signal);
    const parsed = JSON.parse(raw);
    return { content: parsed?.message?.content ?? '' };
  }
}

/** Memory taken by the Ollama models loaded right now (from /api/ps), by name. */
export async function loadedOllamaModels(): Promise<Map<string, number>> {
  try {
    const raw = await httpRequest(`${OLLAMA_URL}/api/ps`, null, {}, 3000);
    const models = (JSON.parse(raw)?.models ?? []) as Array<{ name: string; size?: number }>;
    return new Map(models.map((m) => [m.name, m.size ?? 0]));
  } catch {
    return new Map();
  }
}

// ---------------------------------------------------------------------------
// Anthropic provider
// ---------------------------------------------------------------------------

export class AnthropicProvider implements LlmProvider {
  id = 'anthropic';
  name = 'Anthropic';

  async call(
    messages: LlmMessage[],
    model: string,
    apiKey: string,
    timeout: number = 60000,
    signal?: AbortSignal
  ): Promise<LlmResponse> {
    const url = 'https://api.anthropic.com/v1/messages';

    // Anthropic API: system is separate, not in messages array
    const systemMsg = messages.find((m) => m.role === 'system');
    const nonSystem = messages.filter((m) => m.role !== 'system');

    const body = JSON.stringify({
      model,
      max_tokens: 4096,
      temperature: 0,
      ...(systemMsg ? { system: systemMsg.content } : {}),
      messages: nonSystem.map((m) => ({ role: m.role, content: m.content })),
    });

    const headers: Record<string, string> = {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    };

    const raw = await httpRequest(url, body, headers, timeout, signal);
    const parsed = JSON.parse(raw);
    const content = parsed?.content?.[0]?.text ?? '';
    return { content };
  }
}

// ---------------------------------------------------------------------------
// Provider registry
// ---------------------------------------------------------------------------

export const PROVIDERS: Record<string, LlmProvider> = {
  openai: new OpenAIProvider('https://api.openai.com/v1', 'openai', 'OpenAI'),
  anthropic: new AnthropicProvider(),
  ollama: new OllamaProvider(),
  openrouter: new OpenAIProvider('https://openrouter.ai/api/v1', 'openrouter', 'OpenRouter'),
};

/**
 * Resolve provider from a model string.
 * Supports prefixed format: "ollama/llama3", "anthropic/claude-..."
 * Or auto-detect from model name.
 */
export function resolveProvider(model: string): { provider: LlmProvider; modelName: string } {
  // Explicit prefix: "provider/model"
  const slashIdx = model.indexOf('/');
  if (slashIdx > 0) {
    const prefix = model.substring(0, slashIdx).toLowerCase();
    const modelName = model.substring(slashIdx + 1);
    const provider = PROVIDERS[prefix];
    if (provider) {
      // OpenRouter ids are "vendor/model" or "openrouter/<router>" (e.g. openrouter/auto):
      // keep the prefix when it is part of the id
      if (prefix === 'openrouter' && !modelName.includes('/')) {
        return { provider, modelName: model };
      }
      return { provider, modelName };
    }
  }

  // Auto-detect from model name
  if (model.startsWith('claude-')) {
    return { provider: PROVIDERS.anthropic, modelName: model };
  }
  if (model.startsWith('gpt-') || model.startsWith('o1-') || model.startsWith('o3-')) {
    return { provider: PROVIDERS.openai, modelName: model };
  }

  // Default to OpenAI-compatible
  return { provider: PROVIDERS.openai, modelName: model };
}

/**
 * Get the API key for a provider from VS Code settings or env vars.
 */
export function getApiKey(providerId: string, secrets?: Record<string, string>): string {
  // Check secrets store first (from setup wizard)
  if (secrets?.[`contextdoc.apiKey.${providerId}`]) {
    return secrets[`contextdoc.apiKey.${providerId}`];
  }

  // Fall back to environment variables
  const envMap: Record<string, string[]> = {
    openai: ['OPENAI_API_KEY'],
    anthropic: ['ANTHROPIC_API_KEY'],
    openrouter: ['OPENROUTER_API_KEY'],
    ollama: [], // no key needed
  };

  for (const envVar of envMap[providerId] ?? []) {
    const val = process.env[envVar];
    if (val) { return val; }
  }

  return '';
}

// ---------------------------------------------------------------------------
// Ollama: installed models and where they run
// ---------------------------------------------------------------------------

export interface OllamaModel {
  name: string;
  sizeBytes: number;
  cloud: boolean;     // runs on Ollama's servers (":cloud" models), not on this machine
  embedding: boolean; // embedding models can't answer prompts
}

/** Models installed in the local Ollama, or null when Ollama isn't reachable. */
export async function listOllamaModels(timeoutMs: number = 3000): Promise<OllamaModel[] | null> {
  try {
    const raw = await httpRequest(`${OLLAMA_URL}/api/tags`, null, {}, timeoutMs);
    const models = (JSON.parse(raw)?.models ?? []) as Array<{ name: string; size?: number }>;
    return models.map((m) => ({
      name: m.name,
      sizeBytes: m.size ?? 0,
      cloud: /[:-]cloud$/.test(m.name) || (m.size ?? 0) < 1e6,
      embedding: /embed/i.test(m.name),
    }));
  } catch {
    return null;
  }
}

/** RAM a local model takes once loaded with ContextDoc's context size: about its download size plus 20%
 *  (measured: gemma4:e2b, 7.5 GB download, 8.7 GB loaded). */
export function estimatedRamBytes(model: OllamaModel): number {
  return model.cloud ? 0 : model.sizeBytes * 1.2;
}

/** "heavy" when a local model would take more than half of this machine's RAM. */
export function isHeavyForThisMachine(model: OllamaModel, totalMemBytes: number): boolean {
  return estimatedRamBytes(model) > totalMemBytes * 0.5;
}

export function formatGB(bytes: number): string {
  return `${(bytes / 1e9).toFixed(1)} GB`;
}

/** A machine's RAM as it is sold: 8, 16, 18 GB (binary gigabytes, rounded). */
export function formatRam(bytes: number): string {
  return `${Math.round(bytes / 1024 ** 3)} GB`;
}
