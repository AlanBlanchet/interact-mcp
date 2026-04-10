import pytest
from pydantic import TypeAdapter, ValidationError

from interact_mcp.actions import (
    AnyAction,
    ClickAction,
    DragAction,
    EvaluateJsAction,
    ListClickableAction,
    NavigateAction,
    ScreenshotAction,
    ScrollAction,
    TypeTextAction,
    WaitForAction,
)

adapter = TypeAdapter(list[AnyAction])


def test_click_with_coordinates():
    action = ClickAction(x=100, y=200)
    assert action.x == 100
    assert action.y == 200


def test_click_missing_target():
    with pytest.raises(ValidationError):
        ClickAction()


def test_click_partial_coordinates():
    with pytest.raises(ValidationError):
        ClickAction(x=100)


def test_scroll_defaults():
    action = ScrollAction()
    assert action.direction == "down"
    assert action.amount == 3


def test_scroll_invalid_amount():
    with pytest.raises(ValidationError):
        ScrollAction(amount=0)


def test_wait_for_defaults():
    action = WaitForAction(selector="#el")
    assert action.state == "visible"
    assert action.timeout == 10000


def test_wait_for_invalid_timeout():
    with pytest.raises(ValidationError):
        WaitForAction(selector="#el", timeout=0)


def test_discriminated_union_from_dict():
    raw = [
        {"type": "click", "selector": "#btn"},
        {"type": "navigate", "url": "https://example.com"},
        {"type": "screenshot"},
        {"type": "type_text", "selector": "#input", "text": "hello"},
        {"type": "scroll", "direction": "up", "amount": 5},
        {"type": "drag", "from_x": 0, "from_y": 0, "to_x": 100, "to_y": 100},
        {"type": "evaluate_js", "script": "document.title"},
        {"type": "wait_for", "selector": "#loading", "state": "hidden"},
        {"type": "list_clickable", "scope": "#nav"},
    ]
    actions = adapter.validate_python(raw)
    assert len(actions) == 9
    expected_types = [
        ClickAction,
        NavigateAction,
        ScreenshotAction,
        TypeTextAction,
        ScrollAction,
        DragAction,
        EvaluateJsAction,
        WaitForAction,
        ListClickableAction,
    ]
    for action, expected in zip(actions, expected_types):
        assert isinstance(action, expected)


def test_mutates_flag():
    assert ClickAction(selector="#x").mutates is True
    assert TypeTextAction(selector="#x", text="hi").mutates is True
    assert ScrollAction().mutates is True
    assert DragAction(from_x=0, from_y=0, to_x=1, to_y=1).mutates is True
    assert NavigateAction(url="https://x.com").mutates is True
    assert EvaluateJsAction(script="1+1").mutates is True
    assert ScreenshotAction().mutates is False
    assert WaitForAction(selector="#x").mutates is False
    assert ListClickableAction().mutates is False


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        adapter.validate_python([{"type": "unknown_action"}])
