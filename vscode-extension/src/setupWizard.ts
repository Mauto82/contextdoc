/**
 * Setup wizard: where the model runs → which model → API key (cloud providers only) → test call.
 * The two recommended defaults come first: gemma4 on Ollama's cloud (nothing runs on this
 * machine) and gemma4:e2b locally (the lightest gemma4, ~4.6 GB). Installed Ollama models are
 * listed with their size, and the ones too heavy for this machine's RAM are flagged.
 * The model goes in the settings, the API key in VS Code's SecretStorage.
 */

import * as vscode from 'vscode';
import * as http from 'http';
import * as os from 'os';
import {
  listOllamaModels, isHeavyForThisMachine, formatGB, resolveProvider, getApiKey, OLLAMA_URL,
} from './llm';

export const DEFAULT_CLOUD_MODEL = 'ollama/gemma4:cloud';
export const DEFAULT_LOCAL_MODEL = 'ollama/gemma4:e2b';

interface CloudProvider {
  label: string;
  id: string;
  models: Array<{ id: string; note: string }>;
  envVar: string;
}

const CLOUD_PROVIDERS: CloudProvider[] = [
  {
    label: 'Anthropic',
    id: 'anthropic',
    models: [
      { id: 'claude-haiku-5-5', note: 'cheapest, recommended' },
      { id: 'claude-sonnet-5-5', note: 'more accurate, costs more' },
      { id: 'claude-opus-5-5', note: 'most expensive' },
    ],
    envVar: 'ANTHROPIC_API_KEY',
  },
  {
    label: 'OpenAI',
    id: 'openai',
    models: [
      { id: 'gpt-4o-mini', note: 'cheap' },
      { id: 'gpt-4o', note: 'costs more' },
    ],
    envVar: 'OPENAI_API_KEY',
  },
  {
    label: 'OpenRouter',
    id: 'openrouter',
    models: [{ id: 'openrouter/auto', note: 'OpenRouter picks the model; cost varies' }],
    envVar: 'OPENROUTER_API_KEY',
  },
];

type WhereItem = vscode.QuickPickItem & { action: 'default-cloud' | 'default-local' | 'ollama' | 'cloud' };

export function isConfigured(): boolean {
  return vscode.workspace.getConfiguration('contextdoc').get<string>('model', '').length > 0;
}

export async function runSetupWizard(secrets: vscode.SecretStorage): Promise<boolean> {
  // Step 1: where the model runs
  const where = await vscode.window.showQuickPick<WhereItem>(
    [
      {
        label: '$(cloud) gemma4 on Ollama cloud',
        description: 'recommended',
        detail: `${DEFAULT_CLOUD_MODEL} — runs on Ollama's servers, nothing heavy on this machine. Free tier with usage limits; needs Ollama installed and \`ollama signin\`.`,
        action: 'default-cloud',
      },
      {
        label: '$(device-desktop) gemma4:e2b on this machine',
        description: 'recommended for offline use',
        detail: `${DEFAULT_LOCAL_MODEL} — the lightest gemma4 (~4.6 GB download). Free, private, uses your CPU/GPU and RAM.`,
        action: 'default-local',
      },
      { label: '', kind: vscode.QuickPickItemKind.Separator, action: 'ollama' },
      {
        label: '$(server) Another Ollama model',
        detail: 'Pick from the models installed in Ollama (sizes and RAM warnings shown).',
        action: 'ollama',
      },
      {
        label: '$(key) A paid API (Anthropic, OpenAI, OpenRouter)',
        detail: 'Billed per call by the provider; needs an API key. Results are cached to keep costs down.',
        action: 'cloud',
      },
    ],
    { title: 'ContextDoc Setup (1/3): Where should the model run?', ignoreFocusOut: true }
  );
  if (!where) { return false; }

  let model: string | undefined;
  if (where.action === 'default-cloud' || where.action === 'default-local') {
    model = where.action === 'default-cloud' ? DEFAULT_CLOUD_MODEL : DEFAULT_LOCAL_MODEL;
    if (!(await ensureOllamaModel(model.slice('ollama/'.length)))) { return false; }
  } else if (where.action === 'ollama') {
    model = await pickOllamaModel();
  } else {
    model = await pickCloudModel(secrets);
  }
  if (!model) { return false; }

  // Step 3: a tiny test call, so a wrong key or model shows up now and not at the first test
  if (!(await testModel(model, secrets))) { return false; }

  await vscode.workspace.getConfiguration('contextdoc').update('model', model, vscode.ConfigurationTarget.Global);
  vscode.window.showInformationMessage(`ContextDoc: using ${model}. Change it any time from the status bar.`);
  return true;
}

