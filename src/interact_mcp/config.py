from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    model_config = {"env_prefix": "INTERACT_MCP_"}

    vision_model: str = "gpt-4o"
    vision_api_key: str = ""
    vision_base_url: str | None = None
    headless: bool = True
    browser_type: Literal["chromium", "firefox", "webkit"] = "chromium"
    viewport_width: int = 1280
    viewport_height: int = 720
    screenshot_dump_dir: Path | None = None
