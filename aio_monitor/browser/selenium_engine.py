"""Selenium-based headless browser engine (universal fallback).

Works in any environment with Chrome/Chromium and ChromeDriver installed.
Provides full CSS selector support and reliable screenshot capture.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from aio_monitor.browser.base import BrowserEngine

logger = logging.getLogger(__name__)


class SeleniumEngine(BrowserEngine):
    """Browser engine backed by Selenium + headless ChromeDriver."""

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
        self._driver = None

    async def start(self) -> None:
        """Launch headless Chrome via Selenium."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
        except ImportError:
            raise ImportError(
                "Selenium is not installed. Install it with:\n"
                "  pip install selenium webdriver-manager"
            )

        logger.info("Starting Selenium browser (headless=%s)", self.headless)
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(f"--window-size={self.viewport_width},{self.viewport_height}")
        options.add_argument(f"--user-agent={self.user_agent}")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        # Try webdriver-manager first, fall back to system chromedriver
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            self._driver = webdriver.Chrome(service=service, options=options)
        except Exception:
            logger.info("webdriver-manager not available, trying system chromedriver")
            self._driver = webdriver.Chrome(options=options)

        logger.info("Selenium browser ready")

    @property
    def driver(self):
        """Get the active WebDriver, raising if not started."""
        if self._driver is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._driver

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        logger.debug("Navigating to %s", url)
        self.driver.get(url)

    async def screenshot(self, path: str | Path, full_page: bool = True) -> str:
        """Take a screenshot of the current page."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if full_page:
            # Expand window to capture full page
            total_height = self.driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            self.driver.set_window_size(self.viewport_width, min(total_height + 100, 16384))
            time.sleep(0.5)

        self.driver.save_screenshot(str(path))

        if full_page:
            # Reset window size
            self.driver.set_window_size(self.viewport_width, self.viewport_height)

        logger.debug("Screenshot saved to %s", path)
        return str(path)

    async def get_page_source(self) -> str:
        """Get the full HTML source of the current page."""
        return self.driver.page_source

    async def get_page_text(self) -> str:
        """Get all visible text from the page body."""
        try:
            from selenium.webdriver.common.by import By
            body = self.driver.find_element(By.TAG_NAME, "body")
            return body.text
        except Exception:
            return self.driver.page_source

    async def find_element_text(self, selector: str) -> Optional[str]:
        """Find an element and return its text content."""
        try:
            from selenium.webdriver.common.by import By
            el = self.driver.find_element(By.CSS_SELECTOR, selector)
            return el.text
        except Exception as e:
            logger.debug("find_element_text(%s) failed: %s", selector, e)
            return None

    async def find_elements_text(self, selector: str) -> list[str]:
        """Find all matching elements and return their text."""
        try:
            from selenium.webdriver.common.by import By
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            return [el.text.strip() for el in elements if el.text.strip()]
        except Exception as e:
            logger.debug("find_elements_text(%s) failed: %s", selector, e)
            return []

    async def find_element_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Find an element and return a specific attribute value."""
        try:
            from selenium.webdriver.common.by import By
            el = self.driver.find_element(By.CSS_SELECTOR, selector)
            return el.get_attribute(attribute)
        except Exception as e:
            logger.debug("find_element_attribute(%s, %s) failed: %s", selector, attribute, e)
            return None

    async def find_elements_attribute(self, selector: str, attribute: str) -> list[str]:
        """Find all matching elements and return a specific attribute."""
        try:
            from selenium.webdriver.common.by import By
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            attrs = []
            for el in elements:
                val = el.get_attribute(attribute)
                if val:
                    attrs.append(val)
            return attrs
        except Exception as e:
            logger.debug("find_elements_attribute(%s, %s) failed: %s", selector, attribute, e)
            return []

    async def element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        try:
            from selenium.webdriver.common.by import By
            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
            return len(elements) > 0
        except Exception:
            return False

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an input field."""
        from selenium.webdriver.common.by import By
        el = self.driver.find_element(By.CSS_SELECTOR, selector)
        el.clear()
        el.send_keys(text)

    async def click(self, selector: str) -> None:
        """Click an element."""
        from selenium.webdriver.common.by import By
        el = self.driver.find_element(By.CSS_SELECTOR, selector)
        el.click()

    async def wait_for_selector(self, selector: str, timeout: float = 10.0) -> bool:
        """Wait for an element to appear on the page."""
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            return True
        except Exception:
            return False

    async def wait_for_page_load(self, timeout: float = 30.0) -> None:
        """Wait for the page to fully load."""
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            WebDriverWait(self.driver, timeout).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except Exception:
            time.sleep(2)

    async def stop(self) -> None:
        """Close the browser and clean up."""
        if self._driver:
            self._driver.quit()
            self._driver = None
            logger.info("Selenium browser closed")