// ---------------------------------------------------------------------------
// Ollama
// ---------------------------------------------------------------------------

async function ollamaNotRunning(): Promise<'retry' | 'cancel'> {
  const choice = await vscode.window.showWarningMessage(
    'ContextDoc: Ollama is not running on this machine. Install it from ollama.com and start it, then retry.',
    { modal: true },
    'Retry',
    'Open ollama.com'
  );
  if (choice === 'Open ollama.com') { vscode.env.openExternal(vscode.Uri.parse('https://ollama.com/download')); }
  return choice === 'Retry' ? 'retry' : 'cancel';
}

/** Makes sure an Ollama model is installed, offering to download it (with progress, cancellable). */
async function ensureOllamaModel(name: string): Promise<boolean> {
  for (;;) {
    const models = await listOllamaModels();
    if (models === null) {
      if ((await ollamaNotRunning()) === 'retry') { continue; }
      return false;
    }
    if (models.some((m) => m.name === name || m.name === `${name}:latest`)) { return true; }
    break;
  }

  const cloud = /[:-]cloud$/.test(name);
  const ok = await vscode.window.showInformationMessage(
    cloud
      ? `ContextDoc: ${name} isn't set up in Ollama yet. Add it now? It only registers the cloud model (no big download); you need to be signed in with \`ollama signin\`.`
      : `ContextDoc: ${name} isn't installed. Download it now (~4.6 GB)?`,
    { modal: true },
    'Download'
  );
  if (ok !== 'Download') { return false; }

  return vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Ollama: pulling ${name}`, cancellable: true },
    (progress, token) => pullOllamaModel(name, progress, token)
  );
}

function pullOllamaModel(
  name: string,
  progress: vscode.Progress<{ message?: string; increment?: number }>,
  token: vscode.CancellationToken,
): Promise<boolean> {
  return new Promise((resolve) => {
    let lastPct = 0;
    let buffer = '';
    let failed = false;
    const req = http.request(`${OLLAMA_URL}/api/pull`, { method: 'POST', headers: { 'Content-Type': 'application/json' } }, (res) => {
      res.on('data', (chunk: Buffer) => {
        buffer += chunk.toString('utf-8');
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.trim()) { continue; }
          try {
            const ev = JSON.parse(line);
            if (ev.error) {
              failed = true;
              vscode.window.showErrorMessage(`Ollama: ${ev.error}`);
            } else if (ev.total && ev.completed) {
              const pct = Math.floor((ev.completed / ev.total) * 100);
              progress.report({ message: `${ev.status} ${pct}%`, increment: Math.max(0, pct - lastPct) });
              lastPct = pct;
            } else if (ev.status) {
              progress.report({ message: ev.status });
            }
          } catch {
            // partial line: wait for the rest
          }
        }
      });
      res.on('end', () => resolve(!failed && !token.isCancellationRequested));
    });
    req.on('error', (err) => {
      if (!token.isCancellationRequested) { vscode.window.showErrorMessage(`Ollama: ${err.message}`); }
      resolve(false);
    });
    token.onCancellationRequested(() => req.destroy());
    req.write(JSON.stringify({ model: name, stream: true }));
    req.end();
  });
}

async function pickOllamaModel(): Promise<string | undefined> {
  for (;;) {
    const models = await listOllamaModels();
    if (models === null) {
      if ((await ollamaNotRunning()) === 'retry') { continue; }
      return undefined;
    }
    const ram = os.totalmem();
    const usable = models.filter((m) => !m.embedding);
    if (usable.length === 0) {
      vscode.window.showWarningMessage('ContextDoc: no chat models installed in Ollama. Choose one of the gemma4 defaults to download it.');
      return undefined;
    }
    // light local models first, then cloud ones, heavy ones last
    const rank = (m: typeof usable[number]): number => (isHeavyForThisMachine(m, ram) ? 2 : m.cloud ? 1 : 0);
    usable.sort((a, b) => rank(a) - rank(b) || a.sizeBytes - b.sizeBytes);

    const pick = await vscode.window.showQuickPick(
      usable.map((m) => ({
        label: (isHeavyForThisMachine(m, ram) ? '$(warning) ' : m.cloud ? '$(cloud) ' : '$(device-desktop) ') + m.name,
        description: m.cloud ? 'Ollama cloud' : formatGB(m.sizeBytes),
        detail: isHeavyForThisMachine(m, ram)
          ? `Heavy for this machine: ${formatGB(m.sizeBytes)} with ${formatGB(ram)} of RAM. It may slow everything down.`
          : m.cloud ? 'Runs on Ollama\'s servers, with your account\'s usage limits.' : 'Runs on this machine.',
        model: `ollama/${m.name}`,
        heavy: isHeavyForThisMachine(m, ram),
      })),
      { title: 'ContextDoc Setup (2/3): Choose an Ollama model', ignoreFocusOut: true }
    );
    if (!pick) { return undefined; }
    if (pick.heavy) {
      const go = await vscode.window.showWarningMessage(
        `${pick.model} needs about ${pick.description} of memory on a machine with ${formatGB(ram)}. Tests may freeze your computer while they run.`,
        { modal: true },
        'Use it anyway',
        'Choose another'
      );
      if (go === 'Choose another') { continue; }
      if (go !== 'Use it anyway') { return undefined; }
    }
    return pick.model;
  }
}

// ---------------------------------------------------------------------------
// Paid APIs
// ---------------------------------------------------------------------------

async function pickCloudModel(secrets: vscode.SecretStorage): Promise<string | undefined> {
  const provider = await vscode.window.showQuickPick(
    CLOUD_PROVIDERS.map((p) => ({ label: p.label, provider: p })),
    { title: 'ContextDoc Setup (2/3): Choose the API provider', ignoreFocusOut: true }
  );
  if (!provider) { return undefined; }
  const p = provider.provider;

  const items = p.models.map((m) => ({ label: m.id, description: m.note }));
  items.push({ label: '$(edit) Custom model…', description: 'type a model id' });
  const pick = await vscode.window.showQuickPick(items, {
    title: `ContextDoc Setup (2/3): Choose a ${p.label} model`,
    ignoreFocusOut: true,
  });
  if (!pick) { return undefined; }

  let model = pick.label;
  if (pick.label.includes('Custom')) {
    const custom = await vscode.window.showInputBox({
      title: `ContextDoc Setup (2/3): ${p.label} model id`,
      placeHolder: p.models[0].id,
      ignoreFocusOut: true,
    });
    if (!custom) { return undefined; }
    model = p.id === 'openrouter' && !custom.startsWith('openrouter/') ? `openrouter/${custom}` : custom;
  }

  // API key: from the environment if present, otherwise stored in SecretStorage
  if (!process.env[p.envVar]) {
    const key = await vscode.window.showInputBox({
      title: `ContextDoc Setup: ${p.label} API key`,
      prompt: `Stored in VS Code's SecretStorage. Calls are billed to this key by ${p.label}.`,
      placeHolder: `or set $${p.envVar} in your shell`,
      password: true,
      ignoreFocusOut: true,
      validateInput: (v) => (v.trim() ? null : 'API key cannot be empty'),
    });
    if (!key) { return undefined; }
    await secrets.store(`contextdoc.apiKey.${p.id}`, key.trim());
  }
  return model;
}

// ---------------------------------------------------------------------------
// Test call
// ---------------------------------------------------------------------------

async function testModel(model: string, secrets: vscode.SecretStorage): Promise<boolean> {
  const { provider, modelName } = resolveProvider(model);
  const apiKey = (await secrets.get(`contextdoc.apiKey.${provider.id}`)) ?? getApiKey(provider.id);

  for (;;) {
    const error = await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `ContextDoc Setup (3/3): testing ${model}…`, cancellable: true },
      async (_p, token) => {
        const abort = new AbortController();
        token.onCancellationRequested(() => abort.abort());
        try {
          await provider.call([{ role: 'user', content: 'Reply with the single word OK.' }], modelName, apiKey, 120000, abort.signal);
          return null;
        } catch (err) {
          return err instanceof Error ? err.message : String(err);
        }
      }
    );
    if (error === null) { return true; }
    if (error === 'Cancelled') { return false; }
    const choice = await vscode.window.showErrorMessage(
      `ContextDoc: ${model} didn't answer: ${error.slice(0, 300)}`,
      { modal: true },
      'Retry',
      'Save anyway'
    );
    if (choice === 'Save anyway') { return true; }
    if (choice !== 'Retry') { return false; }
  }
}
