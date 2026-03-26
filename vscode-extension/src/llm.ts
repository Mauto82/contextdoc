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
  call(messages: LlmMessage[], model: string, apiKey: string, timeout?: number): Promise<LlmResponse>;
}

// ---------------------------------------------------------------------------
// HTTP helper
// ---------------------------------------------------------------------------

function httpRequest(
  url: string,
  body: string,
  headers: Record<string, string>,
  timeoutMs: number = 60000
): Promise<string> {
  return new Promise((resolve, reject) => {
    const parsed = new URL(url);
    const isHttps = parsed.protocol === 'https:';
    const lib = isHttps ? https : http;

    const req = lib.request(
      {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? 443 : 80),
        path: parsed.pathname + parsed.search,
        method: 'POST',
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

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`Request timed out after ${timeoutMs}ms`));
    });

    req.write(body);
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
    timeout: number = 60000
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
      max_tokens: 1500,
    });

    const raw = await httpRequest(url, body, headers, timeout);
    const parsed = JSON.parse(raw);
    const content = parsed?.choices?.[0]?.message?.content ?? '';
    return { content };
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
    timeout: number = 60000
  ): Promise<LlmResponse> {
    const url = 'https://api.anthropic.com/v1/messages';

    // Anthropic API: system is separate, not in messages array
    const systemMsg = messages.find((m) => m.role === 'system');
    const nonSystem = messages.filter((m) => m.role !== 'system');

    const body = JSON.stringify({
      model,
      max_tokens: 1500,
      temperature: 0,
      ...(systemMsg ? { system: systemMsg.content } : {}),
      messages: nonSystem.map((m) => ({ role: m.role, content: m.content })),
    });

    const headers: Record<string, string> = {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
    };

    const raw = await httpRequest(url, body, headers, timeout);
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
  ollama: new OpenAIProvider('http://localhost:11434/v1', 'ollama', 'Ollama (local)'),
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
