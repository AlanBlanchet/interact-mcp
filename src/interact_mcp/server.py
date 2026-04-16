import asyncio
import base64
from contextlib import asynccontextmanager
import json
from collections.abc import AsyncIterator
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from playwright.async_api import Page

from interact_mcp import desktop
from interact_mcp.actions import (
    AnyAction,
    AnnotateAction,
    BROWSER_ONLY_ACTIONS,
    ClickAction,
    ClickElementAction,
    CloseTabAction,
    DragAction,
    HoverAction,
    HttpRequestAction,
    KeyPressAction,
    NewTabAction,
    ScreenshotAction,
    ScrollAction,
    SwitchTabAction,
    TypeTextAction,
)
from interact_mcp.browser import BrowserManager, SessionRegistry
from interact_mcp.config import DEFAULT_LIMIT, Config
from interact_mcp.desktop import DesktopElement, DesktopWindow
from interact_mcp.state import (
    InteractiveElement,
    PageState,
    StateChange,
    annotate_screenshot,
    dump_media,
    format_element_list,
)
from interact_mcp.vision import MediaItem, analyze_media, analyze_screenshot

config = Config()
_sessions = SessionRegistry(config)
_DEFAULT_SESSION = "default"
_NO_WINDOWS_MSG = "No desktop windows detected (X11/maim required)."
_ANNOTATE_JS = (Path(__file__).parent / "js" / "annotate_elements.js").read_text()


def _find_desktop_window(title: str) -> desktop.DesktopWindow | str:
    windows = desktop.list_windows()
    if not windows:
        return _NO_WINDOWS_MSG
    win = desktop.find_window(title, windows)
    if win is None:
        return f"No window matching '{title}'. Available:\n{desktop.window_listing(windows)}"
    return win


def _resolve_target(
    window: str | None, session: str,
) -> tuple[DesktopWindow | None, BrowserManager | None, str | None]:
    if window and session != _DEFAULT_SESSION:
        return None, None, "Cannot use both window and session"
    if window:
        result = _find_desktop_window(window)
        if isinstance(result, str):
            return None, None, result
        return result, None, None
    return None, _sessions.get(session), None


_VLM_ELEMENT_PROMPT = (
    "Identify all interactive UI elements (buttons, text fields, dropdowns, "
    "checkboxes, links, menu items, tabs, sliders, icons) in this screenshot. "
    'For each element, return a JSON array with objects like: '
    '{"role": "button", "name": "OK", "x": 200, "y": 300, "w": 120, "h": 40} '
    "where x,y is the top-left corner and w,h is the size. "
    "Only include clearly visible, interactive elements."
)


def _save_to_path(path: str, data: bytes):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def _session_response(session: str, body: str) -> str:
    return f"[session: {session}]\n{body}"


def _maybe_dump(data: bytes, label: str, ext: str = "png"):
    if config.screenshot_dump_dir:
        dump_media(data, label, config.screenshot_dump_dir, ext=ext)


def _dump_and_save(data: bytes, label: str, ext: str = "png", path: str | None = None):
    _maybe_dump(data, label, ext=ext)
    if path:
        _save_to_path(path, data)


async def _vlm(
    data: bytes,
    context: str,
    query: str | None = None,
    media_type: str = "image",
    mime: str = "image/png",
) -> str:
    return await analyze_media(
        [MediaItem.from_bytes(data, media_type, mime)], context, config, query
    )


async def _media_response(
    data: bytes,
    label: str,
    context: str,
    query: str | None = None,
    path: str | None = None,
    media_type: str = "image",
    mime: str = "image/png",
    ext: str = "png",
) -> str | None:
    _dump_and_save(data, label, ext, path)
    if not query:
        return None
    return await _vlm(data, context, query, media_type, mime)


async def _detect_desktop_elements(
    win: DesktopWindow,
) -> tuple[bytes, list[DesktopElement]]:
    screenshot_bytes = desktop.capture_window(win.wid)
    context = _desktop_context(win)
    response = await _vlm(screenshot_bytes, context, _VLM_ELEMENT_PROMPT)
    elements = desktop.parse_elements_from_vlm(response)
    if elements is None:
        return screenshot_bytes, []
    desktop.store_elements(win.wid, elements)
    return screenshot_bytes, elements


