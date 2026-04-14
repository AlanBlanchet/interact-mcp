import subprocess
from collections import deque
from datetime import datetime

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from interact_mcp.config import LOG_MAXLEN, Config
from interact_mcp.state import InteractiveElement


class BrowserManager:
    def __init__(self, config: Config):
        self._config = config
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        # TODO: element map may go stale after mutating actions (click, navigate, etc.)
        self._element_map: dict[int, list[InteractiveElement]] = {}
        self._network_log: deque[dict] = deque(maxlen=LOG_MAXLEN)
        self._console_log: deque[dict] = deque(maxlen=LOG_MAXLEN)

    def set_element_map(self, tab: int, elements: list[InteractiveElement]):
        self._element_map[tab] = elements

    def get_element(self, index: int, tab: int = 0) -> InteractiveElement | None:
        for el in self._element_map.get(tab, []):
            if el.index == index:
                return el
        return None

    @property
    def tab_count(self) -> int:
        if not self._context:
            return 0
        return len(self._context.pages)

    async def ensure_ready(self):
        if self._context:
            return
        await self._ensure_browser()
        await self._new_context()

    async def get_page(self, tab_index: int = 0) -> Page:
        await self.ensure_ready()
        pages = self._context.pages
        if tab_index < len(pages):
            return pages[tab_index]
        raise IndexError(f"Tab {tab_index} does not exist — {len(pages)} tab(s) open")

    async def new_tab(self, url: str | None = None) -> int:
        await self.ensure_ready()
        page = await self._context.new_page()
        self._attach_page_listeners(page)
        if url:
            await page.goto(url)
        return len(self._context.pages) - 1

    async def close_tab(self, tab_index: int):
        await self.ensure_ready()
        pages = self._context.pages
        if tab_index >= len(pages):
            raise IndexError(f"Tab {tab_index} not found")
        await pages[tab_index].close()

    async def save_state(self) -> dict:
        await self.ensure_ready()
        return await self._context.storage_state()

    async def load_state(self, state: dict):
        await self._ensure_browser()
        if self._context:
            await self._context.close()
        await self._new_context(state)

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _context_kwargs(self) -> dict:
        return {
            "viewport": {
                "width": self._config.viewport_width,
                "height": self._config.viewport_height,
            },
        }

    def _install_browser(self):
        subprocess.run(
            ["playwright", "install", self._config.browser_type],
            check=True,
            capture_output=True,
        )

    async def _ensure_browser(self):
        if self._browser:
            return
        self._install_browser()
        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._config.browser_type)
        self._browser = await launcher.launch(
            headless=self._config.headless,
            slow_mo=self._config.slow_mo,
        )

    async def _new_context(self, storage_state: dict | None = None):
        kwargs = self._context_kwargs()
        if storage_state is not None:
            kwargs["storage_state"] = storage_state
        self._context = await self._browser.new_context(**kwargs)
        await self._context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = await self._context.new_page()
        self._attach_page_listeners(page)

    def _attach_page_listeners(self, page: Page):
        page.on(
            "request",
            lambda req: self._network_log.append(
                {
                    "method": req.method,
                    "url": req.url,
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
            ),
        )
        page.on("response", lambda resp: self._on_response(resp))
        page.on(
            "console",
            lambda msg: self._console_log.append(
                {
                    "level": msg.type,
                    "text": msg.text,
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
            ),
        )
        page.on(
            "pageerror",
            lambda err: self._console_log.append(
                {
                    "level": "error",
                    "text": str(err),
                    "ts": datetime.now().isoformat(timespec="seconds"),
                }
            ),
        )

    def _on_response(self, response):
        url = response.url
        for entry in reversed(self._network_log):
            if entry["url"] == url and "status" not in entry:
                entry["status"] = response.status
                entry["content_type"] = response.headers.get("content-type", "")
                break

    def drain_network_log(self, clear: bool = False) -> list[dict]:
        entries = list(self._network_log)
        if clear:
            self._network_log.clear()
        return entries

    def drain_console_log(self, clear: bool = False) -> list[dict]:
        entries = list(self._console_log)
        if clear:
            self._console_log.clear()
        return entries


class SessionRegistry:
    def __init__(self, config: Config):
        self._config = config
        self._sessions: dict[str, BrowserManager] = {}

    def get(self, session_id: str) -> BrowserManager:
        if session_id not in self._sessions:
            self._sessions[session_id] = BrowserManager(self._config)
        return self._sessions[session_id]

    async def close(self, session_id: str):
        mgr = self._sessions.pop(session_id, None)
        if mgr:
            await mgr.close()

    def active(self) -> list[str]:
        return list(self._sessions.keys())

    async def close_all(self):
        for mgr in self._sessions.values():
            await mgr.close()
        self._sessions.clear()
