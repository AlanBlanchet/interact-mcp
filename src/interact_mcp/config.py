import os
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings

_PROVIDERS = {
    "openai":    (["gpt", "o1", "o3", "o4", "chatgpt", "openai"], ["OPENAI_API_KEY"]),
    "anthropic": (["claude", "anthropic"],                         ["ANTHROPIC_API_KEY"]),
    "gemini":    (["gemini"],                                      ["GEMINI_API_KEY"]),
    "zai":       (["zai"],                                         ["ZAI_API_KEY", "Z_AI_API_KEY"]),
}


class Config(BaseSettings):
    model_config = {"env_prefix": "INTERACT_MCP_"}

    image_model: str = "gpt-4o"
    video_model: str = "gemini/gemini-2.0-flash"
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

    def api_key_for(self, model: str):
        for prefixes, env_vars in _PROVIDERS.values():
            if any(model.startswith(p) for p in prefixes):
                for env_var in env_vars:
                    key = os.environ.get(env_var, "")
                    if key:
                        return key
                return ""
        return ""
