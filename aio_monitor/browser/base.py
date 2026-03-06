"""Abstract browser engine interface for SERP automation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class BrowserEngine(ABC):
    """Abstract browser engine that can be backed by OpenClaw or Playwright."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize and start the browser."""
        ...

    @abstractmethod
    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        ...

    @abstractmethod
    async def screenshot(self, path: str | Path, full_page: bool = True) -> str:
        """Take a screenshot. Returns the path to the saved file."""
        ...

    @abstractmethod
    async def get_page_source(self) -> str:
        """Get the current page HTML source."""
        ...

    @abstractmethod
    async def get_page_text(self) -> str:
        """Get the visible text content of the current page."""
        ...

    @abstractmethod
    async def find_element_text(self, selector: str) -> Optional[str]:
        """Find an element by CSS selector and return its text content."""
        ...

    @abstractmethod
    async def find_elements_text(self, selector: str) -> list[str]:
        """Find all elements matching a CSS selector and return their text."""
        ...

    @abstractmethod
    async def find_element_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Find an element and return a specific attribute value."""
        ...

    @abstractmethod
    async def find_elements_attribute(self, selector: str, attribute: str) -> list[str]:
        """Find all matching elements and return a specific attribute value."""
        ...

    @abstractmethod
    async def element_exists(self, selector: str) -> bool:
        """Check if an element matching the selector exists on the page."""
        ...

    @abstractmethod
    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an input element."""
        ...

    @abstractmethod
    async def click(self, selector: str) -> None:
        """Click an element."""
        ...

    @abstractmethod
    async def wait_for_selector(self, selector: str, timeout: float = 10.0) -> bool:
        """Wait for an element to appear. Returns True if found, False on timeout."""
        ...

    @abstractmethod
    async def wait_for_page_load(self, timeout: float = 30.0) -> None:
        """Wait for the page to fully load."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Close the browser and clean up resources."""
        ...
