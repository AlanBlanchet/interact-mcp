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
    ClickElementAction,
    CloseTabAction,
    NewTabAction,
    ScreenshotAction,
    SwitchTabAction,
)
from interact_mcp.browser import BrowserManager, SessionRegistry
from interact_mcp.config import DEFAULT_LIMIT, Config
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


def _session_response(session: str, body: str) -> str:
    return f"[session: {session}]\n{body}"


def _maybe_dump(data: bytes, label: str, ext: str = "png"):
    if config.screenshot_dump_dir:
        dump_media(data, label, config.screenshot_dump_dir, ext=ext)


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
    _maybe_dump(annotated_bytes, "annotated")
    element_list = format_element_list(elements)
    context = (
        f"Annotated page with {len(elements)} interactive elements:\n{element_list}"
    )
    if query:
        media = [MediaItem.from_bytes(annotated_bytes)]
        return await analyze_media(media, context, config, query)
    return context


async def _analyze(state: PageState, query: str | None = None) -> str:
    return await analyze_screenshot(state, config, query)


async def _wait(page: Page, condition: str | None):
    if condition is None:
        return
    if condition in ("networkidle", "domcontentloaded", "load"):
        await page.wait_for_load_state(condition)
    else:
        await page.wait_for_selector(condition, state="visible", timeout=10000)


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
    """Navigate to a URL and return page content.

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
    session: str = _DEFAULT_SESSION,
) -> str:
    """Execute a sequence of browser actions and return per-step feedback.

    Each action needs a 'type' key to select the action model.

    Mutating: click, type_text, scroll, drag, navigate, evaluate_js, upload_file, key_press, click_element
    Observations: screenshot, wait_for, http_request, hover, annotate
    Tab control: new_tab, switch_tab, close_tab

    Any action can include 'wait' to wait after execution (networkidle, load, domcontentloaded, or a CSS selector).

    scope: CSS selector to restrict the final capture to a page sub-tree.
    wait: after all actions, wait for a condition (networkidle, load, domcontentloaded, or a CSS selector).
    query: when set, returns vision analysis of the final state instead of text summary.
    """
    mgr = _sessions.get(session)
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
            state = await _capture(mgr, action.scope, current_tab)
            if action.query:
                report = await _analyze(state, action.query)
            else:
                report = f"{state.title} — {state.visible_text[:300]}"
            step_reports.append(_step(i, action.type, report))
            final = state
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
    query: str | None = None, scope: str | None = None, session: str = _DEFAULT_SESSION
) -> str:
    """Capture the current page. Returns text page state (title, URL, visible text). With query, takes a screenshot and returns VLM visual analysis. scope: CSS selector to restrict to a sub-tree."""
    mgr = _sessions.get(session)
    state = await _capture(mgr, scope)
    if query:
        return _session_response(session, await _analyze(state, query))
    return _session_response(session, state.text_summary())


@mcp.tool()
async def get_interactive_elements(
    scope: str | None = None,
    query: str | None = None,
    limit: int = DEFAULT_LIMIT,
    tab: int = 0,
    session: str = _DEFAULT_SESSION,
) -> str:
    """Annotate the page with numbered interactive elements and return their refs.

    Sets data-interact-ref attributes (e.g. e1, e2) on each element and overlays numbered badges on a screenshot.
    Returns a numbered list with ref, role, and name for each element.
    Use ref values in subsequent click, type_text, hover, drag, or upload_file actions.
    scope: CSS selector to restrict to a page sub-tree.
    limit: Maximum number of elements to return.
    With query, also returns a vision analysis of the annotated screenshot.
    """
    mgr = _sessions.get(session)
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
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(data)
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
async def analyze_window(title: str, query: str | None = None) -> str:
    """Capture a desktop window by title substring and analyze with vision. title: partial match of the window title (e.g. 'Firefox', 'Terminal'). query: what to look for or describe in the window. Works on X11."""
    result = _find_desktop_window(title)
    if isinstance(result, str):
        return result
    win = result

    screenshot_bytes = desktop.capture_window(win.wid)
    _maybe_dump(screenshot_bytes, win.name)

    context = f"Desktop window: {win.name} ({win.w}x{win.h})"
    media = [MediaItem.from_bytes(screenshot_bytes)]
    return await analyze_media(media, context, config, query)


@mcp.tool()
async def record_window(
    title: str,
    query: str | None = None,
    duration: float | None = None,
    path: str | None = None,
) -> str:
    """Record a short video of a desktop window and analyze with vision.

    Works on X11 with ffmpeg. Records for a few seconds, then sends for video analysis.
    If path is provided, also saves the mp4 to that file path.
    """
    result = _find_desktop_window(title)
    if isinstance(result, str):
        return result
    win = result

    dur = duration or config.video_duration
    video_bytes = desktop.capture_window_video(win.wid, dur, config.video_fps)
    _maybe_dump(video_bytes, f"video_{win.name}", ext="mp4")
    if path:
        Path(path).write_bytes(video_bytes)

    context = f"Desktop window recording: {win.name} ({win.w}x{win.h}, {dur}s)"
    media = [MediaItem.from_bytes(video_bytes, "video", "video/mp4")]
    return await analyze_media(media, context, config, query)


def main():
    mcp.run(transport="stdio")
