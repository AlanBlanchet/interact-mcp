from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

DEFAULT_LIMIT = 50
LOG_MAXLEN = 1000


class Config(BaseSettings):
    model_config = {"env_prefix": "INTERACT_MCP_"}

    image_model: str = ""
    video_model: str = ""
    image_base_url: str | None = None
    video_base_url: str | None = None
    headless: bool = True
    slow_mo: int = 0
    browser_type: Literal["chromium", "firefox", "webkit"] = "chromium"
    viewport_width: int = 1280
    viewport_height: int = 720
    screenshot_dump_dir: Path | None = None
    video_fps: int = 5
    video_duration: float = 3.0

    def model_for(self, media_type: str) -> tuple[str, str | None]:
        if media_type == "video":
            return self.video_model, self.video_base_url
        return self.image_model, self.image_base_url
