import litellm

from interact_mcp.config import Config
from interact_mcp.state import PageState


def _image_url(base64_png: str) -> dict:
    return {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{base64_png}"},
    }


async def _vision_completion(messages: list[dict], config: Config) -> str:
    kwargs: dict = {
        "model": config.vision_model,
        "messages": messages,
        "api_key": config.vision_api_key,
        "max_tokens": 200,
    }
    if config.vision_base_url:
        kwargs["api_base"] = config.vision_base_url

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content


def _build_messages(content: list[dict], prompt: str | None) -> list[dict]:
    items: list[dict] = []
    if prompt:
        items.append({"type": "text", "text": prompt})
    items.extend(content)
    return [{"role": "user", "content": items}]


async def analyze_images(
    images: list[str],
    context: str,
    config: Config,
    prompt: str | None = None,
) -> str:
    if not config.vision_api_key:
        return context
    content: list[dict] = [{"type": "text", "text": context}]
    for img in images:
        content.append(_image_url(img))
    return await _vision_completion(_build_messages(content, prompt), config)


async def analyze_screenshot(state: PageState, config: Config, prompt: str | None = None) -> str:
    if not config.vision_api_key:
        return state.text_summary()
    return await analyze_images(
        [state.screenshot_base64],
        f"Page: {state.title} ({state.url})",
        config,
        prompt,
    )
