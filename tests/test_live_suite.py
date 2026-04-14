import asyncio
import sys
import traceback
from datetime import datetime
from pathlib import Path

from interact_mcp import server
from interact_mcp.actions import (
    ClickAction,
    DragAction,
    EvaluateJsAction,
    HoverAction,
    KeyPressAction,
    NavigateAction,
    ScrollAction,
)
from interact_mcp.browser import SessionRegistry
from interact_mcp.config import Config

_TIMESTAMP = datetime.now().strftime("%Y-%m-%d_%H%M%S")
_OUT_DIR = Path("out") / _TIMESTAMP
_SCREENSHOTS_DIR = _OUT_DIR / "screenshots"
_LOG_FILE = _OUT_DIR / "test_log.txt"

_log_lines: list[str] = []


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _log(kind: str, msg: str):
    line = f"[{_ts()}] {kind}: {msg}"
    _log_lines.append(line)
    print(line, flush=True)


def _save_screenshot(name: str, data: bytes):
    path = _SCREENSHOTS_DIR / name
    path.write_bytes(data)
    _log("SCREENSHOT", name)


def _flush_log():
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _LOG_FILE.write_text("\n".join(_log_lines))


async def _capture_screenshot(label: str) -> bytes:
    mgr = server._sessions.get("default")
    page = await mgr.get_page()
    data = await page.screenshot(type="png")
    _save_screenshot(f"{label}.png", data)
    return data


async def scenario_navigation():
    _log("STEP", "Scenario 1: Navigation + Element Discovery")

    result = await server.navigate("https://en.wikipedia.org", wait="networkidle")
    _log("RESULT", f"Navigated: {result[:200]}")

    elements = await server.get_interactive_elements()
    _log("RESULT", f"Interactive elements:\n{elements[:1000]}")

    await _capture_screenshot("01_wikipedia_home")


async def scenario_search():
    _log("STEP", "Scenario 2: Search + Article")

    mgr = server._sessions.get("default")
    page = await mgr.get_page()

    result = await server.run_actions(
        actions=[ClickAction(selector="input[name='search']")],
    )
    _log("RESULT", f"Clicked search: {result[:200]}")

    result = await server.run_actions(
        actions=[
            EvaluateJsAction(
                script="document.querySelector('input[name=search]').value = ''"
            ),
            KeyPressAction(key="p"),
        ],
    )

    for char in "ython programming language":
        await page.keyboard.press(char)
    _log("RESULT", "Typed search query")

    await _capture_screenshot("02_search_typed")

    async with page.expect_navigation(wait_until="networkidle"):
        await page.keyboard.press("Enter")

    await page.wait_for_selector("#firstHeading", timeout=10000)
    title = await page.title()
    _log("RESULT", f"Article loaded: {title}")

    await _capture_screenshot("03_python_article")

    elements = await server.get_interactive_elements()
    _log("RESULT", f"Article elements (first 500):\n{elements[:500]}")


async def scenario_click_navigation():
    _log("STEP", "Scenario 3: Click Navigation")

    result = await server.run_actions(
        actions=[
            ClickAction(selector='a[title="Guido van Rossum"]', wait="networkidle"),
        ],
    )
    _log("RESULT", f"Clicked link: {result[:300]}")

    await _capture_screenshot("04_after_click")

    result = await server.run_actions(
        actions=[
            ScrollAction(direction="down", amount=3),
        ],
    )
    _log("RESULT", f"Scrolled: {result[:200]}")

    await _capture_screenshot("05_after_scroll")


async def scenario_hover():
    _log("STEP", "Scenario 4: Hover Test")

    result = await server.run_actions(
        actions=[NavigateAction(url="https://en.wikipedia.org", wait="networkidle")],
    )
    _log("RESULT", f"Back to main page: {result[:200]}")

    await _capture_screenshot("06_main_page_for_hover")

    result = await server.run_actions(
        actions=[HoverAction(selector="#mp-upper a")],
    )
    _log("RESULT", f"Hovered over link: {result[:200]}")

    await _capture_screenshot("07_after_hover")


