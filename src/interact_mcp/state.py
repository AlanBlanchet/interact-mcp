import base64
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel
from playwright.async_api import Page


def dump_screenshot(screenshot_bytes: bytes, label: str, dump_dir: Path):
    dump_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]", "_", label)[:30]
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{slug}.png"
    (dump_dir / filename).write_bytes(screenshot_bytes)


class PageState(BaseModel):
    url: str
    title: str
    accessibility_tree: str
    screenshot_base64: str
    visible_text: str
    focused_element: str | None

    @classmethod
    async def capture(cls, page: Page, dump_dir: Path | None = None, scope: str | None = None):
        url = page.url
        title = await page.title()

        target = page
        if scope:
            target = page.locator(scope).first

        try:
            if scope:
                accessibility_tree = await target.aria_snapshot()
            else:
                snapshot = await page.accessibility.snapshot()
                accessibility_tree = json.dumps(snapshot, indent=2) if snapshot else ""
        except Exception:
            accessibility_tree = ""

        screenshot_bytes = await target.screenshot(type="png")
        screenshot_base64 = base64.b64encode(screenshot_bytes).decode()

        if dump_dir is not None:
            dump_screenshot(screenshot_bytes, urlparse(url).netloc, dump_dir)

        try:
            if scope:
                visible_text = (await target.inner_text())[:2000]
            else:
                visible_text = (await page.inner_text("body"))[:2000]
        except Exception:
            visible_text = ""

        try:
            props = await page.evaluate(
                "[document.activeElement?.tagName,"
                " document.activeElement?.id,"
                " document.activeElement?.className]"
            )
            tag, el_id, el_class = props
            focused_element = f"{tag}({el_id or el_class or ''})" if tag else None
        except Exception:
            focused_element = None

        return cls(
            url=url,
            title=title,
            accessibility_tree=accessibility_tree,
            screenshot_base64=screenshot_base64,
            visible_text=visible_text,
            focused_element=focused_element,
        )


class StateChange(BaseModel):
    before: PageState
    after: PageState
    description: str = ""

    @classmethod
    def compute(cls, before: PageState, after: PageState):
        parts: list[str] = []

        if before.url != after.url:
            parts.append(f"URL: {before.url} -> {after.url}")

        if before.title != after.title:
            parts.append(f"Title: {before.title} -> {after.title}")

        if before.focused_element != after.focused_element:
            parts.append(f"Focus: {before.focused_element} -> {after.focused_element}")

        before_words = set(before.visible_text.split())
        after_words = set(after.visible_text.split())
        added = after_words - before_words
        removed = before_words - after_words

        if added:
            sample = list(added)[:20]
            parts.append(f"New text: {' '.join(sample)}")

        if removed:
            sample = list(removed)[:20]
            parts.append(f"Removed text: {' '.join(sample)}")

        return cls(
            before=before,
            after=after,
            description="\n".join(parts) if parts else "No visible changes detected.",
        )
