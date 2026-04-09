from interact_mcp.desktop import DesktopWindow, window_listing


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
