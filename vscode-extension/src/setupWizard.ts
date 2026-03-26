/**
 * First-run Setup Wizard.
 * Walks the user through: provider → model → API key.
 * Stores config in VS Code settings, API key in SecretStorage.
 */

import * as vscode from 'vscode';

interface ProviderOption {
  label: string;
  id: string;
  models: string[];
  needsKey: boolean;
  envVar?: string;
}

const PROVIDER_OPTIONS: ProviderOption[] = [
  {
    label: 'OpenAI',
    id: 'openai',
    models: ['gpt-4o-mini', 'gpt-4o', 'gpt-4-turbo', 'o3-mini'],
    needsKey: true,
    envVar: 'OPENAI_API_KEY',
  },
  {
    label: 'Anthropic',
    id: 'anthropic',
    models: ['claude-haiku-20240307', 'claude-sonnet-4-20250514', 'claude-opus-4-20250514'],
    needsKey: true,
    envVar: 'ANTHROPIC_API_KEY',
  },
  {
    label: 'Ollama (local)',
    id: 'ollama',
    models: ['ollama/llama3', 'ollama/mistral', 'ollama/codellama', 'ollama/gemma2'],
    needsKey: false,
  },
  {
    label: 'OpenRouter',
    id: 'openrouter',
    models: ['openrouter/auto', 'openrouter/google/gemini-pro', 'openrouter/meta-llama/llama-3-70b-instruct'],
    needsKey: true,
    envVar: 'OPENROUTER_API_KEY',
  },
];

/**
 * Check if ContextDoc is configured. Returns true if model is set.
 */
export function isConfigured(): boolean {
  const config = vscode.workspace.getConfiguration('contextdoc');
  const model = config.get<string>('model', '');
  return model.length > 0;
}

/**
 * Run the setup wizard. Returns true if setup was completed.
 */
export async function runSetupWizard(secrets: vscode.SecretStorage): Promise<boolean> {
  // Step 1: Pick provider
  const providerPick = await vscode.window.showQuickPick(
    PROVIDER_OPTIONS.map((p) => ({
      label: p.label,
      description: p.needsKey ? 'API key required' : 'No API key needed',
      provider: p,
    })),
    {
      title: 'ContextDoc Setup (1/3): Choose LLM Provider',
      placeHolder: 'Which LLM provider do you want to use?',
    }
  );

  if (!providerPick) { return false; }
  const provider = providerPick.provider;

  // Step 2: Pick or type model
  const modelItems = provider.models.map((m) => ({ label: m }));
  modelItems.push({ label: '$(edit) Custom model...' });

  const modelPick = await vscode.window.showQuickPick(modelItems, {
    title: `ContextDoc Setup (2/3): Choose Model (${provider.label})`,
    placeHolder: 'Select a model or enter a custom one',
  });

  if (!modelPick) { return false; }

  let model: string;
  if (modelPick.label.includes('Custom')) {
    const custom = await vscode.window.showInputBox({
      title: 'ContextDoc Setup (2/3): Custom Model',
      prompt: 'Enter the model identifier (e.g. gpt-4o-mini, claude-haiku-20240307)',
      placeHolder: 'model-name',
    });
    if (!custom) { return false; }
    model = custom;
  } else {
    model = modelPick.label;
  }

  // Step 3: API key (if needed)
  if (provider.needsKey) {
    // Check env var first
    const envVal = provider.envVar ? process.env[provider.envVar] : undefined;
    if (envVal) {
      const useEnv = await vscode.window.showQuickPick(
        [
          { label: `Use $${provider.envVar}`, description: 'Already set in your environment', useEnv: true },
          { label: 'Enter a different key', description: 'Store securely in VS Code', useEnv: false },
        ],
        {
          title: `ContextDoc Setup (3/3): API Key (${provider.label})`,
        }
      );

      if (!useEnv) { return false; }

      if (!useEnv.useEnv) {
        const key = await askForApiKey(provider);
        if (!key) { return false; }
        await secrets.store(`contextdoc.apiKey.${provider.id}`, key);
      }
      // If useEnv, the key will be picked up from env at runtime
    } else {
      const key = await askForApiKey(provider);
      if (!key) { return false; }
      await secrets.store(`contextdoc.apiKey.${provider.id}`, key);
    }
  }

  // Save model to settings
  const config = vscode.workspace.getConfiguration('contextdoc');
  await config.update('model', model, vscode.ConfigurationTarget.Global);

  vscode.window.showInformationMessage(
    `ContextDoc configured! Provider: ${provider.label}, Model: ${model}`
  );

  return true;
}

async function askForApiKey(provider: ProviderOption): Promise<string | undefined> {
  return vscode.window.showInputBox({
    title: `ContextDoc Setup (3/3): API Key (${provider.label})`,
    prompt: `Enter your ${provider.label} API key`,
    placeHolder: provider.envVar ? `Or set $${provider.envVar} in your shell` : 'API key',
    password: true,
    validateInput: (value) => {
      if (!value.trim()) { return 'API key cannot be empty'; }
      return null;
    },
  });
}
