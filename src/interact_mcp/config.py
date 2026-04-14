import os
from pathlib import Path
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings

_PREFIX_KEY_MAP = {
    "gpt": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}


class Config(BaseSettings):
    model_config = {"env_prefix": "INTERACT_MCP_"}

    vision_model: str = "gpt-4o"
    vision_api_key: str = ""
    vision_base_url: str | None = None
    headless: bool = True
    slow_mo: int = 0
    browser_type: Literal["chromium", "firefox", "webkit"] = "chromium"
    viewport_width: int = 1280
    viewport_height: int = 720
    screenshot_dump_dir: Path | None = None
    video_fps: int = 5
    video_duration: float = 3.0

    @model_validator(mode="after")
    def _resolve_api_key(self):
        if self.vision_api_key:
            return self
        for prefix, env_var in _PREFIX_KEY_MAP.items():
            if self.vision_model.startswith(prefix):
                key = os.environ.get(env_var, "")
                if key:
                    self.vision_api_key = key
                    return self
        self.vision_api_key = os.environ.get("OPENAI_API_KEY", "")
        return self
