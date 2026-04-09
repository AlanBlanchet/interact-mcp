import base64
import functools
import inspect
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Literal

from mcp.server.fastmcp import FastMCP
from playwright.async_api import Page

from interact_mcp import desktop
from interact_mcp.browser import BrowserManager
from interact_mcp.config import Config
from interact_mcp.state import PageState, StateChange, dump_screenshot
from interact_mcp.vision import analyze_change, analyze_images, analyze_screenshot

config = Config()
browser = BrowserManager(config)
_NO_WINDOWS_MSG = "No desktop windows detected (X11/maim required)."


@asynccontextmanager
async def _lifespan(_: FastMCP) -> AsyncIterator[None]:
    yield
    await browser.close()


mcp = FastMCP("interact-mcp", lifespan=_lifespan)


async def _capture(page: Page | None = None):
    if page is None:
        page = await browser.get_page()
    return page, await PageState.capture(page, config.screenshot_dump_dir)


def _tracked(fn=None, *, include_result=False):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(**kwargs):
            query = kwargs.pop("query", None)
            page, before = await _capture()
            result = await fn(page, **kwargs)
            _, after = await _capture(page)
            change = StateChange.compute(before, after)
            summary = await analyze_change(change, config, query)
            if include_result:
                return f"Result: {result}\n\n{summary}"
            return summary

        sig = inspect.signature(fn)
        params = [p for n, p in sig.parameters.items() if n != "page"]
        query_param = inspect.Parameter(
            "query", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=str | None
        )
        params.append(query_param)
        wrapper.__signature__ = sig.replace(parameters=params)
        return wrapper

    if fn is not None:
        return decorator(fn)
    return decorator


@mcp.tool()
async def navigate(url: str, query: str | None = None) -> str:
    page = await browser.get_page()
    await page.goto(url)
    _, state = await _capture(page)
    if query and config.vision_api_key:
        return await analyze_screenshot(state, config, query)
    return f"{state.title}\n\n{state.visible_text}"


@mcp.tool()
@_tracked
async def click(page: Page, selector: str | None = None, x: int | None = None, y: int | None = None):
    await _execute_action(page, {"type": "click", "selector": selector, "x": x, "y": y})


@mcp.tool()
@_tracked
async def type_text(page: Page, selector: str, text: str, clear_first: bool = True):
    await _execute_action(page, {"type": "type_text", "selector": selector, "text": text, "clear_first": clear_first})


SCROLL_DELTA = {"down": (0, 300), "up": (0, -300), "right": (300, 0), "left": (-300, 0)}


@mcp.tool()
@_tracked
async def scroll(page: Page, direction: Literal["down", "up", "right", "left"] = "down", amount: int = 3):
    await _execute_action(page, {"type": "scroll", "direction": direction, "amount": amount})


@mcp.tool()
@_tracked
async def drag(page: Page, from_x: int, from_y: int, to_x: int, to_y: int):
    await _execute_action(page, {"type": "drag", "from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y})


@mcp.tool()
async def screenshot(query: str | None = None) -> str:
    _, state = await _capture()
    return await analyze_screenshot(state, config, query)


@mcp.tool()
@_tracked(include_result=True)
async def evaluate_js(page: Page, script: str):
    return await _execute_action(page, {"type": "evaluate_js", "script": script})


@mcp.tool()
async def get_page_state() -> str:
    _, state = await _capture()
    return (
        f"URL: {state.url}\n"
        f"Title: {state.title}\n"
        f"Focused: {state.focused_element}\n\n"
        f"Accessibility Tree:\n{state.accessibility_tree}\n\n"
        f"Visible Text:\n{state.visible_text}"
    )


async def _execute_action(page: Page, action: dict):
    action_type = action["type"]
    if action_type == "navigate":
        await page.goto(action["url"])
    elif action_type == "click":
        if action.get("selector"):
            await page.click(action["selector"])
        elif action.get("x") is not None:
            await page.mouse.click(action["x"], action["y"])
        else:
            raise ValueError("Provide either selector or both x and y coordinates")
    elif action_type == "type_text":
        if action.get("clear_first", True):
            await page.fill(action["selector"], action["text"])
        else:
            await page.type(action["selector"], action["text"])
    elif action_type == "scroll":
        dx, dy = SCROLL_DELTA[action.get("direction", "down")]
        for _ in range(action.get("amount", 3)):
            await page.mouse.wheel(dx, dy)
    elif action_type == "drag":
        await page.mouse.move(action["from_x"], action["from_y"])
        await page.mouse.down()
        await page.mouse.move(action["to_x"], action["to_y"])
        await page.mouse.up()
    elif action_type == "evaluate_js":
        return await page.evaluate(action["script"])
    else:
        raise ValueError(f"Unknown action type: {action_type}")


@mcp.tool()
async def run_actions(actions: list[dict], query: str | None = None) -> str:
    """Execute multiple browser actions in sequence.

    Each action dict has a 'type' key: navigate, click, type_text, scroll, drag, evaluate_js.
    navigate: url. click: selector OR x+y coordinates. type_text: selector, text, clear_first.
    scroll: direction (down/up/right/left), amount. drag: from_x, from_y, to_x, to_y.
    evaluate_js: script.

    Returns per-step change summaries plus a final state description.
    If query is provided and vision is configured, the final state is analyzed with that prompt.
    """
    page = await browser.get_page()
    step_reports: list[str] = []
    final: PageState | None = None

    for i, action in enumerate(actions):
        action_type = action.get("type", "")
        _, before = await _capture(page)
        result = await _execute_action(page, action)
        _, final = await _capture(page)
        change = StateChange.compute(before, final)
        report = f"Step {i + 1} ({action_type}): {change.description}"
        if result is not None:
            report += f"\n  result: {result}"
        step_reports.append(report)

    if final is None:
        _, final = await _capture(page)
    if query:
        final_summary = await analyze_screenshot(final, config, query)
    else:
        final_summary = f"{final.title} — {final.url}\n{final.visible_text[:500]}"

    return "\n".join(step_reports) + f"\n\n---\nFinal state: {final_summary}"


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
