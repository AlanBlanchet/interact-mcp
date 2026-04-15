import * as vscode from "vscode";

const ENV_PREFIX = "INTERACT_MCP_";
const SETTING_SECTION = "interactMcp";

interface ProviderInfo {
  envKeys: string[];
  models: string[];
}

interface ModelsData {
  providers: Record<string, ProviderInfo>;
}

interface ModelSettingItem extends vscode.QuickPickItem {
  settingKey: string;
}

class KeyManager {
  private cache = new Map<string, string>();

  constructor(private secrets: vscode.SecretStorage) {}

  async loadAll(allEnvKeys: string[]): Promise<void> {
    for (const key of allEnvKeys) {
      const val = await this.secrets.get(key);
      if (val) this.cache.set(key, val);
    }
  }

  get(key: string): string | undefined {
    return this.cache.get(key);
  }

  async set(key: string, value: string): Promise<void> {
    await this.secrets.store(key, value);
    this.cache.set(key, value);
  }

  async remove(key: string): Promise<void> {
    await this.secrets.delete(key);
    this.cache.delete(key);
  }

  syncCache(key: string, value: string | undefined): void {
    if (value) this.cache.set(key, value);
    else this.cache.delete(key);
  }

  entries(): [string, string][] {
    return [...this.cache.entries()];
  }

  missingKeys(required: string[]): string[] {
    return required.filter((k) => !this.cache.has(k));
  }
}

function settingToEnv(key: string): string {
  return ENV_PREFIX + key.replace(/[A-Z]/g, (c) => "_" + c).toUpperCase();
}

function formatLabel(key: string): string {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

function buildEnv(
  settingKeys: string[],
  keyManager: KeyManager,
  allEnvKeys: Set<string>,
): Record<string, string> {
  const cfg = vscode.workspace.getConfiguration(SETTING_SECTION);
  const env: Record<string, string> = {};

  for (const [k, v] of Object.entries(process.env)) {
    if (v !== undefined && !allEnvKeys.has(k)) {
      env[k] = v;
    }
  }

  for (const key of settingKeys) {
    const value = cfg.get(key);
    if (value === undefined || value === null || value === "") continue;
    env[settingToEnv(key)] =
      typeof value === "boolean" ? (value ? "true" : "false") : String(value);
  }

  for (const [k, v] of keyManager.entries()) {
    env[k] = v;
  }

  return env;
}

function providerOf(
  model: string,
  modelsData: ModelsData,
): string | undefined {
  for (const [provider, info] of Object.entries(modelsData.providers)) {
    if (info.models.includes(model)) return provider;
  }
}

async function ensureKeys(
  provider: string,
  modelsData: ModelsData,
  keyManager: KeyManager,
  emitter: vscode.EventEmitter<void>,
): Promise<boolean> {
  const info = modelsData.providers[provider];
  if (!info) return true;
  const missing = keyManager.missingKeys(info.envKeys);
  for (const key of missing) {
    if (process.env[key]) {
      const use = await vscode.window.showInformationMessage(
        `Found ${key} in your environment. Use it?`,
        "Yes",
        "No",
      );
      if (use === "Yes") {
        await keyManager.set(key, process.env[key]!);
        emitter.fire();
        continue;
      }
    }
    const value = await vscode.window.showInputBox({
      prompt: `Enter your ${key}`,
      password: /KEY|SECRET|TOKEN/i.test(key),
      ignoreFocusOut: true,
    });
    if (!value) return false;
    await keyManager.set(key, value);
    emitter.fire();
  }
  return true;
}

async function selectModel(
  settingKeys: string[],
  modelsData: ModelsData,
  keyManager: KeyManager,
  emitter: vscode.EventEmitter<void>,
): Promise<void> {
  const modelKeys = settingKeys.filter((k) => k.endsWith("Model"));
  if (!modelKeys.length) return;

  let settingKey: string;
  if (modelKeys.length === 1) {
    settingKey = modelKeys[0];
  } else {
    const picked = await vscode.window.showQuickPick<ModelSettingItem>(
      modelKeys.map((k) => ({ label: formatLabel(k), settingKey: k })),
      { placeHolder: "Which model to configure?" },
    );
    if (!picked) return;
    settingKey = picked.settingKey;
  }

  const items: vscode.QuickPickItem[] = [];
  for (const [provider, info] of Object.entries(modelsData.providers)) {
    items.push({ label: provider, kind: vscode.QuickPickItemKind.Separator });
    for (const name of info.models) {
      items.push({ label: name });
    }
  }

  if (!items.length) {
    vscode.window.showWarningMessage(
      "No models available. Run generate-models script.",
    );
    return;
  }

  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: `Select ${formatLabel(settingKey).toLowerCase()}`,
    matchOnDescription: true,
  });

  if (!picked) return;

  await vscode.workspace
    .getConfiguration(SETTING_SECTION)
    .update(settingKey, picked.label, vscode.ConfigurationTarget.Global);

  const provider = providerOf(picked.label, modelsData);
  if (provider) {
    await ensureKeys(provider, modelsData, keyManager, emitter);
  }
}