def _desktop_context(win: DesktopWindow) -> str:
    return f"Desktop window: {win.name} ({win.w}x{win.h})"


async def _capture_desktop(
    win: DesktopWindow, query: str | None = None, path: str | None = None,
) -> tuple[bytes, str]:
    screenshot_bytes = desktop.capture_window(win.wid)
    context = _desktop_context(win)
    result = await _media_response(screenshot_bytes, win.name, context, query, path)
    return screenshot_bytes, result or context


async def _annotate_desktop(
    win: DesktopWindow, query: str | None = None,
) -> tuple[list[DesktopElement] | None, str]:
    screenshot_bytes, elements = await _detect_desktop_elements(win)
    if not elements:
        return None, "Could not detect elements — try screenshot with query instead"
    annotated = annotate_screenshot(screenshot_bytes, desktop.to_interactive_elements(elements))
    element_list = desktop.format_desktop_elements(elements)
    context = f"Annotated desktop window with {len(elements)} elements:\n{element_list}"
    result = await _media_response(annotated, f"annotated_{win.name}", context, query)
    return elements, result or context


def _desktop_label(win: DesktopWindow) -> str:
    return f"[window: {win.name}]"


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[None]:
    yield
    await _sessions.close_all()


mcp = FastMCP("interact-mcp", lifespan=_lifespan)


async def _capture(mgr: BrowserManager, scope: str | None = None, tab: int = 0):
    page = await mgr.get_page(tab)
    return await PageState.capture(page, config.screenshot_dump_dir, scope)


