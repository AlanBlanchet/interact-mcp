import io

import pytest
from PIL import Image

from interact_mcp.state import (
    InteractiveElement,
    PageState,
    StateChange,
    annotate_screenshot,
    dump_media,
    format_element_list,
)


def _make_state(**overrides) -> PageState:
    defaults = {
        "url": "https://example.com",
        "title": "Example",
        "accessibility_tree": "{}",
        "screenshot_base64": "abc123",
        "visible_text": "Hello world",
        "focused_element": None,
    }
    return PageState(**(defaults | overrides))


def test_no_changes():
    before = _make_state()
    after = _make_state()
    change = StateChange.compute(before, after)
    assert change.description == "No visible changes detected."


@pytest.mark.parametrize(
    "field, before_val, after_val, expected",
    [
        ("url", "https://example.com/a", "https://example.com/b", ["https://example.com/a", "https://example.com/b"]),
        ("title", "Page A", "Page B", ["Page A", "Page B"]),
        ("focused_element", "INPUT(search)", "BUTTON(submit)", ["INPUT(search)", "BUTTON(submit)"]),
        ("visible_text", "Hello", "Hello World", ["World"]),
        ("visible_text", "Hello World", "Hello", ["World"]),
    ],
)
def test_field_change(field, before_val, after_val, expected):
    before = _make_state(**{field: before_val})
    after = _make_state(**{field: after_val})
    change = StateChange.compute(before, after)
    for text in expected:
        assert text in change.description


def test_multiple_changes():
    before = _make_state(url="https://a.com", title="A", visible_text="old content")
    after = _make_state(url="https://b.com", title="B", visible_text="new content")
    change = StateChange.compute(before, after)
    assert "URL:" in change.description
    assert "Title:" in change.description
    assert "new" in change.description


def test_dump_media(tmp_path):
    data = b"\x89PNG fake screenshot data"
    dump_media(data, "example.com", tmp_path / "shots")
    files = list((tmp_path / "shots").glob("*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == data
    assert "example_com" in files[0].name


def _make_element(index: int, ref: str | None = None, **kw) -> InteractiveElement:
    defaults = dict(role="button", name=f"Element {index}", x=10.0, y=20.0, width=80.0, height=40.0)
    return InteractiveElement(index=index, ref=ref, **(defaults | kw))


def _make_png(width: int = 200, height: int = 100) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(240, 240, 240)).save(buf, format="PNG")
    return buf.getvalue()


# --- annotate_screenshot ---


def test_annotate_screenshot_produces_valid_png():
    elements = [_make_element(1, x=5, y=5, width=30, height=20),
                _make_element(2, x=50, y=10, width=40, height=30)]
    result = annotate_screenshot(_make_png(), elements)
    img = Image.open(io.BytesIO(result))
    assert img.format == "PNG"
    assert img.size == (200, 100)


def test_annotate_screenshot_no_elements():
    raw = _make_png()
    result = annotate_screenshot(raw, [])
    img = Image.open(io.BytesIO(result))
    assert img.size == (200, 100)


# --- format_element_list ---


def test_format_element_list():
    elements = [_make_element(1, ref="e10"), _make_element(2)]
    text = format_element_list(elements)
    assert "[1]" in text
    assert "[2]" in text
    assert "ref=e10" in text
    assert "ref=None" in text
    assert "button" in text


