import * as vscode from "vscode";

const SETTINGS_TO_ENV: [string, string][] = [
  ["imageModel", "INTERACT_MCP_IMAGE_MODEL"],
  ["videoModel", "INTERACT_MCP_VIDEO_MODEL"],
  ["imageBaseUrl", "INTERACT_MCP_IMAGE_BASE_URL"],
  ["videoBaseUrl", "INTERACT_MCP_VIDEO_BASE_URL"],
  ["headless", "INTERACT_MCP_HEADLESS"],
  ["browserType", "INTERACT_MCP_BROWSER_TYPE"],
  ["viewportWidth", "INTERACT_MCP_VIEWPORT_WIDTH"],
  ["viewportHeight", "INTERACT_MCP_VIEWPORT_HEIGHT"],
];

const API_KEY_VARS = [
  "OPENAI_API_KEY",
  "GEMINI_API_KEY",
  "ANTHROPIC_API_KEY",
  "AZURE_API_KEY",
  "AZURE_API_BASE",
  "AWS_ACCESS_KEY_ID",
  "AWS_SECRET_ACCESS_KEY",
  "AWS_REGION_NAME",
  "GROQ_API_KEY",
  "MISTRAL_API_KEY",
  "DEEPSEEK_API_KEY",
  "TOGETHER_API_KEY",
  "OPENROUTER_API_KEY",
  "REPLICATE_API_KEY",
  "HUGGINGFACE_API_KEY",
  "COHERE_API_KEY",
  "VOYAGE_API_KEY",
  "VERTEXAI_PROJECT",
  "VERTEXAI_LOCATION",
];

type ModelMap = Record<string, string[]>;

function buildEnv(): Record<string, string> {
  const cfg = vscode.workspace.getConfiguration("interactMcp");
  const env: Record<string, string> = {};

  for (const [settingKey, envVar] of SETTINGS_TO_ENV) {
    const value = cfg.get(settingKey);
    if (value === undefined || value === null || value === "") continue;
    env[envVar] = typeof value === "boolean" ? (value ? "true" : "false") : String(value);
  }

  for (const v of API_KEY_VARS) {
    if (process.env[v]) env[v] = process.env[v]!;
  }

  return env;
}

async function selectModel(
  settingKey: "imageModel" | "videoModel",
  models: ModelMap,
): Promise<void> {
  const items: vscode.QuickPickItem[] = [];
  for (const [provider, names] of Object.entries(models)) {
    items.push({ label: provider, kind: vscode.QuickPickItemKind.Separator });
    for (const name of names) {
      items.push({ label: name });
    }
  }

  if (!items.length) {
    vscode.window.showWarningMessage("No models available. Run generate-models script.");
    return;
  }

  const picked = await vscode.window.showQuickPick(items, {
    placeHolder: `Select ${settingKey === "imageModel" ? "image" : "video"} model`,
    matchOnDescription: true,
  });

  if (picked) {
    await vscode.workspace
      .getConfiguration("interactMcp")
      .update(settingKey, picked.label, vscode.ConfigurationTarget.Global);
  }
}

export function activate(context: vscode.ExtensionContext): void {
  let models: ModelMap = {};
  try { models = require("./models.json"); } catch {}
  const emitter = new vscode.EventEmitter<void>();

  const provider = (vscode.lm as any).registerMcpServerDefinitionProvider("interact-mcp", {
    provideMcpServerDefinitions() {
      return [new (vscode as any).McpStdioServerDefinition("Interact MCP", "uvx", ["interact-mcp"], buildEnv())];
    },
    onDidChangeMcpServerDefinitions: emitter.event,
  });

  context.subscriptions.push(
    provider,
    emitter,
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("interactMcp")) emitter.fire();
    }),
    vscode.commands.registerCommand("interactMcp.selectImageModel", () =>
      selectModel("imageModel", models),
    ),
    vscode.commands.registerCommand("interactMcp.selectVideoModel", () =>
      selectModel("videoModel", models),
    ),
  );
}

export function deactivate(): void {}