async def _annotate_page(
    mgr: BrowserManager,
    tab: int = 0,
    scope: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> tuple[bytes, list[InteractiveElement]]:
    page = await mgr.get_page(tab)
    raw_boxes = await page.evaluate(_ANNOTATE_JS, {"scope": scope, "limit": limit})
    elements = [
        InteractiveElement(
            index=i + 1,
            ref=raw["ref"],
            role=raw["tag"],
            name=raw["name"],
            x=raw["x"],
            y=raw["y"],
            width=raw["width"],
            height=raw["height"],
        )
        for i, raw in enumerate(raw_boxes)
    ]
    screenshot_bytes = await page.screenshot(type="png")
    return annotate_screenshot(screenshot_bytes, elements), elements


async def _annotate_and_describe(
    mgr: BrowserManager,
    tab: int = 0,
    scope: str | None = None,
    query: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> str:
    annotated_bytes, elements = await _annotate_page(mgr, tab, scope, limit)
    mgr.set_element_map(tab, elements)
    element_list = format_element_list(elements)
    context = (
        f"Annotated page with {len(elements)} interactive elements:\n{element_list}"
    )
    result = await _media_response(annotated_bytes, "annotated", context, query)
    return result or context


async def _analyze(state: PageState, query: str | None = None) -> str:
    return await analyze_screenshot(state, config, query)


async def _element_screenshot(
    mgr: BrowserManager,
    tab: int,
    selector: str | None,
    element: int | None,
    query: str | None = None,
    path: str | None = None,
) -> str:
    page = await mgr.get_page(tab)

    if element is not None:
        el = mgr.get_element(element, tab)
        if el is None:
            return f"Element {element} not found — run get_interactive_elements first"
        if not el.playwright_ref:
            return f"Element {element} has no ref attribute — cannot screenshot"
        locator = page.locator(el.playwright_ref)
        meta = f"[{el.index}] {el.role}: {el.name!r} ({el.width:.0f}x{el.height:.0f} at {el.x:.0f},{el.y:.0f})"
    else:
        locator = page.locator(selector)
        count = await locator.count()
        if count == 0:
            return f"No element matches '{selector}'"
        if count > 1:
            return f"'{selector}' matches {count} elements — use get_interactive_elements and element for precision"
        tag = await locator.evaluate("el => el.tagName.toLowerCase()")
        text = (await locator.inner_text())[:200]
        box = await locator.bounding_box()
        meta = f"{tag}: {text!r}"
        if box:
            meta += f" ({box['width']:.0f}x{box['height']:.0f} at {box['x']:.0f},{box['y']:.0f})"

    try:
        png_bytes = await locator.screenshot(type="png")
    except Exception as e:
        return f"Cannot screenshot element: {e}"
    result = await _media_response(png_bytes, "element", meta, query, path)
    return result or meta


async def _wait(page: Page, condition: str | None):
    if condition is None:
        return
    if condition in ("networkidle", "domcontentloaded", "load"):
        await page.wait_for_load_state(condition)
    else:
        await page.wait_for_selector(
            condition, state="visible", timeout=config.wait_timeout
        )


def _step(i: int, action_type: str, msg: str) -> str:
    return f"Step {i + 1} ({action_type}): {msg}"


@mcp.tool()
async def navigate(
    url: str,
    query: str | None = None,
    scope: str | None = None,
    wait: str | None = None,
    session: str = _DEFAULT_SESSION,
) -> str:
    """Navigate to a URL and return page content. Browser-only — requires a session, not a window.

    scope: CSS selector to restrict to a page sub-tree.
    wait: "networkidle", "load", "domcontentloaded", or a CSS selector (waits for visibility, 10s timeout).
    query: when set, returns vision analysis instead of text summary.
    """
    mgr = _sessions.get(session)
    page = await mgr.get_page()
    await page.goto(url)
    await _wait(page, wait)
    state = await _capture(mgr, scope)
    if query:
        return _session_response(session, await _analyze(state, query))
    return _session_response(session, state.text_summary())


@mcp.tool()
async def run_actions(
    actions: list[AnyAction],
    query: str | None = None,
    scope: str | None = None,
    wait: str | None = None,
    window: str | None = None,
    session: str = _DEFAULT_SESSION,
) -> str:
    """Execute a sequence of actions on a browser session or desktop window.

    Default: operates on browser session "default".
    With window: operates on a desktop window by title (use list_desktop_windows to discover).
    window and session are mutually exclusive.

    Each action needs a 'type' key to select the action model.

    Mutating: click, type_text, scroll, drag, navigate, evaluate_js, upload_file, key_press, click_element
    Observations: screenshot, wait_for, http_request, hover, annotate
    Tab control: new_tab, switch_tab, close_tab

    Browser-only actions (navigate, evaluate_js, wait_for, upload_file, new_tab, switch_tab, close_tab) error when used with window.

    Any action can include 'wait' to wait after execution (networkidle, load, domcontentloaded, or a CSS selector — browser only).

    scope: CSS selector to restrict the final capture to a page sub-tree (browser only).
    wait: after all actions, wait for a condition (browser only).
    query: when set, returns vision analysis of the final state instead of text summary.
    """
    win, mgr, err = _resolve_target(window, session)
    if err:
        return err
    if win:
        return await _run_actions_desktop(win, actions, query)
    return await _run_actions_browser(mgr, actions, query, scope, wait, session)
async def _run_actions_desktop(
    win: DesktopWindow,
    actions: list[AnyAction],
    query: str | None,
) -> str:
    wid = win.wid
    label = _desktop_label(win)
    step_reports: list[str] = []

    for i, action in enumerate(actions):
        if action.type in BROWSER_ONLY_ACTIONS:
            step_reports.append(
                _step(i, action.type, f"Action '{action.type}' is browser-only — use a session instead of window")
            )
            continue

        if isinstance(action, ClickAction):
            if action.x is not None and action.y is not None:
                await desktop.desktop_click(wid, action.x, action.y)
            elif action.ref:
                idx = desktop.ref_to_index(action.ref)
                el = desktop.get_element(wid, idx)
                if el is None:
                    step_reports.append(_step(i, action.type, f"Element {idx} not found — run get_interactive_elements first"))
                    continue
                await desktop.desktop_click(wid, el.center_x, el.center_y)
            elif action.selector:
                step_reports.append(_step(i, action.type, "CSS selectors not supported on desktop — use x,y coordinates"))
                continue
            step_reports.append(_step(i, action.type, "clicked"))

        elif isinstance(action, ClickElementAction):
            el = desktop.get_element(wid, action.element)
            if el is None:
                step_reports.append(_step(i, action.type, f"Element {action.element} not found — run get_interactive_elements first"))
                continue
            await desktop.desktop_click(wid, el.center_x, el.center_y)
            step_reports.append(_step(i, action.type, f"clicked [{el.index}] {el.role}: {el.name!r}"))

        elif isinstance(action, HoverAction):
            if action.x is not None and action.y is not None:
                await desktop.desktop_hover(wid, action.x, action.y)
            elif action.ref:
                idx = desktop.ref_to_index(action.ref)
                el = desktop.get_element(wid, idx)
                if el is None:
                    step_reports.append(_step(i, action.type, f"Element {idx} not found"))
                    continue
                await desktop.desktop_hover(wid, el.center_x, el.center_y)
            else:
                step_reports.append(_step(i, action.type, "Provide x,y or ref for desktop hover"))
                continue
            step_reports.append(_step(i, action.type, "hovered"))

        elif isinstance(action, TypeTextAction):
            if action.ref:
                idx = desktop.ref_to_index(action.ref)
                el = desktop.get_element(wid, idx)
                if el is None:
                    step_reports.append(_step(i, action.type, f"Element {idx} not found"))
                    continue
                await desktop.desktop_click(wid, el.center_x, el.center_y)
            if action.clear_first:
                await desktop.desktop_key(wid, "ctrl+a")
                await desktop.desktop_key(wid, "Delete")
            await desktop.desktop_type(wid, action.text)
            step_reports.append(_step(i, action.type, f"typed {len(action.text)} chars"))

        elif isinstance(action, KeyPressAction):
            await desktop.desktop_key(wid, action.key)
            step_reports.append(_step(i, action.type, f"pressed {action.key}"))

        elif isinstance(action, ScrollAction):
            await desktop.desktop_scroll(wid, win.w // 2, win.h // 2, action.direction, action.amount)
            step_reports.append(_step(i, action.type, f"scrolled {action.direction} x{action.amount}"))

        elif isinstance(action, DragAction):
            fx, fy = action.from_x, action.from_y
            tx, ty = action.to_x, action.to_y
            if action.from_ref:
                idx = desktop.ref_to_index(action.from_ref)
                el = desktop.get_element(wid, idx)
                if el is None:
                    step_reports.append(_step(i, action.type, f"from_ref element {idx} not found"))
                    continue
                fx, fy = el.center_x, el.center_y
            if action.to_ref:
                idx = desktop.ref_to_index(action.to_ref)
                el = desktop.get_element(wid, idx)
                if el is None:
                    step_reports.append(_step(i, action.type, f"to_ref element {idx} not found"))
                    continue
                tx, ty = el.center_x, el.center_y
            await desktop.desktop_drag(wid, fx, fy, tx, ty, action.steps)
            step_reports.append(_step(i, action.type, f"dragged ({fx},{fy})->({tx},{ty})"))

        elif isinstance(action, ScreenshotAction):
            _, report = await _capture_desktop(win, action.query)
            step_reports.append(_step(i, action.type, report))

        elif isinstance(action, AnnotateAction):
            _, report = await _annotate_desktop(win, action.query)
            step_reports.append(_step(i, action.type, report))

        elif isinstance(action, HttpRequestAction):
            result = await action.execute(None)
            step_reports.append(_step(i, action.type, str(result)))

        else:
            step_reports.append(_step(i, action.type, f"Action '{action.type}' not supported on desktop"))

        await asyncio.sleep(0.1)

    if query:
        _, final_summary = await _capture_desktop(win, query)
    else:
        final_summary = f"{win.name} ({win.w}x{win.h})"

    return f"{label}\n" + "\n".join(step_reports) + f"\n\n---\nFinal state: {final_summary}"


async def _run_actions_browser(
    mgr: BrowserManager,
    actions: list[AnyAction],
    query: str | None,
    scope: str | None,
    wait: str | None,
    session: str,
) -> str:
    current_tab = 0
    page = await mgr.get_page(current_tab)
    step_reports: list[str] = []
    final: PageState | None = None

    for i, action in enumerate(actions):
        if isinstance(action, NewTabAction):
            idx = await mgr.new_tab(action.url)
            current_tab = idx
            page = await mgr.get_page(current_tab)
            step_reports.append(_step(i, action.type, f"opened tab {idx}"))
            continue

        if isinstance(action, SwitchTabAction):
            current_tab = action.index
            page = await mgr.get_page(current_tab)
            step_reports.append(
                _step(i, action.type, f"switched to tab {action.index}")
            )
            continue

        if isinstance(action, CloseTabAction):
            idx = action.index if action.index is not None else mgr.tab_count - 1
            await mgr.close_tab(idx)
            step_reports.append(_step(i, action.type, f"closed tab {idx}"))
            if idx == current_tab:
                current_tab = max(0, current_tab - 1)
                page = await mgr.get_page(current_tab)
            elif idx < current_tab:
                current_tab -= 1
            continue

        if isinstance(action, AnnotateAction):
            report = await _annotate_and_describe(
                mgr, current_tab, action.scope, action.query, action.limit
            )
            step_reports.append(_step(i, action.type, report))
            final = await _capture(mgr, scope=action.scope, tab=current_tab)
            continue

        if isinstance(action, ClickElementAction):
            el = mgr.get_element(action.element, current_tab)
            if el is None:
                step_reports.append(
                    _step(
                        i,
                        action.type,
                        f"Element {action.element} not found — run annotate first",
                    )
                )
                continue
            before = await _capture(mgr, tab=current_tab)
            if el.ref:
                await page.locator(el.playwright_ref).click()
            else:
                await page.mouse.click(el.center_x, el.center_y)
            if action.wait:
                await _wait(page, action.wait)
            final = await _capture(mgr, tab=current_tab)
            change = StateChange.compute(before, final)
            step_reports.append(_step(i, action.type, change.description))
            continue

        if isinstance(action, ScreenshotAction):
            if action.element is not None or action.selector is not None:
                report = await _element_screenshot(
                    mgr, current_tab, action.selector, action.element, action.query
                )
            else:
                state = await _capture(mgr, action.scope, current_tab)
                if action.query:
                    report = await _analyze(state, action.query)
                else:
                    report = f"{state.title} — {state.visible_text[:300]}"
                final = state
            step_reports.append(_step(i, action.type, report))
            continue

        if not action.mutates:
            result = await action.execute(page)
            step_reports.append(_step(i, action.type, str(result)))
            continue

        before = await _capture(mgr, tab=current_tab)
        result = await action.execute(page)
        if action.wait:
            await _wait(page, action.wait)
        final = await _capture(mgr, tab=current_tab)
        change = StateChange.compute(before, final)
        entry = _step(i, action.type, change.description)
        if result is not None:
            entry += f"\n  result: {result}"
        step_reports.append(entry)

    if final is None:
        final = await _capture(mgr, scope, current_tab)
    elif wait:
        await _wait(page, wait)
        final = await _capture(mgr, scope, current_tab)
    elif scope:
        final = await _capture(mgr, scope, current_tab)
    if query:
        final_summary = await _analyze(final, query)
    else:
        final_summary = f"{final.title} — {final.url}\n{final.visible_text[:500]}"

    return _session_response(
        session, "\n".join(step_reports) + f"\n\n---\nFinal state: {final_summary}"
    )


@mcp.tool()
async def screenshot(
    query: str | None = None,
    scope: str | None = None,
    selector: str | None = None,
    element: int | None = None,
    path: str | None = None,
    window: str | None = None,
    session: str = _DEFAULT_SESSION,
) -> str:
    """Capture the current page or a desktop window.

    Default: operates on browser session "default".
    With window: captures a desktop window by title (use list_desktop_windows to discover).
    window and session are mutually exclusive.

    Returns depend on parameters:
    - No selector/element, no query: page title + visible text content (browser) or window metadata (desktop).
    - No selector/element, with query: full screenshot analyzed by VLM.
    - With selector/element, no query: element metadata (browser only).
    - With selector/element, with query: cropped element screenshot analyzed by VLM (browser only).

    element: integer index from get_interactive_elements (priority over selector).
    selector: CSS selector targeting one element (browser only).
    query: question for VLM visual analysis of the captured content.
    scope: CSS selector to restrict text extraction to a sub-tree (browser only).
    path: save the PNG screenshot to this file path.
    """
    win, mgr, err = _resolve_target(window, session)
    if err:
        return err
    if win:
        _, description = await _capture_desktop(win, query, path)
        return f"{_desktop_label(win)}\n{description}"
    if element is not None or selector is not None:
        return _session_response(
            session, await _element_screenshot(mgr, 0, selector, element, query, path)
        )
    state = await _capture(mgr, scope)
    if path:
        png_bytes = base64.b64decode(state.screenshot_base64)
        _save_to_path(path, png_bytes)
    if query:
        return _session_response(session, await _analyze(state, query))
    return _session_response(session, state.text_summary())


@mcp.tool()
async def get_interactive_elements(
    scope: str | None = None,
    query: str | None = None,
    limit: int = DEFAULT_LIMIT,
    tab: int = 0,
    window: str | None = None,
    session: str = _DEFAULT_SESSION,
) -> str:
    """Annotate interactive elements with numbered badges and return their details.

    Default: operates on browser session "default". Sets data-interact-ref attributes on DOM elements.
    With window: uses VLM to detect interactive elements in a desktop window screenshot.
    window and session are mutually exclusive. Use list_desktop_windows to discover windows.

    Returns a numbered list with role/name for each element.
    Use element indices in subsequent click_element actions, or ref values for click/type_text/hover (browser only).
    scope: CSS selector to restrict to a page sub-tree (browser only).
    limit: Maximum number of elements to return (browser only).
    With query, also returns a vision analysis of the annotated screenshot.
    """
    win, mgr, err = _resolve_target(window, session)
    if err:
        return err
    if win:
        _, report = await _annotate_desktop(win, query)
        return f"{_desktop_label(win)}\n{report}"
    return _session_response(
        session, await _annotate_and_describe(mgr, tab, scope, query, limit)
    )


@mcp.tool()
async def get_page_state(
    scope: str | None = None, session: str = _DEFAULT_SESSION
) -> str:
    """Get current page URL, title, accessibility tree, focused element, and visible text. scope: CSS selector to restrict to a page sub-tree."""
    mgr = _sessions.get(session)
    state = await _capture(mgr, scope)
    return _session_response(
        session,
        f"URL: {state.url}\n"
        f"Title: {state.title}\n"
        f"Focused: {state.focused_element}\n\n"
        f"Accessibility Tree:\n{state.accessibility_tree}\n\n"
        f"Visible Text:\n{state.visible_text}",
    )


@mcp.tool()
async def list_sessions() -> str:
    """List all active browser sessions."""
    sessions = _sessions.active()
    if not sessions:
        return "No active sessions."
    return "\n".join(f"  {s}" for s in sessions)


@mcp.tool()
async def close_session(session: str = _DEFAULT_SESSION) -> str:
    """Close a browser session and free its resources."""
    await _sessions.close(session)
    return _session_response(session, f"Session '{session}' closed.")


@mcp.tool()
async def save_session(path: str, session: str = _DEFAULT_SESSION) -> str:
    """Export cookies and localStorage to a file for later restoration."""
    mgr = _sessions.get(session)
    state = await mgr.save_state()
    Path(path).write_text(json.dumps(state))
    return _session_response(session, f"Session '{session}' saved to {path}.")


@mcp.tool()
async def load_session(path: str, session: str = _DEFAULT_SESSION) -> str:
    """Restore cookies and localStorage from a previously saved session file."""
    state = json.loads(Path(path).read_text())
    mgr = _sessions.get(session)
    await mgr.load_state(state)
    return _session_response(session, f"Session '{session}' restored from {path}.")


@mcp.tool()
async def download_asset(url: str, path: str, session: str = _DEFAULT_SESSION) -> str:
    """Download a URL to a local file path. Uses the browser session's cookies for authenticated downloads."""
    mgr = _sessions.get(session)
    page = await mgr.get_page()
    response = await page.context.request.get(url)
    data = await response.body()
    _save_to_path(path, data)
    return _session_response(session, f"Downloaded {len(data)} bytes to {path}")


@mcp.tool()
async def get_network_log(
    clear: bool = False, limit: int = DEFAULT_LIMIT, session: str = _DEFAULT_SESSION
) -> str:
    """Return captured network requests (last `limit` entries). Set clear=True to flush the log after reading."""
    mgr = _sessions.get(session)
    entries = mgr.drain_network_log(clear)
    entries = entries[-limit:]
    if not entries:
        return _session_response(session, "No network requests captured.")
    lines = []
    for e in entries:
        status = e.get("status", "pending")
        ctype = e.get("content_type", "")
        lines.append(
            f"{e['method']} {status} {e['url']}" + (f" ({ctype})" if ctype else "")
        )
    return _session_response(session, "\n".join(lines))


@mcp.tool()
async def get_console_log(
    clear: bool = False, limit: int = DEFAULT_LIMIT, session: str = _DEFAULT_SESSION
) -> str:
    """Return captured browser console messages and errors (last `limit` entries). Set clear=True to flush after reading."""
    mgr = _sessions.get(session)
    entries = mgr.drain_console_log(clear)
    entries = entries[-limit:]
    if not entries:
        return _session_response(session, "No console messages captured.")
    lines = [f"[{e['level']}] {e['text']}" for e in entries]
    return _session_response(session, "\n".join(lines))


@mcp.tool()
async def list_desktop_windows() -> str:
    """List all visible desktop windows."""
    windows = desktop.list_windows()
    if not windows:
        return _NO_WINDOWS_MSG
    return desktop.window_listing(windows)


@mcp.tool()
async def record(
    start: bool = True,
    query: str | None = None,
    duration: float | None = None,
    fps: int | None = None,
    path: str | None = None,
    window: str | None = None,
    session: str = _DEFAULT_SESSION,
) -> str:
    """Record actions as video and optionally analyze with vision.

    Browser (session): Two-step — record(start=True) then perform actions then record(start=False).
    Desktop (window): Records for duration seconds, then returns.
    window and session are mutually exclusive. Use list_desktop_windows to discover windows.

    start: True to begin recording, False to stop and export (browser only).
    query: question for VLM visual analysis of the recording.
    duration: recording length in seconds (desktop only, default from config).
    fps: frames per second (desktop only, default from config).
    path: save the video file to this path.
    """
    win, mgr, err = _resolve_target(window, session)
    if err:
        return err
    if win:
        return await _record_desktop(win, query, duration, fps, path)
    return await _record_browser(mgr, start, query, path, session)


async def _record_desktop(
    win: DesktopWindow,
    query: str | None,
    duration: float | None,
    fps: int | None,
    path: str | None,
) -> str:
    dur = duration or config.video_duration
    actual_fps = fps or config.video_fps
    video_bytes = desktop.capture_window_video(win.wid, dur, actual_fps)
    _dump_and_save(video_bytes, f"video_{win.name}", "mp4", path)

    is_static = not desktop.detect_motion(video_bytes)
    if is_static and not query:
        return (
            f"Recording captured but no motion detected — frames are identical. "
            f"The window content did not change during the {dur}s recording."
        )

    context = f"Desktop window recording: {win.name} ({win.w}x{win.h}, {dur}s)"
    if is_static:
        context = (
            "WARNING: Recording appears static — no significant motion was detected "
            "between frames. Describe only what you actually observe.\n" + context
        )
    return await _vlm(video_bytes, context, query, "video", "video/mp4")


async def _record_browser(
    mgr: BrowserManager,
    start: bool,
    query: str | None,
    path: str | None,
    session: str,
) -> str:
    if start:
        url = await mgr.start_recording()
        return _session_response(session, f"Recording started. Current URL: {url}")
    video_bytes = await mgr.stop_recording()
    if not video_bytes:
        return _session_response(
            session, "Recording stopped but no video data captured."
        )
    result = await _media_response(
        video_bytes,
        "browser_recording",
        "Browser recording",
        query,
        path,
        "video",
        "video/webm",
        "webm",
    )
    if result:
        return _session_response(session, result)
    size = len(video_bytes)
    msg = f"Recording stopped. Video captured ({size} bytes)."
    if path:
        msg += f" Saved to {path}."
    return _session_response(session, msg)


def main():
    mcp.run(transport="stdio")
