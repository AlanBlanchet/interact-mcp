from interact_mcp.desktop import (
    DesktopElement,
    DesktopWindow,
    format_desktop_elements,
    map_key,
    parse_elements_from_vlm,
    ref_to_index,
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