async function manageApiKeys(
  keyManager: KeyManager,
  modelsData: ModelsData,
  emitter: vscode.EventEmitter<void>,
): Promise<void> {
  const entries = keyManager.entries();
  const items: vscode.QuickPickItem[] = [];

  for (const [key, value] of entries) {
    const masked =
      value.length > 8
        ? value.slice(0, 4) + "..." + value.slice(-4)
        : "****";
    items.push({ label: key, description: masked });
  }
  items.push({ label: "$(add) Add new API key", description: "" });

  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: "Manage API keys",
  });
  if (!picked) return;

  if (picked.label.startsWith("$(add)")) {
    const allKeys = new Set<string>();
    for (const info of Object.values(modelsData.providers)) {
      for (const k of info.envKeys) allKeys.add(k);
    }
    const unconfigured = [...allKeys].filter((k) => !keyManager.get(k)).sort();
    if (!unconfigured.length) {
      vscode.window.showInformationMessage("All provider API keys are already configured.");
      return;
    }
    const keyName = await vscode.window.showQuickPick(unconfigured, {
      placeHolder: "Which API key?",
    });
    if (!keyName) return;
    const value = await vscode.window.showInputBox({
      prompt: `Enter ${keyName}`,
      password: /KEY|SECRET|TOKEN/i.test(keyName),
      ignoreFocusOut: true,
    });
    if (value) {
      await keyManager.set(keyName, value);
      emitter.fire();
    }
    return;
  }

  const action = await vscode.window.showQuickPick(
    [{ label: "Update" }, { label: "Remove" }],
    { placeHolder: picked.label },
  );
  if (!action) return;
  if (action.label === "Remove") {
    await keyManager.remove(picked.label);
    emitter.fire();
    vscode.window.showInformationMessage(`Removed ${picked.label}`);
  } else {
    const value = await vscode.window.showInputBox({
      prompt: `Enter new value for ${picked.label}`,
      password: /KEY|SECRET|TOKEN/i.test(picked.label),
      ignoreFocusOut: true,
    });
    if (value) {
      await keyManager.set(picked.label, value);
      emitter.fire();
    }
  }
}

export async function activate(
  context: vscode.ExtensionContext,
): Promise<void> {
  let modelsData: ModelsData = { providers: {} };
  try {
    const loaded = require("./models.json");
    if (loaded?.providers) modelsData = loaded;
  } catch {}

  const allEnvKeys = new Set<string>();
  for (const info of Object.values(modelsData.providers)) {
    for (const k of info.envKeys) allEnvKeys.add(k);
  }

  const keyManager = new KeyManager(context.secrets);
  await keyManager.loadAll([...allEnvKeys]);

  const prefix = SETTING_SECTION + ".";
  const settingKeys = Object.keys(
    context.extension.packageJSON?.contributes?.configuration?.properties ?? {},
  )
    .filter((k) => k.startsWith(prefix))
    .map((k) => k.slice(prefix.length));

  const emitter = new vscode.EventEmitter<void>();
  context.subscriptions.push(
    emitter,
    context.secrets.onDidChange(async (e) => {
      if (!allEnvKeys.has(e.key)) return;
      keyManager.syncCache(e.key, await context.secrets.get(e.key));
      emitter.fire();
    }),
  );

  const log = vscode.window.createOutputChannel("Interact MCP");
  context.subscriptions.push(log);

  function resolveCommand(): [string, string[]] {
    const explicit = vscode.workspace
      .getConfiguration(SETTING_SECTION)
      .get<string>("projectPath") || "";
    if (explicit) {
      log.appendLine(`Using explicit projectPath: ${explicit}`);
      return ["uv", ["run", "--directory", explicit, "interact-mcp"]];
    }

    // Auto-detect workspace containing interact-mcp
    const folders = vscode.workspace.workspaceFolders ?? [];
    log.appendLine(`Scanning ${folders.length} workspace folder(s)`);
    for (const folder of folders) {
      const p = require("path").join(folder.uri.fsPath, "pyproject.toml");
      try {
        const pyproject = require("fs").readFileSync(p, "utf8") as string;
        if (pyproject.includes('name = "interact-mcp"')) {
          log.appendLine(`Auto-detected project at ${folder.uri.fsPath}`);
          return ["uv", ["run", "--directory", folder.uri.fsPath, "interact-mcp"]];
        }
      } catch (err) {
        log.appendLine(`Skip ${p}: ${err instanceof Error ? err.message : err}`);
      }
    }

    log.appendLine("No local project found, falling back to uvx");
    return ["uvx", ["interact-mcp"]];
  }

  try {
    const serverDef = (vscode.lm as any).registerMcpServerDefinitionProvider(
      "interact-mcp",
      {
        provideMcpServerDefinitions() {
          const [cmd, args] = resolveCommand();
          const env = buildEnv(settingKeys, keyManager, allEnvKeys);
          log.appendLine(`Starting: ${cmd} ${args.join(" ")}`);
          return [
            new (vscode as any).McpStdioServerDefinition(
              "Interact MCP",
              cmd,
              args,
              env,
            ),
          ];
        },
        onDidChangeMcpServerDefinitions: emitter.event,
      },
    );
    context.subscriptions.push(serverDef);
    log.appendLine("MCP server definition registered");
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    log.appendLine(`MCP registration failed: ${msg}`);
    vscode.window.showWarningMessage(
      `Interact MCP: MCP server registration failed — ${msg}`,
    );
  }

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration(SETTING_SECTION)) emitter.fire();
    }),
    vscode.commands.registerCommand("interactMcp.selectModel", () =>
      selectModel(settingKeys, modelsData, keyManager, emitter),
    ),
    vscode.commands.registerCommand("interactMcp.manageApiKeys", () =>
      manageApiKeys(keyManager, modelsData, emitter),
    ),
  );
}

export function deactivate(): void {}
