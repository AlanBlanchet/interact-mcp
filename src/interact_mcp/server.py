import base64
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from playwright.async_api import Page

from interact_mcp import desktop
from interact_mcp.actions import AnyAction, ScreenshotAction
from interact_mcp.browser import BrowserManager
from interact_mcp.config import Config
from interact_mcp.state import PageState, StateChange, dump_screenshot
from interact_mcp.vision import analyze_images, analyze_screenshot

config = Config()
browser = BrowserManager(config)
_NO_WINDOWS_MSG = "No desktop windows detected (X11/maim required)."


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[None]:
    yield
    await browser.close()


mcp = FastMCP("interact-mcp", lifespan=_lifespan)


async def _capture(page: Page | None = None, scope: str | None = None):
    if page is None:
        page = await browser.get_page()
    return await PageState.capture(page, config.screenshot_dump_dir, scope)


async def _analyze(state: PageState, query: str | None = None) -> str:
    return await analyze_screenshot(state, config, query)


async def _wait(page: Page, condition: str | None):
    if condition is None:
        return
    if condition in ("networkidle", "domcontentloaded", "load"):
        await page.wait_for_load_state(condition)
    else:
        await page.wait_for_selector(condition, state="visible", timeout=10000)


@mcp.tool()
async def navigate(
    url: str,
    query: str | None = None,
    scope: str | None = None,
    wait: str | None = None,
) -> str:
    """Navigate to a URL and return page content. Use scope to focus on an element, wait to wait for a condition, query for vision analysis."""
    page = await browser.get_page()
    await page.goto(url)
    await _wait(page, wait)
    state = await _capture(page, scope)
    if query:
        return await _analyze(state, query)
    return state.text_summary()


@mcp.tool()
async def run_actions(
    actions: list[AnyAction],
    query: str | None = None,
    scope: str | None = None,
    wait: str | None = None,
) -> str:
    """Execute a sequence of browser actions and return per-step feedback.

    Each action needs a 'type' key to select the action model.

    Mutating: click, type_text, scroll, drag, navigate, evaluate_js
    Observations: screenshot, wait_for, list_clickable

    Any action can include 'wait' to wait after execution (networkidle, load, or a CSS selector).
    """
    page = await browser.get_page()
    step_reports: list[str] = []
    final: PageState | None = None

    for i, action in enumerate(actions):
        if isinstance(action, ScreenshotAction):
            state = await _capture(page, action.scope)
            if action.query:
                report = await _analyze(state, action.query)
            else:
                report = f"{state.title} — {state.visible_text[:300]}"
            step_reports.append(f"Step {i + 1} ({action.type}): {report}")
            final = state
            continue

        if not action.mutates:
            result = await action.execute(page)
            step_reports.append(f"Step {i + 1} ({action.type}): {result}")
            continue

        before = await _capture(page)
        result = await action.execute(page)
        if action.wait:
            await _wait(page, action.wait)
        final = await _capture(page)
        change = StateChange.compute(before, final)
        report = f"Step {i + 1} ({action.type}): {change.description}"
        if result is not None:
            report += f"\n  result: {result}"
        step_reports.append(report)

    if final is None:
        final = await _capture(page, scope)
    elif wait:
        await _wait(page, wait)
        final = await _capture(page, scope)
    elif scope:
        final = await _capture(page, scope)
    if query:
        final_summary = await _analyze(final, query)
    else:
        final_summary = f"{final.title} — {final.url}\n{final.visible_text[:500]}"

    return "\n".join(step_reports) + f"\n\n---\nFinal state: {final_summary}"


@mcp.tool()
async def screenshot(query: str | None = None, scope: str | None = None) -> str:
    """Capture the current page or a scoped element. With query, returns vision analysis."""
    state = await _capture(scope=scope)
    return await _analyze(state, query)


@mcp.tool()
async def get_page_state(scope: str | None = None) -> str:
    """Get current page URL, title, accessibility tree, focused element, and visible text."""
    state = await _capture(scope=scope)
    return (
        f"URL: {state.url}\n"
        f"Title: {state.title}\n"
        f"Focused: {state.focused_element}\n\n"
        f"Accessibility Tree:\n{state.accessibility_tree}\n\n"
        f"Visible Text:\n{state.visible_text}"
    )


@mcp.tool()
async def list_desktop_windows() -> str:
    """List all visible desktop windows."""
    windows = desktop.list_windows()
    if not windows:
        return _NO_WINDOWS_MSG
    return desktop.window_listing(windows)


@mcp.tool()
async def analyze_window(title: str, query: str | None = None) -> str:
    """Capture a desktop window by title substring and analyze with vision.

    Works on X11. Captures the window screenshot and sends it for analysis.
    """
    windows = desktop.list_windows()
    if not windows:
        return _NO_WINDOWS_MSG
    win = desktop.find_window(title, windows)
    if win is None:
        return f"No window matching '{title}'. Available:\n{desktop.window_listing(windows)}"

    screenshot_bytes = desktop.capture_window(win.wid)
    screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

    if config.screenshot_dump_dir:
        dump_screenshot(screenshot_bytes, win.name, config.screenshot_dump_dir)

    context = f"Desktop window: {win.name} ({win.w}x{win.h})"
    return await analyze_images([screenshot_b64], context, config, query)


def main():
    mcp.run(transport="stdio")
