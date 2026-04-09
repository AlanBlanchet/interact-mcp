import subprocess

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from interact_mcp.config import Config


class BrowserManager:
    def __init__(self, config: Config):
        self._config = config
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    async def ensure_ready(self):
        if self._page:
            return

        self._install_browser()

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._config.browser_type)
        self._browser = await launcher.launch(headless=self._config.headless)
        self._context = await self._browser.new_context(
            viewport={
                "width": self._config.viewport_width,
                "height": self._config.viewport_height,
            }
        )
        self._page = await self._context.new_page()

    async def get_page(self) -> Page:
        await self.ensure_ready()
        assert self._page is not None
        return self._page

    async def close(self):
        if self._browser:
            await self._browser.close()
            self._browser = None
            self._context = None
            self._page = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _install_browser(self):
        subprocess.run(
            ["playwright", "install", self._config.browser_type],
            check=True,
            capture_output=True,
        )
