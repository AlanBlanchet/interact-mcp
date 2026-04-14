from interact_mcp.browser import BrowserManager
from interact_mcp.config import Config
from interact_mcp.state import InteractiveElement, ref_locator


def _el(index: int, ref: str | None = None) -> InteractiveElement:
    return InteractiveElement(
        index=index,
        ref=ref,
        role="button",
        name=f"btn{index}",
        x=0,
        y=0,
        width=10,
        height=10,
    )


# --- BrowserManager element map ---


def test_element_map_per_tab_isolation():
    mgr = BrowserManager(Config())
    mgr.set_element_map(0, [_el(1), _el(2)])
    mgr.set_element_map(1, [_el(3)])

    assert mgr.get_element(1, tab=0) is not None
    assert mgr.get_element(2, tab=0) is not None
    assert mgr.get_element(3, tab=0) is None
    assert mgr.get_element(3, tab=1) is not None
    assert mgr.get_element(1, tab=1) is None


def test_element_map_tab_overwrite():
    mgr = BrowserManager(Config())
    mgr.set_element_map(0, [_el(1)])
    mgr.set_element_map(0, [_el(2)])
    assert mgr.get_element(1, tab=0) is None
    assert mgr.get_element(2, tab=0) is not None


def test_get_element_missing_tab():
    mgr = BrowserManager(Config())
    assert mgr.get_element(1, tab=5) is None


def test_get_element_default_tab():
    mgr = BrowserManager(Config())
    mgr.set_element_map(0, [_el(7)])
    assert mgr.get_element(7) is not None


# --- InteractiveElement ref ---


def test_element_ref_none_by_default():
    el = InteractiveElement(
        index=1, role="button", name="x", x=0, y=0, width=10, height=10
    )
    assert el.ref is None


def test_element_playwright_ref():
    el = InteractiveElement(
        index=1, ref="e42", role="button", name="x", x=0, y=0, width=10, height=10
    )
    assert el.playwright_ref == '[data-interact-ref="e42"]'


def test_element_center_coords():
    el = InteractiveElement(
        index=1, role="button", name="x", x=10, y=20, width=80, height=40
    )
    assert el.center_x == 50
    assert el.center_y == 40


# --- ref_locator ---


def test_ref_locator():
    assert ref_locator("e5") == '[data-interact-ref="e5"]'
