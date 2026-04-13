import base64
import io
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel
from playwright.async_api import Page

_ANNOTATION_COLORS = ["#FF4444", "#44AA44", "#4444FF", "#FF8800", "#AA44AA", "#00AAAA"]
_ARIA_REF_RE = re.compile(r'- \w[\w-]*(?: "([^"]*)")?\s\[ref=(e\d+)[^\]]*\]')


def aria_locator(ref: str) -> str:
    return f"aria-ref:{ref}"


class InteractiveElement(BaseModel):
    index: int
    ref: str | None = None
    role: str
    name: str
    x: float
    y: float
    width: float
    height: float

    @property
    def center_x(self) -> int:
        return int(self.x + self.width / 2)

    @property
    def center_y(self) -> int:
        return int(self.y + self.height / 2)

    @property
    def playwright_ref(self) -> str | None:
        if self.ref is None:
            return None
        return aria_locator(self.ref)


def annotate_screenshot(
    screenshot_bytes: bytes, elements: list["InteractiveElement"]
) -> bytes:
    img = Image.open(io.BytesIO(screenshot_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    for el in elements:
        color = _ANNOTATION_COLORS[el.index % len(_ANNOTATION_COLORS)]
        draw.rectangle(
            [el.x, el.y, el.x + el.width, el.y + el.height], outline=color, width=2
        )
        badge_x, badge_y = el.x, el.y
        draw.rectangle([badge_x, badge_y, badge_x + 22, badge_y + 16], fill=color)
        draw.text((badge_x + 3, badge_y + 2), str(el.index), fill="white", font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def format_element_list(elements: list[InteractiveElement]) -> str:
    return "\n".join(
        f"  [{el.index}] {el.role}: {el.name!r}  ref={el.ref}" for el in elements
    )


def match_refs(aria_snapshot: str, raw_boxes: list[dict]) -> list[InteractiveElement]:
    name_to_refs: dict[str, list[str]] = {}
    for name_str, ref_str in _ARIA_REF_RE.findall(aria_snapshot):
        name_to_refs.setdefault(name_str, []).append(ref_str)

    name_counter: dict[str, int] = {}
    elements: list[InteractiveElement] = []
    for i, raw in enumerate(raw_boxes):
        name = raw["name"]
        idx = name_counter.get(name, 0)
        name_counter[name] = idx + 1
        refs = name_to_refs.get(name, [])
        elements.append(
            InteractiveElement(
                index=i + 1,
                ref=refs[idx] if idx < len(refs) else None,
                role=raw["tag"],
                name=name,
                x=raw["x"],
                y=raw["y"],
                width=raw["width"],
                height=raw["height"],
            )
        )
    return elements


def dump_media(data: bytes, label: str, dump_dir: Path, ext: str = "png"):
    dump_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9]", "_", label)[:30]
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{slug}.{ext}"
    (dump_dir / filename).write_bytes(data)


def bytes_to_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


class PageState(BaseModel):
    url: str
    title: str
    accessibility_tree: str
    screenshot_base64: str
    visible_text: str
    focused_element: str | None

    @classmethod
    async def capture(
        cls, page: Page, dump_dir: Path | None = None, scope: str | None = None
    ):
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
        screenshot_base64 = bytes_to_b64(screenshot_bytes)

        if dump_dir is not None:
            dump_media(screenshot_bytes, urlparse(url).netloc, dump_dir)

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

    def text_summary(self) -> str:
        return f"{self.title}\n\n{self.visible_text}"


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
