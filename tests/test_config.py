from pathlib import Path

import pytest

from interact_mcp.config import Config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY",
        "ZAI_API_KEY", "Z_AI_API_KEY",
        "INTERACT_MCP_IMAGE_MODEL", "INTERACT_MCP_VIDEO_MODEL",
        "INTERACT_MCP_IMAGE_BASE_URL", "INTERACT_MCP_VIDEO_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_defaults():
    cfg = Config()
    assert cfg.image_model == "gpt-4o"
    assert cfg.video_model == "gemini/gemini-2.0-flash"
    assert cfg.image_base_url is None
    assert cfg.video_base_url is None
    assert cfg.headless is True
    assert cfg.browser_type == "chromium"
    assert cfg.viewport_width == 1280
    assert cfg.viewport_height == 720
    assert cfg.screenshot_dump_dir is None
    assert cfg.video_fps == 5
    assert cfg.video_duration == 3.0
    assert not hasattr(cfg, "vision_api_key")


def test_from_env(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_IMAGE_MODEL", "claude-3-opus")
    monkeypatch.setenv("INTERACT_MCP_VIDEO_MODEL", "gpt-4o")
    monkeypatch.setenv("INTERACT_MCP_HEADLESS", "false")
    monkeypatch.setenv("INTERACT_MCP_BROWSER_TYPE", "firefox")
    monkeypatch.setenv("INTERACT_MCP_VIEWPORT_WIDTH", "1920")
    cfg = Config()
    assert cfg.image_model == "claude-3-opus"
    assert cfg.video_model == "gpt-4o"
    assert cfg.headless is False
    assert cfg.browser_type == "firefox"
    assert cfg.viewport_width == 1920


def test_screenshot_dump_dir_from_env(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_SCREENSHOT_DUMP_DIR", "/tmp/shots")
    cfg = Config()
    assert cfg.screenshot_dump_dir == Path("/tmp/shots")


def test_api_key_for_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    cfg = Config()
    assert cfg.api_key_for("gpt-4o") == "sk-openai"


def test_api_key_for_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    cfg = Config()
    assert cfg.api_key_for("gemini/gemini-2.0-flash") == "gem-key"


def test_api_key_for_zai(monkeypatch):
    monkeypatch.setenv("ZAI_API_KEY", "zai-primary")
    cfg = Config()
    assert cfg.api_key_for("zai/glm-4.5v") == "zai-primary"


def test_api_key_for_zai_fallback(monkeypatch):
    monkeypatch.setenv("Z_AI_API_KEY", "z-ai-fallback")
    cfg = Config()
    assert cfg.api_key_for("zai/glm-4.5v") == "z-ai-fallback"


def test_api_key_for_anthropic(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    cfg = Config()
    assert cfg.api_key_for("claude-3-opus") == "sk-ant"


def test_api_key_for_routed_format(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    cfg = Config()
    assert cfg.api_key_for("openai/gpt-4o") == "sk-openai"
    assert cfg.api_key_for("anthropic/claude-3-opus") == "sk-ant"


def test_api_key_for_unknown_provider():
    cfg = Config()
    assert cfg.api_key_for("some-unknown-model") == ""


def test_image_base_url(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_IMAGE_BASE_URL", "https://img.example.com")
    cfg = Config()
    assert cfg.image_base_url == "https://img.example.com"


def test_video_base_url(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_VIDEO_BASE_URL", "https://vid.example.com")
    cfg = Config()
    assert cfg.video_base_url == "https://vid.example.com"


def test_video_settings_from_env(monkeypatch):
    monkeypatch.setenv("INTERACT_MCP_VIDEO_FPS", "10")
    monkeypatch.setenv("INTERACT_MCP_VIDEO_DURATION", "5.0")
    cfg = Config()
    assert cfg.video_fps == 10
    assert cfg.video_duration == 5.0


def test_api_key_for_openai_prefixes(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = Config()
    for prefix in ("gpt-4o", "o1-preview", "o3-mini", "o4-mini", "chatgpt-4o", "openai/gpt-4o"):
        assert cfg.api_key_for(prefix) == "sk-test"