async def scenario_clipboard():
    _log("STEP", "Scenario 5: Text Selection + Clipboard")

    result = await server.run_actions(
        actions=[
            NavigateAction(
                url="https://en.wikipedia.org/wiki/Python_(programming_language)",
                wait="networkidle",
            ),
        ],
    )
    _log("RESULT", f"Navigated to article: {result[:200]}")

    mgr = server._sessions.get("default")
    page = await mgr.get_page()

    await page.wait_for_selector("#firstHeading", timeout=10000)
    box = await page.evaluate(
        "(() => { const el = document.querySelector('#firstHeading');"
        " const r = el.getBoundingClientRect();"
        " return {x: r.x, y: r.y, width: r.width, height: r.height}; })()"
    )
    _log("RESULT", f"Heading box: {box}")

    start_x = int(box["x"] + 5)
    start_y = int(box["y"] + box["height"] / 2)
    end_x = int(box["x"] + box["width"] - 5)

    result = await server.run_actions(
        actions=[
            DragAction(
                from_x=start_x, from_y=start_y, to_x=end_x, to_y=start_y, steps=15
            )
        ],
    )
    _log("RESULT", f"Dragged to select: {result[:200]}")

    selected = await page.evaluate("window.getSelection().toString()")
    _log("RESULT", f"Selected text: {selected!r}")

    await _capture_screenshot("08_text_selected")

    await page.keyboard.press("Control+c")
    _log("RESULT", "Pressed Ctrl+C")

    await page.click("input[name=search]")
    await page.evaluate(
        "s => document.querySelector(s).value = ''", "input[name=search]"
    )
    _log("RESULT", "Focused and cleared search input")

    await page.keyboard.press("Control+v")
    _log("RESULT", "Pressed Ctrl+V")

    await asyncio.sleep(0.5)

    pasted = await page.evaluate(
        "s => document.querySelector(s).value", "input[name=search]"
    )
    _log("RESULT", f"Pasted text: {pasted!r}")

    match = selected.strip() == pasted.strip() if selected and pasted else False
    _log(
        "RESULT", f"Clipboard match: {match} (selected={selected!r}, pasted={pasted!r})"
    )

    await _capture_screenshot("09_after_paste")


async def scenario_multi_tab():
    _log("STEP", "Scenario 6: Multi-tab")

    result = await server.run_actions(
        actions=[
            NavigateAction(url="https://en.wikipedia.org", wait="networkidle"),
        ],
    )
    _log("RESULT", f"Tab 0 at Wikipedia: {result[:200]}")

    mgr = server._sessions.get("default")
    tab_idx = await mgr.new_tab(
        "https://en.wikipedia.org/wiki/Rust_(programming_language)"
    )
    _log("RESULT", f"Opened new tab at index {tab_idx}")

    page1 = await mgr.get_page(tab_idx)
    await page1.wait_for_load_state("networkidle")

    await _capture_screenshot("10_tab0")

    page1_data = await page1.screenshot(type="png")
    _save_screenshot("11_tab1_rust.png", page1_data)

    page0 = await mgr.get_page(0)
    title0 = await page0.title()
    title1 = await page1.title()
    _log("RESULT", f"Tab 0: {title0}, Tab 1: {title1}")

    await mgr.close_tab(tab_idx)
    _log("RESULT", f"Closed tab {tab_idx}")

    remaining = mgr.tab_count
    _log("RESULT", f"Remaining tabs: {remaining}")

    await _capture_screenshot("12_after_tab_close")


async def main():
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

    cfg = Config(
        headless=False,
        slow_mo=800,
        vision_model="gpt-4o-mini",
        screenshot_dump_dir=_SCREENSHOTS_DIR,
    )
    server.config = cfg
    server._sessions = SessionRegistry(cfg)

    scenarios = [
        ("Navigation + Element Discovery", scenario_navigation),
        ("Search + Article", scenario_search),
        ("Click Navigation", scenario_click_navigation),
        ("Hover Test", scenario_hover),
        ("Text Selection + Clipboard", scenario_clipboard),
        ("Multi-tab", scenario_multi_tab),
    ]

    results: list[tuple[str, bool, str]] = []

    try:
        for name, fn in scenarios:
            _log("STEP", f"--- Starting: {name} ---")
            try:
                await fn()
                results.append((name, True, ""))
                _log("RESULT", f"{name}: PASSED")
            except Exception as exc:
                results.append((name, False, str(exc)))
                _log("RESULT", f"{name}: FAILED - {exc}")
                traceback.print_exc()
    finally:
        _log("STEP", "Cleaning up")
        await server._sessions.close_all()
        _flush_log()

    print("\n=== SUMMARY ===", flush=True)
    all_passed = True
    for name, passed, err in results:
        status = "PASS" if passed else "FAIL"
        line = f"  [{status}] {name}"
        if err:
            line += f" -- {err}"
        print(line, flush=True)
        if not passed:
            all_passed = False

    print(f"\nLog: {_LOG_FILE}", flush=True)
    print(f"Screenshots: {_SCREENSHOTS_DIR}", flush=True)

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
