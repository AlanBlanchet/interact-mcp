# interact-mcp

MCP server for browser + desktop automation with VLM vision.

## Architecture

- Python 3.11, uv package manager, src layout at `src/interact_mcp/`
- FastMCP for protocol, Playwright for browser, xdotool/maim for desktop, litellm for VLM
- VS Code extension in `vscode-extension/` (TypeScript, SecretStorage for API keys)
- Config via pydantic-settings with `INTERACT_MCP_` env prefix
- `_run_actions_desktop()` and `_run_actions_browser()` are the two dispatch paths in server.py
- Every tool's docstring IS the agent-facing documentation — keep them precise about parameters and return values

## Desktop automation

- Tools accept EITHER `session` (browser) OR `window` (desktop) — mutually exclusive
- Mouse ops work in background via `xdotool --window WID`, keyboard MUST activate window first then restore previous focus via `_restore_focus`
- GTK apps ignore `xdotool key --window WID` — keyboard always needs `windowactivate`
- `desktop_type` for character input, `desktop_key` for control keys (Enter, Tab, combos)
- xdotool coordinates are window-relative and can be negative — clamp to 0
- `maim -u -i WID` uses XComposite — captures even when occluded (on supported compositors)
- `SleepAction` for agent-controlled delays between actions

## Video and vision

- ffmpeg libx264 requires even width AND height — use pad filter (`pad=ceil(iw/2)*2:ceil(ih/2)*2`)
- Playwright video requires context close — recording destroys and recreates the browser context
- `detect_motion()` gates VLM analysis: pixel-counting on histogram (not mean-diff), needed because VLMs hallucinate motion in static videos

## Testing

- `uv run pytest tests/ -q --tb=short` — must pass before committing
- `tests/live_desktop_test.py` is a manual live test, not CI-safe (needs X11 + running apps)
- Mock `_run` in desktop tests, mock `_get_active_window` for keyboard tests
- Browser integration tests skip without API keys
- TypeScript/extension changes → rebuild `.vsix` + reinstall in VS Code before declaring done
- Agent-facing behavior changes → validate via real agent chat: open VS Code, open chat panel, select cheap model (Haiku), send prompt, screenshot evidence required

## Git

- Strict mode (no git-mode file) — branches, conventional commits, `--no-ff` merges
- Pre-commit hook auto-builds `.vsix` when `vscode-extension/` files change
