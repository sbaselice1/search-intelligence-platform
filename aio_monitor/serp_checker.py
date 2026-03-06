"""Google SERP checker — searches Google and detects AI Overviews.

This module handles:
1. Navigating to Google and performing a search
2. Detecting whether an AI Overview is present
3. Extracting cited domains from the AI Overview
4. Taking a screenshot of the SERP
5. Checking if target domains are cited
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from aio_monitor.browser.base import BrowserEngine
from aio_monitor.models import KeywordResult, RunStatus

logger = logging.getLogger(__name__)

# CSS selectors and text patterns for detecting AI Overviews on Google.
# Google's DOM changes frequently — these are best-effort and may need updating.
# When detection is uncertain, we store raw notes + screenshot for manual review.

# Known AI Overview container selectors (Google changes these periodically)
AI_OVERVIEW_SELECTORS = [
    # Data attribute-based selectors (most reliable)
    "[data-attrid='wa:/description']",
    "div[data-md]",
    # Class-based selectors for the AI-generated answer block
    "div.kp-wholepage",
    "div.ifM9O",
    # SGE / AI Overview specific containers
    "div[jsname='N760b']",
    "div.M8OgIe",
    "div.PkOFod",
    # The "AI Overview" label/heading
    "div.RjnGAd",
    "div.LLtSOc",
    # Generative AI container
    "div[data-sgrd]",
    "div[data-q]",
]

# Text patterns that indicate AI Overview presence
AI_OVERVIEW_TEXT_PATTERNS = [
    r"AI\s*Overview",
    r"AI-generated",
    r"Generative\s*AI",
    r"According to.*sources",
]

# Selectors for citation links within AI Overview sections
CITATION_SELECTORS = [
    "div[data-sgrd] a[href]",
    "div[data-md] a[href]",
    "div.M8OgIe a[href]",
    "div.kp-wholepage a[href]",
    "div.LLtSOc a[href]",
    # Carousel-style citation cards
    "a.irOOuf",
    "a[data-ved] cite",
]


def extract_domain(url: str) -> str:
    """Extract the domain from a URL, stripping www. prefix."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain.lower()
    except Exception:
        return ""


