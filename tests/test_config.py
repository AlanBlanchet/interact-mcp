from pathlib import Path

from interact_mcp.config import Config


def test_defaults():
    cfg = Config()
    assert cfg.vision_model == "gpt-4o"
    assert cfg.vision_api_key == ""
    assert cfg.vision_base_url is None
    assert cfg.headless is True
    assert cfg.browser_type == "chromium"
    assert cfg.viewport_width == 1280
    assert cfg.viewport_height == 720
    assert cfg.screenshot_dump_dir is None


def test_from_env(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_VISION_MODEL", "claude-3-opus")
    monkeypatch.setenv("INTERACT_MCP_VISION_API_KEY", "sk-test")
    monkeypatch.setenv("INTERACT_MCP_HEADLESS", "false")
    monkeypatch.setenv("INTERACT_MCP_BROWSER_TYPE", "firefox")
    monkeypatch.setenv("INTERACT_MCP_VIEWPORT_WIDTH", "1920")

    cfg = Config()
    assert cfg.vision_model == "claude-3-opus"
    assert cfg.vision_api_key == "sk-test"
    assert cfg.headless is False
    assert cfg.browser_type == "firefox"
    assert cfg.viewport_width == 1920


def test_screenshot_dump_dir_from_env(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_SCREENSHOT_DUMP_DIR", "/tmp/shots")
    cfg = Config()
    assert cfg.screenshot_dump_dir == Path("/tmp/shots")
