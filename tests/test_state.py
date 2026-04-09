import pytest

from interact_mcp.state import PageState, StateChange, dump_screenshot


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


def test_dump_screenshot(tmp_path):
    data = b"\x89PNG fake screenshot data"
    dump_screenshot(data, "example.com", tmp_path / "shots")
    files = list((tmp_path / "shots").glob("*.png"))
    assert len(files) == 1
    assert files[0].read_bytes() == data
    assert "example_com" in files[0].name
