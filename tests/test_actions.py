import pytest
from pydantic import TypeAdapter, ValidationError

from interact_mcp.actions import (
    AnyAction,
    AnnotateAction,
    ClickAction,
    ClickElementAction,
    CloseTabAction,
    DragAction,
    EvaluateJsAction,
    HttpRequestAction,
    ListClickableAction,
    NavigateAction,
    NewTabAction,
    ScreenshotAction,
    ScrollAction,
    SwitchTabAction,
    TypeTextAction,
    UploadFileAction,
    WaitForAction,
)

adapter = TypeAdapter(list[AnyAction])


def test_click_with_ref():
    action = ClickAction(ref="e42")
    assert action.ref == "e42"
    assert action.selector is None
    assert action.x is None


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
        {
            "type": "upload_file",
            "selector": "input[type=file]",
            "path": "/tmp/file.txt",
        },
        {"type": "new_tab"},
        {"type": "switch_tab", "index": 1},
        {"type": "close_tab"},
        {"type": "http_request", "url": "https://example.com"},
        {"type": "annotate"},
        {"type": "click_element", "element": 3},
    ]
    actions = adapter.validate_python(raw)
    assert len(actions) == 16
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
        UploadFileAction,
        NewTabAction,
        SwitchTabAction,
        CloseTabAction,
        HttpRequestAction,
        AnnotateAction,
        ClickElementAction,
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
    assert UploadFileAction(selector="input", path="/f.txt").mutates is True
    assert NewTabAction().mutates is False
    assert SwitchTabAction().mutates is False
    assert CloseTabAction().mutates is False
    assert HttpRequestAction(url="https://x.com").mutates is False
    assert AnnotateAction().mutates is False
    assert ClickElementAction(element=1).mutates is True


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        adapter.validate_python([{"type": "unknown_action"}])


def test_upload_file_defaults():
    action = UploadFileAction(selector="input[type=file]", path="/some/file.txt")
    assert action.type == "upload_file"
    assert action.mutates is True


def test_new_tab_defaults():
    action = NewTabAction()
    assert action.type == "new_tab"
    assert action.url is None
    assert action.mutates is False


def test_switch_tab_defaults():
    action = SwitchTabAction()
    assert action.type == "switch_tab"
    assert action.index == 0
    assert action.mutates is False


def test_close_tab_defaults():
    action = CloseTabAction()
    assert action.type == "close_tab"
    assert action.index is None
    assert action.mutates is False


def test_http_request_defaults():
    action = HttpRequestAction(url="https://example.com")
    assert action.type == "http_request"
    assert action.method == "GET"
    assert action.headers == {}
    assert action.body is None
    assert action.mutates is False


def test_drag_with_refs():
    action = DragAction(from_ref="e1", to_ref="e2")
    assert action.from_ref == "e1"
    assert action.to_ref == "e2"
    assert action.from_x is None


def test_drag_missing_to():
    with pytest.raises(ValidationError):
        DragAction(from_x=0, from_y=0)


def test_type_text_with_ref():
    action = TypeTextAction(ref="e15", text="hello")
    assert action.ref == "e15"
    assert action.selector is None


def test_type_text_missing_target():
    with pytest.raises(ValidationError):
        TypeTextAction(text="hello")


def test_upload_file_with_ref():
    action = UploadFileAction(ref="e7", path="/some/file.txt")
    assert action.ref == "e7"
    assert action.selector is None


def test_upload_file_missing_target():
    with pytest.raises(ValidationError):
        UploadFileAction(path="/some/file.txt")


def test_annotate_defaults():
    action = AnnotateAction()
    assert action.type == "annotate"
    assert action.scope is None
    assert action.query is None
    assert action.mutates is False


def test_annotate_with_scope():
    action = AnnotateAction(scope="#main")
    assert action.scope == "#main"


def test_click_element_validates():
    action = ClickElementAction(element=3)
    assert action.element == 3
    assert action.type == "click_element"
    assert action.mutates is True
