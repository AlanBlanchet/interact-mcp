import base64
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP
from playwright.async_api import Page

from interact_mcp import desktop
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
    return page, await PageState.capture(page, config.screenshot_dump_dir, scope)


async def _wait(page: Page, condition: str | None):
    if condition is None:
        return
    if condition in ("networkidle", "domcontentloaded", "load"):
        await page.wait_for_load_state(condition)
    else:
        await page.wait_for_selector(condition, state="visible", timeout=10000)


SCROLL_DELTA = {"down": (0, 300), "up": (0, -300), "right": (300, 0), "left": (-300, 0)}


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


async def _list_clickable(page: Page, scope: str | None = None) -> str:
    elements = await page.evaluate(
        """(scopeSelector) => {
        const root = scopeSelector ? document.querySelector(scopeSelector) : document;
        if (!root) return [];
        const items = root.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"], [onclick]');
        return Array.from(items).slice(0, 100).map((el, i) => {
            const tag = el.tagName.toLowerCase();
            const text = (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80);
            const type = el.type || '';
            const href = el.href || '';

            let selector = '';
            if (el.id) selector = '#' + el.id;
            else if (el.getAttribute('data-testid')) selector = `[data-testid="${el.getAttribute('data-testid')}"]`;
            else if (el.name) selector = `${tag}[name="${el.name}"]`;
            else if (text && tag === 'button') selector = `button:has-text("${text.slice(0, 30)}")`;
            else if (text && tag === 'a') selector = `a:has-text("${text.slice(0, 30)}")`;
            else {
                const classes = Array.from(el.classList).slice(0, 2).join('.');
                selector = classes ? `${tag}.${classes}` : `${tag}:nth-of-type(${i + 1})`;
            }

            return { tag, selector, text, type, href };
        });
    }""",
        scope,
    )

    if not elements:
        return "No interactive elements found." + (
            f" (scoped to '{scope}')" if scope else ""
        )

    lines = []
    for el in elements:
        parts = [el["tag"]]
        if el["type"]:
            parts.append(f"type={el['type']}")
        if el["text"]:
            parts.append(f'"{el["text"]}"')
        if el["href"]:
            parts.append(f"-> {el['href'][:60]}")
        lines.append(f"  {el['selector']}  [{' | '.join(parts)}]")

    return "\n".join(lines)


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
    _, state = await _capture(page, scope)
    if query and config.vision_api_key:
        return await analyze_screenshot(state, config, query)
    return f"{state.title}\n\n{state.visible_text}"


@mcp.tool()
async def run_actions(
    actions: list[dict],
    query: str | None = None,
    scope: str | None = None,
    wait: str | None = None,
) -> str:
    """Execute a sequence of browser actions and return per-step feedback.

    Each action dict needs a 'type' key. Available types:

    Actions (mutate page):
      click:       selector OR x+y coordinates
      type_text:   selector, text, clear_first (default true)
      scroll:      direction (down/up/left/right), amount (default 3)
      drag:        from_x, from_y, to_x, to_y
      navigate:    url
      evaluate_js: script

    Observations (read page, no mutation):
      screenshot:     scope (optional CSS selector to focus on), query (optional)
      wait_for:       selector, state (visible/hidden/attached/detached), timeout (ms)
      list_clickable: scope (optional CSS selector)

    Any action can include 'wait' to wait after execution (networkidle, load, or a CSS selector).

    Parameters:
      actions: list of action dicts
      query: vision prompt for final state analysis
      scope: CSS selector to scope the final screenshot
      wait: wait condition after the last action
    """
    page = await browser.get_page()
    step_reports: list[str] = []
    final: PageState | None = None

    for i, action in enumerate(actions):
        action_type = action.get("type", "")
        scope_override = action.get("scope")

        if action_type == "screenshot":
            _, state = await _capture(page, scope_override)
            if action.get("query") and config.vision_api_key:
                report = f"Step {i + 1} (screenshot): {await analyze_screenshot(state, config, action['query'])}"
            else:
                report = f"Step {i + 1} (screenshot): {state.title} — {state.visible_text[:300]}"
            step_reports.append(report)
            final = state
            continue

        if action_type == "list_clickable":
            result = await _list_clickable(page, scope_override)
            step_reports.append(f"Step {i + 1} (list_clickable):\n{result}")
            continue

        if action_type == "wait_for":
            await page.wait_for_selector(
                action["selector"],
                state=action.get("state", "visible"),
                timeout=action.get("timeout", 10000),
            )
            step_reports.append(f"Step {i + 1} (wait_for): '{action['selector']}' is {action.get('state', 'visible')}")
            continue

        _, before = await _capture(page)
        result = await _execute_action(page, action)
        action_wait = action.get("wait")
        if action_wait:
            await _wait(page, action_wait)
        _, final = await _capture(page)
        change = StateChange.compute(before, final)
        report = f"Step {i + 1} ({action_type}): {change.description}"
        if result is not None:
            report += f"\n  result: {result}"
        step_reports.append(report)

    if final is None:
        _, final = await _capture(page, scope)
    elif wait:
        await _wait(page, wait)
        _, final = await _capture(page, scope)
    elif scope:
        _, final = await _capture(page, scope)
    if query:
        final_summary = await analyze_screenshot(final, config, query)
    else:
        final_summary = f"{final.title} — {final.url}\n{final.visible_text[:500]}"

    return "\n".join(step_reports) + f"\n\n---\nFinal state: {final_summary}"


@mcp.tool()
async def screenshot(query: str | None = None, scope: str | None = None) -> str:
    """Capture the current page or a scoped element. With query, returns vision analysis."""
    _, state = await _capture(scope=scope)
    return await analyze_screenshot(state, config, query)


@mcp.tool()
async def get_page_state(scope: str | None = None) -> str:
    """Get current page URL, title, accessibility tree, focused element, and visible text."""
    _, state = await _capture(scope=scope)
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
