import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from interact_mcp.desktop import (
    DesktopElement,
    DesktopWindow,
    desktop_click,
    desktop_drag,
    desktop_hover,
    desktop_key,
    desktop_scroll,
    desktop_type,
    detect_motion,
    format_desktop_elements,
    get_element,
    map_key,
    parse_elements_from_vlm,
    ref_to_index,
    store_elements,
    window_listing,
)


def test_area_computed():
    win = DesktopWindow(name="test", wid=1, w=800, h=600, x=0, y=0)
    assert win.area == 480000


def test_window_listing_format():
    windows = [
        DesktopWindow(name="Zed", wid=2, w=1920, h=1080, x=0, y=0),
        DesktopWindow(name="Alacritty", wid=1, w=800, h=600, x=10, y=10),
    ]
    result = window_listing(windows)
    lines = result.split("\n")
    assert len(lines) == 2
    assert lines[0] == "  Alacritty (800x600)"
    assert lines[1] == "  Zed (1920x1080)"


def test_window_listing_empty():
    assert window_listing([]) == ""


def test_desktop_element_center():
    el = DesktopElement(index=1, x=100, y=200, w=80, h=40, role="button", name="OK")
    assert el.center_x == 140
    assert el.center_y == 220


def test_map_key_single():
    assert map_key("Enter") == "Return"
    assert map_key("ArrowDown") == "Down"
    assert map_key("Tab") == "Tab"
    assert map_key("a") == "a"


def test_map_key_combo():
    assert map_key("Control+a") == "ctrl+a"
    assert map_key("Control+Shift+ArrowUp") == "ctrl+shift+Up"
    assert map_key("Alt+F4") == "alt+F4"


def test_format_desktop_elements():
    elements = [
        DesktopElement(index=1, x=10, y=20, w=100, h=30, role="button", name="Save"),
        DesktopElement(index=2, x=120, y=20, w=100, h=30, role="button", name="Cancel"),
    ]
    result = format_desktop_elements(elements)
    assert "[1] button: 'Save' (100x30 at 10,20)" in result
    assert "[2] button: 'Cancel' (100x30 at 120,20)" in result


def test_parse_elements_from_vlm_valid():
    response = 'Here are the elements: [{"role": "button", "name": "OK", "x": 100, "y": 200, "w": 80, "h": 40}]'
    elements = parse_elements_from_vlm(response)
    assert elements is not None
    assert len(elements) == 1
    assert elements[0].role == "button"
    assert elements[0].name == "OK"
    assert elements[0].x == 100
    assert elements[0].center_x == 140


def test_parse_elements_from_vlm_no_json():
    assert parse_elements_from_vlm("No elements found in this image.") is None


def test_parse_elements_from_vlm_malformed():
    assert parse_elements_from_vlm("[{invalid json}]") is None


def test_parse_elements_from_vlm_partial():
    response = '[{"role": "button", "name": "OK", "x": 10, "y": 20, "w": 30, "h": 40}, {"bad": true}]'
    elements = parse_elements_from_vlm(response)
    assert elements is not None
    assert len(elements) == 1


def test_ref_to_index():
    assert ref_to_index("e0") == 0
    assert ref_to_index("e42") == 42
    assert ref_to_index("e999") == 999


# --- Async desktop action tests ---


@pytest.fixture
def mock_run():
    with patch("interact_mcp.desktop._run", new_callable=AsyncMock) as m:
        yield m


@pytest.mark.asyncio
async def test_desktop_click_commands(mock_run):
    await desktop_click(123, 50, 100)
    assert mock_run.call_count == 2
    mock_run.assert_any_call("xdotool", "mousemove", "--window", "123", "50", "100")
    mock_run.assert_any_call("xdotool", "click", "--window", "123", "1")


@pytest.mark.asyncio
async def test_desktop_click_right_button(mock_run):
    await desktop_click(123, 50, 100, button=3)
    mock_run.assert_any_call("xdotool", "click", "--window", "123", "3")


@pytest.mark.asyncio
async def test_desktop_type_commands(mock_run):
    await desktop_type(123, "hello world")
    mock_run.assert_called_once_with(
        "xdotool", "type", "--window", "123", "--delay", "12", "--", "hello world"
    )


