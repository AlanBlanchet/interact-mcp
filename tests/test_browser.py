from interact_mcp.browser import BrowserManager
from interact_mcp.config import Config
from interact_mcp.state import _ARIA_REF_RE, InteractiveElement


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
    assert el.playwright_ref == "aria-ref:e42"


def test_element_center_coords():
    el = InteractiveElement(
        index=1, role="button", name="x", x=10, y=20, width=80, height=40
    )
    assert el.center_x == 50
    assert el.center_y == 40


# --- ARIA ref regex ---


def test_aria_ref_re_named_element():
    snap = '- button "Submit" [ref=e42]'
    assert _ARIA_REF_RE.findall(snap) == [("Submit", "e42")]


def test_aria_ref_re_unnamed_element():
    snap = "- button [ref=e43]"
    assert _ARIA_REF_RE.findall(snap) == [("", "e43")]


def test_aria_ref_re_element_with_extra_attrs():
    snap = "- checkbox [ref=e44, checked]"
    assert _ARIA_REF_RE.findall(snap) == [("", "e44")]


def test_aria_ref_re_duplicate_names():
    snap = '- button "Close" [ref=e1]\n- button "Close" [ref=e2]'
    matches = _ARIA_REF_RE.findall(snap)
    assert matches == [("Close", "e1"), ("Close", "e2")]


def test_aria_ref_re_mixed():
    snap = '- button "Submit" [ref=e1]\n- button [ref=e2]\n- textbox "Email" [ref=e3]'
    matches = _ARIA_REF_RE.findall(snap)
    assert matches == [("Submit", "e1"), ("", "e2"), ("Email", "e3")]


def test_aria_ref_re_hyphenated_role():
    snap = '- menu-item "Open" [ref=e5]'
    matches = _ARIA_REF_RE.findall(snap)
    assert matches == [("Open", "e5")]