class SerpChecker:
    """Checks Google SERPs for AI Overview presence and cited domains."""

    def __init__(
        self,
        browser: BrowserEngine,
        target_domains: list[str],
        google_domain: str = "https://www.google.com",
        search_params: Optional[dict] = None,
        screenshots_dir: str = "output/screenshots",
        delay_between_searches: float = 5.0,
        page_load_timeout: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.browser = browser
        self.target_domains = [d.lower().replace("www.", "") for d in target_domains]
        self.google_domain = google_domain
        self.search_params = search_params or {"hl": "en", "gl": "us"}
        self.screenshots_dir = Path(screenshots_dir)
        self.delay_between_searches = delay_between_searches
        self.page_load_timeout = page_load_timeout
        self.max_retries = max_retries

    def _build_search_url(self, keyword: str) -> str:
        """Build a Google search URL for the given keyword."""
        from urllib.parse import quote_plus, urlencode
        params = {**self.search_params, "q": keyword}
        return f"{self.google_domain}/search?{urlencode(params, quote_via=quote_plus)}"

    def _make_screenshot_path(self, keyword: str, date_str: str) -> Path:
        """Generate a screenshot file path for a keyword."""
        safe_keyword = re.sub(r"[^a-zA-Z0-9_-]", "_", keyword)[:80]
        date_dir = self.screenshots_dir / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%H%M%S")
        return date_dir / f"{safe_keyword}_{timestamp}.png"

    async def _detect_ai_overview_from_source(self, page_source: str) -> tuple[bool, str]:
        """Detect AI Overview from page HTML source. Returns (found, notes)."""
        notes_parts: list[str] = []

        # Check for text patterns in the source
        for pattern in AI_OVERVIEW_TEXT_PATTERNS:
            if re.search(pattern, page_source, re.IGNORECASE):
                notes_parts.append(f"Text pattern match: {pattern}")
                return True, "; ".join(notes_parts)

        # Check for known container elements
        for selector in AI_OVERVIEW_SELECTORS:
            # Convert CSS selector to a rough HTML attribute check
            if "data-sgrd" in selector and "data-sgrd" in page_source:
                notes_parts.append("Attribute match: data-sgrd")
                return True, "; ".join(notes_parts)
            if "data-md" in selector and 'data-md="' in page_source:
                notes_parts.append("Attribute match: data-md")
                return True, "; ".join(notes_parts)

        return False, "No AI Overview indicators found in page source"

    async def _detect_ai_overview_via_selectors(self) -> tuple[bool, str]:
        """Try to detect AI Overview using browser CSS selectors."""
        for selector in AI_OVERVIEW_SELECTORS:
            try:
                exists = await self.browser.element_exists(selector)
                if exists:
                    return True, f"Selector match: {selector}"
            except Exception:
                continue
        return False, ""

    async def _extract_citations_from_source(self, page_source: str) -> list[str]:
        """Extract cited domains from AI Overview containers in page source.

        Uses BeautifulSoup to isolate AI Overview container HTML first,
        then extracts href links only from those sections.  Falls back to
        an empty list if no container can be identified.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning(
                "beautifulsoup4 not installed — cannot scope citation "
                "extraction to AI Overview container. Returning empty list."
            )
            return []

        soup = BeautifulSoup(page_source, "html.parser")

        # Attempt to isolate AI Overview container(s) using known markers
        container_queries = [
            {"attrs": {"data-sgrd": True}},
            {"attrs": {"data-md": True}},
            {"class_": "M8OgIe"},
            {"class_": "kp-wholepage"},
            {"class_": "LLtSOc"},
            {"class_": "PkOFod"},
        ]

        container_html_parts: list[str] = []
        for query in container_queries:
            for tag in soup.find_all(**query):
                container_html_parts.append(str(tag))

        if not container_html_parts:
            # No AI Overview container found — return empty rather than
            # extracting from the whole page
            return []

        # Parse only the container HTML for href links
        container_soup = BeautifulSoup(
            "\n".join(container_html_parts), "html.parser"
        )

        domains: list[str] = []
        for a_tag in container_soup.find_all("a", href=True):
            href = a_tag["href"]
            if not href.startswith("http"):
                continue
            domain = extract_domain(href)
            if domain and not self._is_google_internal(domain):
                if domain not in domains:
                    domains.append(domain)

        return domains

    async def _extract_citations_via_selectors(self) -> list[str]:
        """Extract cited domains using browser CSS selectors."""
        domains: list[str] = []
        for selector in CITATION_SELECTORS:
            try:
                hrefs = await self.browser.find_elements_attribute(selector, "href")
                for href in hrefs:
                    domain = extract_domain(href)
                    if domain and not self._is_google_internal(domain):
                        if domain not in domains:
                            domains.append(domain)
            except Exception:
                continue
        return domains

    @staticmethod
    def _is_google_internal(domain: str) -> bool:
        """Check if a domain is a Google internal domain."""
        google_domains = {
            "google.com", "google.co.uk", "google.ca",
            "gstatic.com", "googleapis.com", "googleusercontent.com",
            "googlesyndication.com", "googleadservices.com",
            "youtube.com", "youtu.be", "yt.be",
            "accounts.google.com", "support.google.com",
            "maps.google.com", "play.google.com",
        }
        return any(domain == gd or domain.endswith(f".{gd}") for gd in google_domains)

    def _check_target_cited(self, cited_domains: list[str]) -> bool:
        """Check if any target domain appears in the cited domains."""
        for cited in cited_domains:
            cited_clean = cited.lower().replace("www.", "")
            for target in self.target_domains:
                if cited_clean == target or cited_clean.endswith(f".{target}"):
                    return True
        return False

    async def check_keyword(self, keyword: str, date_str: str) -> KeywordResult:
        """Check a single keyword for AI Overview presence.

        Args:
            keyword: The search keyword to check.
            date_str: Date string (YYYY-MM-DD) for organizing screenshots.

        Returns:
            KeywordResult with all fields populated.
        """
        result = KeywordResult(keyword=keyword)
        notes_parts: list[str] = []

        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    logger.info(
                        "Retry %d/%d for keyword: %s",
                        attempt, self.max_retries, keyword,
                    )
                    await asyncio.sleep(2)

                # Navigate to Google search
                search_url = self._build_search_url(keyword)
                logger.info("Searching: %s", keyword)
                await self.browser.navigate(search_url)
                await self.browser.wait_for_page_load(timeout=self.page_load_timeout)

                # Check for consent/cookie dialogs and try to dismiss
                await self._handle_consent_dialog()

                # Small delay to let dynamic content render
                await asyncio.sleep(2)

                # Take screenshot
                screenshot_path = self._make_screenshot_path(keyword, date_str)
                try:
                    result.screenshot_path = await self.browser.screenshot(screenshot_path)
                    notes_parts.append(f"Screenshot saved: {result.screenshot_path}")
                except Exception as e:
                    notes_parts.append(f"Screenshot failed: {e}")
                    result.screenshot_path = ""

                # Detect AI Overview — try selectors first, then page source
                ai_found = False
                detection_note = ""

                ai_found, detection_note = await self._detect_ai_overview_via_selectors()
                if detection_note:
                    notes_parts.append(detection_note)

                if not ai_found:
                    # Fall back to page source analysis
                    page_source = await self.browser.get_page_source()
                    ai_found, detection_note = await self._detect_ai_overview_from_source(
                        page_source
                    )
                    if detection_note:
                        notes_parts.append(detection_note)

                result.ai_overview_present = ai_found

                # Extract citations if AI Overview is present
                if ai_found:
                    # Try selector-based extraction first
                    cited = await self._extract_citations_via_selectors()

                    if not cited:
                        # Fall back to source parsing
                        page_source = await self.browser.get_page_source()
                        cited = await self._extract_citations_from_source(page_source)
                        if cited:
                            notes_parts.append(
                                "Citations extracted from page source (less precise)"
                            )

                    result.cited_domains = cited
                    result.target_domain_cited = self._check_target_cited(cited)

                    if not cited:
                        notes_parts.append(
                            "AI Overview detected but no citations could be extracted. "
                            "Review screenshot for manual verification."
                        )
                else:
                    notes_parts.append("No AI Overview detected for this query")

                result.run_status = RunStatus.SUCCESS.value
                result.notes = "; ".join(notes_parts)
                return result

            except Exception as e:
                logger.error(
                    "Error checking keyword '%s' (attempt %d): %s",
                    keyword, attempt + 1, e,
                )
                notes_parts.append(f"Attempt {attempt + 1} error: {e}")

                if attempt == self.max_retries:
                    result.run_status = RunStatus.FAILED.value
                    result.notes = "; ".join(notes_parts)
                    return result

        # Should not reach here, but just in case
        result.run_status = RunStatus.FAILED.value
        result.notes = "; ".join(notes_parts)
        return result

    async def _handle_consent_dialog(self) -> None:
        """Try to dismiss Google's cookie consent dialog if present."""
        consent_selectors = [
            "button#L2AGLb",  # "I agree" button
            "button[aria-label='Accept all']",
            "button.tHlp8d",
            "form[action*='consent'] button",
        ]
        for selector in consent_selectors:
            try:
                exists = await self.browser.element_exists(selector)
                if exists:
                    await self.browser.click(selector)
                    logger.info("Dismissed consent dialog")
                    await asyncio.sleep(1)
                    return
            except Exception:
                continue

    async def check_keywords(
        self, keywords: list[str], date_str: str
    ) -> list[KeywordResult]:
        """Check multiple keywords sequentially with delays.

        Args:
            keywords: List of keywords to check.
            date_str: Date string for organizing output.

        Returns:
            List of KeywordResult objects.
        """
        results: list[KeywordResult] = []
        total = len(keywords)

        for i, keyword in enumerate(keywords, 1):
            logger.info("Checking keyword %d/%d: %s", i, total, keyword)
            result = await self.check_keyword(keyword, date_str)
            results.append(result)
            logger.info(
                "  → AI Overview: %s | Target cited: %s | Status: %s",
                result.ai_overview_present,
                result.target_domain_cited,
                result.run_status,
            )

            # Delay between searches to avoid rate limiting
            if i < total:
                logger.debug(
                    "Waiting %.1fs before next search...",
                    self.delay_between_searches,
                )
                await asyncio.sleep(self.delay_between_searches)

        return results
