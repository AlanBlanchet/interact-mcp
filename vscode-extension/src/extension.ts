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

function settingToEnv(key: string): string {
  return ENV_PREFIX + key.replace(/[A-Z]/g, (c) => "_" + c).toUpperCase();
}

function formatLabel(key: string): string {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (c) => c.toUpperCase());
}

function filterEnv(env: NodeJS.ProcessEnv): Record<string, string> {
  const result: Record<string, string> = {};
  for (const [k, v] of Object.entries(env)) {
    if (v !== undefined) result[k] = v;
  }
  return result;
}

function buildEnv(settingKeys: string[]): Record<string, string> {
  const cfg = vscode.workspace.getConfiguration(SETTING_SECTION);
  const env: Record<string, string> = {};

  for (const key of settingKeys) {
    const value = cfg.get(key);
    if (value === undefined || value === null || value === "") continue;
    env[settingToEnv(key)] =
      typeof value === "boolean" ? (value ? "true" : "false") : String(value);
  }

  return { ...filterEnv(process.env), ...env };
}

async function selectModel(
  settingKeys: string[],
  modelsData: ModelsData,
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

  if (picked) {
    await vscode.workspace
      .getConfiguration(SETTING_SECTION)
      .update(settingKey, picked.label, vscode.ConfigurationTarget.Global);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  let modelsData: ModelsData = { providers: {} };
  try {
    const loaded = require("./models.json");
    if (loaded?.providers) modelsData = loaded;
  } catch {}

  const prefix = SETTING_SECTION + ".";
  const settingKeys = Object.keys(
    context.extension.packageJSON?.contributes?.configuration?.properties ?? {},
  )
    .filter((k) => k.startsWith(prefix))
    .map((k) => k.slice(prefix.length));

  const emitter = new vscode.EventEmitter<void>();
  context.subscriptions.push(emitter);

  try {
    const serverDef = (vscode.lm as any).registerMcpServerDefinitionProvider(
      "interact-mcp",
      {
        provideMcpServerDefinitions() {
          return [
            new (vscode as any).McpStdioServerDefinition(
              "Interact MCP",
              "uvx",
              ["interact-mcp"],
              buildEnv(settingKeys),
            ),
          ];
        },
        onDidChangeMcpServerDefinitions: emitter.event,
      },
    );
    context.subscriptions.push(serverDef);
  } catch {
    vscode.window.showWarningMessage(
      "Interact MCP: MCP server registration unavailable — update VS Code to 1.99+",
    );
  }

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration(SETTING_SECTION)) emitter.fire();
    }),
    vscode.commands.registerCommand("interactMcp.selectModel", () =>
      selectModel(settingKeys, modelsData),
    ),
  );
}

export function deactivate(): void {}
