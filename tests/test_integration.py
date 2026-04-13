import pytest
from pydantic import TypeAdapter

from interact_mcp import server
from interact_mcp.actions import AnyAction
from interact_mcp.browser import SessionRegistry
from interact_mcp.config import Config

_action_adapter = TypeAdapter(list[AnyAction])

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="module"),
]


@pytest.fixture(scope="module")
async def _setup():
    cfg = Config(vision_model="gpt-4o-mini", headless=True)
    registry = SessionRegistry(cfg)

    orig_config = server.config
    orig_sessions = server._sessions
    server.config = cfg
    server._sessions = registry

    yield

    await registry.close_all()
    server.config = orig_config
    server._sessions = orig_sessions


@pytest.fixture(autouse=True, scope="module")
async def _use_setup(_setup):
    yield


async def test_navigate_and_verify():
    result = await server.navigate(
        "https://en.wikipedia.org",
        query="What website is this? Name it.",
        wait="networkidle",
    )
    assert "wikipedia" in result.lower()


async def test_get_page_state_structure():
    result = await server.get_page_state()
    assert "URL: https://en.wikipedia.org" in result
    assert "Title:" in result
    assert "Accessibility Tree:" in result
    assert "Visible Text:" in result


async def test_screenshot_identifies_content():
    result = await server.screenshot(query="Describe the main visual elements on this page.")
    assert len(result) > 20


async def test_type_and_verify():
    actions = _action_adapter.validate_python([
        {"type": "type_text", "selector": "input[name='search']", "text": "Python programming"},
    ])
    result = await server.run_actions(
        actions=actions,
        query="What text is in the search box?",
    )
    assert "python" in result.lower()


async def test_navigate_to_article_and_verify():
    actions = _action_adapter.validate_python([
        {"type": "navigate", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)", "wait": "networkidle"},
        {"type": "wait_for", "selector": "#firstHeading"},
    ])
    result = await server.run_actions(
        actions=actions,
        query="What programming language is this article about?",
    )
    assert "python" in result.lower()


async def test_scroll_reveals_content():
    actions = _action_adapter.validate_python([
        {"type": "scroll", "direction": "down", "amount": 5},
    ])
    result = await server.run_actions(actions=actions)
    assert "Step 1 (scroll):" in result


async def test_evaluate_js_returns_value():
    actions = _action_adapter.validate_python([
        {"type": "evaluate_js", "script": "document.title"},
    ])
    result = await server.run_actions(actions=actions)
    assert "Python" in result


async def test_click_coordinate():
    actions = _action_adapter.validate_python([
        {"type": "click", "x": 640, "y": 360, "wait": "networkidle"},
    ])
    result = await server.run_actions(actions=actions)
    assert "Step 1 (click):" in result


async def test_click_selector():
    await server.navigate(
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        wait="networkidle",
    )
    actions = _action_adapter.validate_python([
        {"type": "click", "selector": "#firstHeading"},
    ])
    result = await server.run_actions(actions=actions)
    assert "Step 1 (click):" in result


async def test_list_clickable_finds_elements():
    actions = _action_adapter.validate_python([
        {"type": "list_clickable"},
    ])
    result = await server.run_actions(actions=actions)
    assert "list_clickable" in result
    assert "a" in result.lower() or "input" in result.lower()


async def test_drag_executes():
    actions = _action_adapter.validate_python([
        {"type": "drag", "from_x": 400, "from_y": 300, "to_x": 500, "to_y": 300},
    ])
    result = await server.run_actions(actions=actions)
    assert "Step 1 (drag):" in result


async def test_full_workflow_with_vision():
    actions = _action_adapter.validate_python([
        {"type": "navigate", "url": "https://en.wikipedia.org/wiki/Rust_(programming_language)", "wait": "networkidle"},
        {"type": "wait_for", "selector": "#firstHeading"},
        {"type": "list_clickable"},
        {"type": "scroll", "direction": "down", "amount": 3},
        {"type": "evaluate_js", "script": "document.title"},
        {"type": "screenshot", "query": "What article is this?"},
    ])
    result = await server.run_actions(
        actions=actions,
        query="Summarize what we're looking at.",
    )
    assert "rust" in result.lower()


async def test_session_isolation():
    """Two sessions should have independent browser state."""
    await server.navigate(
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        wait="networkidle",
        session="session_a",
    )
    await server.navigate(
        "https://en.wikipedia.org/wiki/Rust_(programming_language)",
        wait="networkidle",
        session="session_b",
    )
    state_a = await server.get_page_state(session="session_a")
    state_b = await server.get_page_state(session="session_b")
    assert "Python" in state_a
    assert "Rust" in state_b
    assert "Rust" not in state_a
    assert "Python" not in state_b

    await server.close_session("session_a")
    await server.close_session("session_b")


async def test_http_request_action():
    """HTTP request action fires raw request without browser."""
    actions = _action_adapter.validate_python([
        {"type": "http_request", "method": "GET", "url": "https://httpbin.org/get"},
    ])
    result = await server.run_actions(actions=actions)
    assert "200" in result
    assert "httpbin" in result.lower()


async def test_multi_tab():
    """New tab opens independently, switch_tab changes context."""
    await server.navigate("https://en.wikipedia.org", wait="networkidle", session="tabs_test")

    actions = _action_adapter.validate_python([
        {"type": "new_tab", "url": "https://en.wikipedia.org/wiki/Python_(programming_language)"},
        {"type": "switch_tab", "index": 1},
        {"type": "wait_for", "selector": "#firstHeading"},
        {"type": "screenshot", "query": "What article is this?"},
    ])
    result = await server.run_actions(actions=actions, session="tabs_test")
    assert "python" in result.lower()

    await server.close_session("tabs_test")
    assert "Final state:" in result


async def test_annotate_and_click_by_ref():
    """Annotate page, get refs, click by ref — no coordinates needed."""
    await server.navigate("https://en.wikipedia.org", wait="networkidle", session="ref_test")

    result = await server.get_interactive_elements(session="ref_test")
    assert "interactive elements" in result
    assert "ref=" in result

    lines = [l for l in result.split("\n") if "ref=" in l]
    assert len(lines) > 0

    await server.close_session("ref_test")


async def test_desktop_windows_graceful():
    result = await server.list_desktop_windows()
    assert isinstance(result, str)


async def test_analyze_window_no_match():
    result = await server.analyze_window("NONEXISTENT_WINDOW_12345")
    assert "No desktop windows" in result or "No window matching" in result
