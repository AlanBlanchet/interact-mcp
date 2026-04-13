from pathlib import Path

from interact_mcp.config import Config


def test_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    cfg = Config()
    assert cfg.vision_model == "gpt-4o"
    assert cfg.vision_api_key == ""
    assert cfg.vision_base_url is None
    assert cfg.headless is True
    assert cfg.browser_type == "chromium"
    assert cfg.viewport_width == 1280
    assert cfg.viewport_height == 720
    assert cfg.screenshot_dump_dir is None
    assert cfg.video_fps == 5
    assert cfg.video_duration == 3.0


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


def test_auto_resolve_openai_key(monkeypatch):
    monkeypatch.delenv("INTERACT_MCP_VISION_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-auto-resolved")
    cfg = Config()
    assert cfg.vision_api_key == "sk-auto-resolved"


def test_auto_resolve_gemini_key(monkeypatch):
    monkeypatch.delenv("INTERACT_MCP_VISION_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key-123")
    monkeypatch.setenv("INTERACT_MCP_VISION_MODEL", "gemini-pro-vision")
    cfg = Config()
    assert cfg.vision_api_key == "gem-key-123"


def test_explicit_key_takes_priority(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_VISION_API_KEY", "explicit-key")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-use")
    cfg = Config()
    assert cfg.vision_api_key == "explicit-key"


def test_video_settings_from_env(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_VIDEO_FPS", "10")
    monkeypatch.setenv("INTERACT_MCP_VIDEO_DURATION", "5.0")
    cfg = Config()
    assert cfg.video_fps == 10
    assert cfg.video_duration == 5.0