@pytest.mark.asyncio
async def test_desktop_key_commands(mock_run):
    await desktop_key(123, "Enter")
    mock_run.assert_called_once_with("xdotool", "key", "--window", "123", "--", "Return")


@pytest.mark.asyncio
async def test_desktop_key_combo(mock_run):
    await desktop_key(123, "Control+a")
    mock_run.assert_called_once_with("xdotool", "key", "--window", "123", "--", "ctrl+a")


@pytest.mark.asyncio
async def test_desktop_scroll_down(mock_run):
    await desktop_scroll(123, 50, 100, "down", 3)
    assert mock_run.call_count == 4
    mock_run.assert_any_call("xdotool", "mousemove", "--window", "123", "50", "100")
    calls = [c for c in mock_run.call_args_list if "click" in c.args]
    assert len(calls) == 3
    for c in calls:
        assert c.args == ("xdotool", "click", "--window", "123", "5")


@pytest.mark.asyncio
async def test_desktop_scroll_up(mock_run):
    await desktop_scroll(123, 50, 100, "up", 2)
    assert mock_run.call_count == 3
    calls = [c for c in mock_run.call_args_list if "click" in c.args]
    assert len(calls) == 2
    for c in calls:
        assert c.args == ("xdotool", "click", "--window", "123", "4")


@pytest.mark.asyncio
async def test_desktop_drag_commands(mock_run):
    await desktop_drag(123, 0, 0, 100, 100, steps=5)
    # mousemove start + mousedown + 5 intermediate mousemoves + mouseup = 8
    assert mock_run.call_count == 8
    mock_run.assert_any_call("xdotool", "mousemove", "--window", "123", "0", "0")
    mock_run.assert_any_call("xdotool", "mousedown", "--window", "123", "1")
    mock_run.assert_any_call("xdotool", "mouseup", "--window", "123", "1")
    # verify intermediate coords (linear interpolation)
    for i in range(1, 6):
        expected_x = str(100 * i // 5)
        expected_y = str(100 * i // 5)
        mock_run.assert_any_call(
            "xdotool", "mousemove", "--window", "123", expected_x, expected_y
        )


@pytest.mark.asyncio
async def test_desktop_hover_commands(mock_run):
    await desktop_hover(123, 200, 300)
    mock_run.assert_called_once_with("xdotool", "mousemove", "--window", "123", "200", "300")


@pytest.mark.asyncio
async def test_desktop_no_focus_stealing(mock_run):
    await desktop_click(1, 0, 0)
    await desktop_type(1, "x")
    await desktop_key(1, "a")
    await desktop_scroll(1, 0, 0, "down", 1)
    await desktop_drag(1, 0, 0, 1, 1, steps=1)
    await desktop_hover(1, 0, 0)
    focus_commands = {"windowfocus", "windowactivate", "windowraise"}
    for call in mock_run.call_args_list:
        assert not focus_commands.intersection(call.args)


def test_detect_motion_ffmpeg_failure():
    with patch("interact_mcp.desktop.subprocess.run", side_effect=RuntimeError("boom")):
        assert detect_motion(b"fake video") is True


def test_store_and_get_element():
    elements = [
        DesktopElement(index=1, x=10, y=20, w=30, h=40, role="button", name="OK"),
        DesktopElement(index=2, x=50, y=60, w=70, h=80, role="link", name="Help"),
    ]
    store_elements(999, elements)
    assert get_element(999, 1) == elements[0]
    assert get_element(999, 2) == elements[1]


def test_get_element_invalid_index():
    store_elements(888, [])
    assert get_element(888, 1) is None
    assert get_element(777, 5) is None


@pytest.mark.asyncio
async def test_run_raises_on_failure():
    mock_proc = AsyncMock()
    mock_proc.returncode = 1
    mock_proc.communicate.return_value = (b"", b"some error")
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from interact_mcp.desktop import _run

        with pytest.raises(RuntimeError, match="xdotool failed"):
            await _run("xdotool", "fake", "cmd")
