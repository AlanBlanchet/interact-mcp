# interact-mcp

MCP server: browser + desktop automation with VLM vision.

## Architecture

- Python 3.11, uv, src layout `src/interact_mcp/`
- FastMCP (protocol), Playwright (browser), xdotool/maim (desktop), litellm (VLM)
- VS Code extension `vscode-extension/` (TypeScript, SecretStorage for API keys)
- Config: pydantic-settings, `INTERACT_MCP_` env prefix
- Two dispatch paths: `_run_actions_desktop()`, `_run_actions_browser()` in server.py
- Tool docstrings = agent-facing docs — keep precise

## Desktop

- `session` (browser) OR `window` (desktop) — mutually exclusive
- Mouse: background via `xdotool --window WID`. Keyboard: must `windowactivate` first → `_restore_focus` after
- GTK ignores `xdotool key --window` → keyboard always needs `windowactivate`
- `desktop_type` = character input, `desktop_key` = control keys/combos
- xdotool coords window-relative, can be negative → clamp to 0
- `maim -u -i WID` uses XComposite — captures even when occluded
- `SleepAction` for agent-controlled delays

## Video/Vision

- ffmpeg libx264 needs even w/h → pad filter (`pad=ceil(iw/2)*2:ceil(ih/2)*2`)
- Playwright video needs context close — recording destroys/recreates browser context
- `detect_motion()` gates VLM: pixel-counting on histogram (not mean-diff), VLMs hallucinate motion in static video

## Testing

- `uv run pytest tests/ -q --tb=short` — pass before committing
- `tests/live_desktop_test.py` = manual, not CI-safe (needs X11 + running apps)
- Mock `_run` in desktop tests, `_get_active_window` for keyboard tests
- Browser integration tests skip without API keys
- TypeScript/extension changes → rebuild `.vsix` + reinstall in VS Code before declaring done
- Agent-facing behavior changes → validate via real agent chat: open VS Code, open chat panel, select cheap model (Haiku), send prompt, screenshot evidence required

## Git

- Strict mode — branches, conventional commits, `--no-ff` merges
- Pre-commit hook auto-builds `.vsix` on `vscode-extension/` changes
