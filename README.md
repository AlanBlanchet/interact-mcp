# interact-mcp

MCP server for browser interaction and desktop window analysis. Gives agents the ability to navigate, click, type, scroll, and drag in a headless browser — plus capture and analyze any desktop window — with optional vision analysis.

Instead of screenshot → analyze → act loops, each tool returns a **text summary of what changed**. Vision analysis is optional and controlled by the caller via `query`.

---

## Install

```bash
uvx interact-mcp
```

Or add to a project:

```bash
uv add interact-mcp
```

Playwright browsers are auto-installed on first run. Desktop window analysis requires X11 + `maim` (Linux).

```bash
# On Debian/Ubuntu, install maim for desktop capture
sudo apt install maim
```

---

## Configuration

All settings are environment variables with the `INTERACT_MCP_` prefix.

| Variable                           | Default    | Description                                                                          |
| ---------------------------------- | ---------- | ------------------------------------------------------------------------------------ |
| `INTERACT_MCP_VISION_MODEL`        | `gpt-4o`   | litellm model string — any provider supported                                        |
| `INTERACT_MCP_VISION_API_KEY`      | _(empty)_  | API key for the vision model. When empty, tools return text-only summaries           |
| `INTERACT_MCP_VISION_BASE_URL`     | _(none)_   | Custom endpoint (e.g. local Ollama, Azure)                                           |
| `INTERACT_MCP_HEADLESS`            | `true`     | Run browser headlessly                                                               |
| `INTERACT_MCP_BROWSER_TYPE`        | `chromium` | `chromium`, `firefox`, or `webkit`                                                   |
| `INTERACT_MCP_VIEWPORT_WIDTH`      | `1280`     | Browser viewport width                                                               |
| `INTERACT_MCP_VIEWPORT_HEIGHT`     | `720`      | Browser viewport height                                                              |
| `INTERACT_MCP_SCREENSHOT_DUMP_DIR` | _(none)_   | When set, saves every screenshot as a PNG file to this folder — useful for debugging |

### Vision model examples

```bash
# OpenAI
INTERACT_MCP_VISION_API_KEY=sk-...
INTERACT_MCP_VISION_MODEL=gpt-4o

# Anthropic
INTERACT_MCP_VISION_API_KEY=sk-ant-...
INTERACT_MCP_VISION_MODEL=claude-3-5-sonnet-20241022

# Google
INTERACT_MCP_VISION_API_KEY=...
INTERACT_MCP_VISION_MODEL=gemini/gemini-1.5-pro

# Local (no key needed)
INTERACT_MCP_VISION_MODEL=ollama/llava
INTERACT_MCP_VISION_BASE_URL=http://localhost:11434
```

---

## MCP client setup

### Claude Desktop

```json
{
  "mcpServers": {
    "interact": {
      "command": "uvx",
      "args": ["interact-mcp"],
      "env": {
        "INTERACT_MCP_VISION_API_KEY": "sk-...",
        "INTERACT_MCP_VISION_MODEL": "gpt-4o"
      }
    }
  }
}
```

### VS Code / Copilot

In `.vscode/mcp.json` or `~/.config/Code/User/mcp.json`:

```json
{
  "servers": {
    "interact": {
      "type": "stdio",
      "command": "bash",
      "args": ["-c", "source ~/.api_keys && INTERACT_MCP_VISION_API_KEY=$OPENAI_API_KEY exec uvx interact-mcp"]
    }
  }
}
```

Or with explicit env:

```json
{
  "servers": {
    "interact": {
      "type": "stdio",
      "command": "uvx",
      "args": ["interact-mcp"],
      "env": {
        "INTERACT_MCP_VISION_API_KEY": "sk-..."
      }
    }
  }
}
```

---

## Tools

The browser session is **persistent** across all tool calls. Navigate once, then click, type, scroll — each call picks up where the last left off. No session management needed.

### Common parameters

Most browser tools accept these optional params:

| Param | Type | Description |
|---|---|---|
| `query` | string | Prompt sent to the vision model alongside screenshots. Controls what the VLM focuses on. |
| `scope` | string | CSS selector to narrow the screenshot and text extraction to a specific element instead of the full page. |
| `wait` | string | Wait condition after the action, before capturing state. Values: `networkidle`, `domcontentloaded`, `load`, or any CSS selector (waits for it to be visible). |

### `navigate(url, query?, scope?, wait?)`

Go to a URL. Returns page title and visible text. If `query` is provided and vision is configured, the page is analyzed with that query instead.

```
navigate("https://github.com")
navigate("https://github.com", query="What is the main call-to-action?")
navigate("https://myapp.com", wait="networkidle", scope="#main-content")
```

### `click(selector?, x?, y?, query?, scope?, wait?)`

Click an element by CSS selector or by coordinates. Returns a summary of what changed after the click.

```
click(selector="button[type=submit]")
click(selector="button[type=submit]", wait="networkidle")
click(selector="#login-btn", query="Did login succeed?", scope=".auth-panel")
```

### `type_text(selector, text, clear_first?, query?, scope?, wait?)`

Type into an input field. `clear_first=true` replaces existing content (default). Returns what changed.

```
type_text(selector="input[name=email]", text="user@example.com")
type_text(selector="#search", text="interact mcp", clear_first=False)
```

### `scroll(direction?, amount?, query?, scope?, wait?)`

Scroll the page. `direction` is `down`/`up`/`left`/`right`, `amount` is number of scroll increments (default 3). Returns what became visible.

```
scroll()
scroll(direction="up", amount=5, scope=".results-panel")
```

