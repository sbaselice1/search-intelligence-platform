"""Playwright-based headless browser engine (fallback).

Used when OpenClaw is not installed or as a lightweight alternative.
Provides full CSS selector support and reliable screenshot capture.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from aio_monitor.browser.base import BrowserEngine

logger = logging.getLogger(__name__)


class PlaywrightEngine(BrowserEngine):
    """Browser engine backed by Playwright headless Chromium."""

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1280,
        viewport_height: int = 900,
        user_agent: str = "",
    ) -> None:
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None

    async def start(self) -> None:
        """Launch Playwright and open a browser context."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is not installed. Install it with:\n"
                "  pip install playwright && playwright install chromium"
            )

        logger.info("Starting Playwright browser (headless=%s)", self.headless)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._context = await self._browser.new_context(
            viewport={"width": self.viewport_width, "height": self.viewport_height},
            user_agent=self.user_agent,
        )
        self._page = await self._context.new_page()
        logger.info("Playwright browser ready")

    @property
    def page(self):
        """Get the active page, raising if not started."""
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    async def navigate(self, url: str) -> None:
        """Navigate to a URL and wait for network idle."""
        logger.debug("Navigating to %s", url)
        await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)

    async def screenshot(self, path: str | Path, full_page: bool = True) -> str:
        """Take a screenshot of the current page."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=str(path), full_page=full_page)
        logger.debug("Screenshot saved to %s", path)
        return str(path)

    async def get_page_source(self) -> str:
        """Get the full HTML source of the current page."""
        return await self.page.content()

    async def get_page_text(self) -> str:
        """Get all visible text from the page."""
        return await self.page.inner_text("body")

    async def find_element_text(self, selector: str) -> Optional[str]:
        """Find an element and return its text content."""
        try:
            el = self.page.locator(selector).first
            if await el.count() > 0:
                return await el.inner_text()
        except Exception as e:
            logger.debug("find_element_text(%s) failed: %s", selector, e)
        return None

    async def find_elements_text(self, selector: str) -> list[str]:
        """Find all matching elements and return their text."""
        try:
            elements = self.page.locator(selector)
            count = await elements.count()
            texts = []
            for i in range(count):
                text = await elements.nth(i).inner_text()
                texts.append(text.strip())
            return texts
        except Exception as e:
            logger.debug("find_elements_text(%s) failed: %s", selector, e)
            return []

    async def find_element_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Find an element and return a specific attribute value."""
        try:
            el = self.page.locator(selector).first
            if await el.count() > 0:
                return await el.get_attribute(attribute)
        except Exception as e:
            logger.debug("find_element_attribute(%s, %s) failed: %s", selector, attribute, e)
        return None

    async def find_elements_attribute(self, selector: str, attribute: str) -> list[str]:
        """Find all matching elements and return a specific attribute."""
        try:
            elements = self.page.locator(selector)
            count = await elements.count()
            attrs = []
            for i in range(count):
                val = await elements.nth(i).get_attribute(attribute)
                if val:
                    attrs.append(val)
            return attrs
        except Exception as e:
            logger.debug("find_elements_attribute(%s, %s) failed: %s", selector, attribute, e)
            return []

    async def element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        try:
            return await self.page.locator(selector).count() > 0
        except Exception:
            return False

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an input field."""
        await self.page.fill(selector, text)

    async def click(self, selector: str) -> None:
        """Click an element."""
        await self.page.click(selector)

    async def wait_for_selector(self, selector: str, timeout: float = 10.0) -> bool:
        """Wait for an element to appear on the page."""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout * 1000)
            return True
        except Exception:
            return False

    async def wait_for_page_load(self, timeout: float = 30.0) -> None:
        """Wait for the page to reach a loaded state."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout * 1000)
        except Exception:
            # networkidle can be flaky; fall back to domcontentloaded
            try:
                await self.page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

    async def stop(self) -> None:
        """Close the browser and clean up Playwright resources."""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None
        self._context = None
        logger.info("Playwright browser closed")
