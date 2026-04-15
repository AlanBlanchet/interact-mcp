import base64
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import litellm
from pydantic import BaseModel

from interact_mcp.config import Config
from interact_mcp.state import PageState, bytes_to_b64


class MediaItem(BaseModel):
    data: str
    media_type: Literal["image", "video"] = "image"
    mime_type: str = "image/png"

    @classmethod
    def from_bytes(
        cls,
        raw: bytes,
        media_type: Literal["image", "video"] = "image",
        mime_type: str = "image/png",
    ):
        return cls(data=bytes_to_b64(raw), media_type=media_type, mime_type=mime_type)


def _image_content(item: MediaItem) -> dict:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{item.mime_type};base64,{item.data}"},
    }


def _extract_frames(video_base64: str, mime_type: str, fps: int = 1) -> list[str]:
    video_bytes = base64.b64decode(video_base64)
    with tempfile.TemporaryDirectory() as tmpdir:
        ext = "mp4" if "mp4" in mime_type else "webm"
        video_path = f"{tmpdir}/input.{ext}"
        Path(video_path).write_bytes(video_bytes)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-vf",
                f"fps={fps}",
                f"{tmpdir}/frame_%03d.jpg",
            ],
            check=True,
            capture_output=True,
        )
        return [
            bytes_to_b64(fp.read_bytes())
            for fp in sorted(Path(tmpdir).glob("frame_*.jpg"))
        ]


def _video_content(item: MediaItem, model: str) -> list[dict]:
    if model.startswith("gemini"):
        return [
            {
                "type": "file",
                "file": {
                    "file_data": f"data:{item.mime_type};base64,{item.data}",
                },
            }
        ]
    frames = _extract_frames(item.data, item.mime_type)
    return [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{f}"}}
        for f in frames
    ]


async def _vision_completion(
    messages: list[dict], model: str, base_url: str | None, max_tokens: int
) -> str:
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if base_url:
        kwargs["api_base"] = base_url

    response = await litellm.acompletion(**kwargs)
    text = response.choices[0].message.content
    if response.choices[0].finish_reason == "length":
        text += f"\n\n[Response truncated at {max_tokens} tokens — increase interactMcp.maxTokens for longer responses]"
    return text


def _build_messages(content: list[dict], prompt: str | None) -> list[dict]:
    items: list[dict] = []
    if prompt:
        items.append({"type": "text", "text": prompt})
    items.extend(content)
    return [{"role": "user", "content": items}]


async def analyze_media(
    media: list[MediaItem],
    context: str,
    config: Config,
    prompt: str | None = None,
) -> str:
    has_video = any(m.media_type == "video" for m in media)
    model, base_url = config.model_for("video" if has_video else "image")
    if not model:
        return "[Vision not configured — select a model in VS Code settings or set INTERACT_MCP_IMAGE_MODEL]"
    if not litellm.validate_environment(model)["keys_in_environment"]:
        return f"[Vision unavailable — {model} API key not configured] {context}"
    content: list[dict] = [{"type": "text", "text": context}]
    for item in media:
        if item.media_type == "image":
            content.append(_image_content(item))
        else:
            content.extend(_video_content(item, model))
    return await _vision_completion(
        _build_messages(content, prompt), model, base_url, config.max_tokens
    )


async def analyze_screenshot(
    state: PageState, config: Config, prompt: str | None = None
) -> str:
    if not config.image_model:
        return "[Vision not configured — select a model in VS Code settings or set INTERACT_MCP_IMAGE_MODEL]"
    if not litellm.validate_environment(config.image_model)["keys_in_environment"]:
        return f"[Vision unavailable — {config.image_model} API key not configured] {state.text_summary()}"
    media = [MediaItem(data=state.screenshot_base64)]
    return await analyze_media(
        media,
        f"Page: {state.title} ({state.url})",
        config,
        prompt,
    )