### `drag(from_x, from_y, to_x, to_y, query?, scope?, wait?)`

Mouse drag from one coordinate to another. Returns what changed.

```
drag(from_x=100, from_y=200, to_x=300, to_y=200)
```

### `screenshot(query?, scope?)`

Capture the current page or a scoped element. Returns vision analysis if query is provided.

```
screenshot()
screenshot(query="Are there any error messages visible?")
screenshot(scope=".sidebar", query="What navigation items are available?")
```

### `evaluate_js(script, query?, scope?, wait?)`

Run JavaScript on the page. Returns the script result plus a summary of any page changes.

```
evaluate_js(script="return document.querySelectorAll('a').length")
evaluate_js(script="window.scrollTo(0, document.body.scrollHeight)", wait="networkidle")
```

### `get_page_state(scope?)`

Observe the current page or a scoped element. Returns URL, title, focused element, accessibility tree, and visible text.

```
get_page_state()
get_page_state(scope="#hero-table")
```

### `wait_for(selector, state?, timeout?, query?, scope?)`

Wait for an element to reach a specific state. Useful after actions that trigger async loading.

- `state`: `visible` (default), `hidden`, `attached`, `detached`
- `timeout`: milliseconds (default 10000)

```
wait_for(selector=".results-table")
wait_for(selector=".loading-spinner", state="hidden")
wait_for(selector="#success-message", timeout=5000, query="What does the success message say?")
```

### `list_clickable(scope?)`

List all interactive elements (links, buttons, inputs, selects) with their CSS selectors and text. Use this to discover what actions are available.

```
list_clickable()
list_clickable(scope=".navigation")
```

### `run_actions(actions, query?)`

Execute multiple actions in one call. Returns per-step change reports plus a final state summary. Best for known workflows (login, form fill, submit) where each step is predetermined.

```
run_actions(actions=[
  {"type": "navigate", "url": "https://example.com/login"},
  {"type": "type_text", "selector": "#email", "text": "user@example.com"},
  {"type": "type_text", "selector": "#password", "text": "secret"},
  {"type": "click", "selector": "button[type=submit]"}
], query="Did the login succeed? What page are we on?")
```

Action types:

| Type          | Required fields                    | Optional fields                                    |
| ------------- | ---------------------------------- | -------------------------------------------------- |
| `navigate`    | `url`                              | —                                                  |
| `click`       | `selector` OR `x`+`y`              | —                                                  |
| `type_text`   | `selector`, `text`                 | `clear_first` (default: true)                      |
| `scroll`      | —                                  | `direction` (default: down), `amount` (default: 3) |
| `drag`        | `from_x`, `from_y`, `to_x`, `to_y` | —                                                  |
| `evaluate_js` | `script`                           | —                                                  |

All action types also support an optional `wait` key for per-step wait conditions.

---

## Desktop window tools

These work on X11 desktops (Linux). They capture real desktop windows — not just the headless browser.

### `list_desktop_windows()`

List all visible desktop windows with their names and dimensions.

```
list_desktop_windows()
```

### `analyze_window(title, query?)`

Capture a desktop window by title substring and analyze it with vision (if configured).

```
analyze_window(title="Chrome")
analyze_window(title="Visual Studio Code", query="What file is currently open?")
analyze_window(title="Slack", query="Are there any unread messages?")
```

---

## How tracking works

The browser session is a single persistent Playwright page. Each tool call operates on the same page state:

1. Call `navigate("http://localhost:8000")` → agent reads page title + content
2. Call `click(selector="#sign-in")` → agent reads what changed (modal opened? redirect?)
3. Call `type_text(selector="#email", text="user@example.com")` → agent reads what changed
4. Call `screenshot(query="Is the form filled correctly?")` → agent gets visual confirmation
5. Call `click(selector="button[type=submit]")` → agent reads what changed (success? error?)
6. Call `analyze_window(title="Chrome", query="Did the page update in the real browser too?")` → check the actual desktop

Each tool returns enough context to decide the next action. Use `get_page_state()` at any point to re-orient if you're unsure of the current state.

### Typical workflow: interact with a local server

```
navigate("http://localhost:8000", wait="networkidle")
list_clickable()
click(selector="nav a[href='/settings']", wait="networkidle")
type_text(selector="#api-key", text="sk-test-123")
click(selector="button[type=submit]", wait="networkidle", query="Did the settings save?")
screenshot(scope=".settings-form", query="What does the form look like now?")
```

### Scoped inspection

```
navigate("http://localhost:8000")
screenshot(scope="#hero-table", query="Are there any alignment issues in the table?")
get_page_state(scope=".sidebar")
list_clickable(scope=".toolbar")
```

### Batch workflow: login + navigate

```
run_actions(actions=[
  {"type": "navigate", "url": "http://localhost:8000/login"},
  {"type": "type_text", "selector": "#username", "text": "admin"},
  {"type": "type_text", "selector": "#password", "text": "secret"},
  {"type": "click", "selector": "button[type=submit]"}
], query="Did login succeed? What page are we on now?")
```

---

## Screenshot dumping

Set `INTERACT_MCP_SCREENSHOT_DUMP_DIR` to a folder path and every `PageState` capture will save a timestamped PNG there. Filenames are `{timestamp}_{url_host}.png`. Screenshots are still consumed and analyzed normally — dumping is additive.

```bash
INTERACT_MCP_SCREENSHOT_DUMP_DIR=./debug-screenshots uvx interact-mcp
```

---

## No system prompt

Vision calls do not include a system prompt. The `query` parameter you pass to any tool becomes the user-facing prompt the model receives alongside the page data. You control all framing.
