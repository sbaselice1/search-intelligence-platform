"""OpenClaw managed browser engine implementation.

Uses the `openclaw browser` CLI to control an isolated Chromium instance.
This is the primary/recommended engine for the AI Overview monitor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from aio_monitor.browser.base import BrowserEngine

logger = logging.getLogger(__name__)


class OpenClawEngine(BrowserEngine):
    """Browser engine backed by OpenClaw's managed browser CLI."""

    def __init__(
        self,
        browser_profile: str = "openclaw",
        cli_path: str = "",
        action_timeout: int = 30,
    ) -> None:
        self.browser_profile = browser_profile
        self.cli_path = cli_path or self._find_openclaw_cli()
        self.action_timeout = action_timeout
        self._started = False

    @staticmethod
    def _find_openclaw_cli() -> str:
        """Locate the openclaw CLI binary on PATH."""
        path = shutil.which("openclaw")
        if path:
            return path
        # Common install locations
        for candidate in [
            "/usr/local/bin/openclaw",
            "/usr/bin/openclaw",
            str(Path.home() / ".npm-global" / "bin" / "openclaw"),
        ]:
            if Path(candidate).is_file():
                return candidate
        return "openclaw"  # Fall back to bare name, let subprocess find it

    async def _run_cli(self, *args: str, timeout: Optional[float] = None) -> str:
        """Run an openclaw browser CLI command and return stdout."""
        cmd = [
            self.cli_path, "browser",
            "--browser-profile", self.browser_profile,
            *args,
        ]
        effective_timeout = timeout or self.action_timeout
        logger.debug("Running OpenClaw CLI: %s", " ".join(cmd))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"OpenClaw command timed out after {effective_timeout}s: {' '.join(cmd)}"
            )

        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode != 0:
            logger.error("OpenClaw CLI error (rc=%d): %s", proc.returncode, stderr_str)
            raise RuntimeError(
                f"OpenClaw command failed (rc={proc.returncode}): {stderr_str}"
            )

        if stderr_str:
            logger.debug("OpenClaw stderr: %s", stderr_str)

        return stdout_str

    async def start(self) -> None:
        """Start the OpenClaw managed browser."""
        logger.info("Starting OpenClaw managed browser (profile: %s)", self.browser_profile)
        try:
            status = await self._run_cli("status", "--json")
            logger.debug("Browser status: %s", status)
        except Exception:
            logger.info("Browser not running, starting it...")

        try:
            await self._run_cli("start")
            self._started = True
            logger.info("OpenClaw managed browser started")
        except Exception as e:
            logger.warning("Could not start OpenClaw browser: %s", e)
            raise

    async def navigate(self, url: str) -> None:
        """Navigate to a URL in the managed browser."""
        await self._run_cli("open", url)
        # Give the page a moment to settle
        await asyncio.sleep(2)

    async def screenshot(self, path: str | Path, full_page: bool = True) -> str:
        """Take a screenshot and save it to the given path."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # OpenClaw screenshot command outputs to a default location;
        # we capture and move it
        try:
            result = await self._run_cli("screenshot", "--json")
            # Parse the JSON to find the output path
            try:
                data = json.loads(result)
                src_path = data.get("path", "")
            except (json.JSONDecodeError, KeyError):
                # If not JSON, the output might be the path directly
                src_path = result.strip()

            if src_path and Path(src_path).exists() and str(Path(src_path)) != str(path):
                import shutil as sh
                sh.move(src_path, str(path))
            elif not Path(path).exists():
                # Fallback: try with explicit path argument
                await self._run_cli("screenshot", str(path))
        except Exception as e:
            logger.warning("Screenshot via OpenClaw failed: %s", e)
            raise

        return str(path)

    async def get_page_source(self) -> str:
        """Get the current page HTML via OpenClaw snapshot."""
        try:
            result = await self._run_cli("snapshot", "--html")
            return result
        except Exception:
            # Fallback: try extract_text
            return await self._run_cli("snapshot")

    async def get_page_text(self) -> str:
        """Get visible text content from the current page."""
        return await self._run_cli("snapshot")

    async def find_element_text(self, selector: str) -> Optional[str]:
        """Find element text — uses snapshot parsing."""
        # OpenClaw doesn't have direct CSS selector queries via CLI;
        # we get the full snapshot and note this limitation
        logger.debug(
            "OpenClaw CLI does not support direct CSS selector queries. "
            "Using page source parsing instead for selector: %s",
            selector,
        )
        return None  # Caller should fall back to page source parsing

    async def find_elements_text(self, selector: str) -> list[str]:
        """Find elements text — limited in CLI mode."""
        logger.debug("find_elements_text not directly supported via OpenClaw CLI")
        return []

    async def find_element_attribute(self, selector: str, attribute: str) -> Optional[str]:
        """Find element attribute — limited in CLI mode."""
        return None

    async def find_elements_attribute(self, selector: str, attribute: str) -> list[str]:
        """Find elements attribute — limited in CLI mode."""
        return []

    async def element_exists(self, selector: str) -> bool:
        """Check element existence — not directly supported, returns False."""
        return False

    async def type_text(self, selector: str, text: str) -> None:
        """Type text into an element using OpenClaw ref-based interaction."""
        # In OpenClaw, you'd typically snapshot first, find the ref, then type
        # This is a simplified version
        await self._run_cli("type", selector, text)

    async def click(self, selector: str) -> None:
        """Click an element using OpenClaw ref-based interaction."""
        await self._run_cli("click", selector)

    async def wait_for_selector(self, selector: str, timeout: float = 10.0) -> bool:
        """Wait for selector — not directly supported via CLI."""
        # OpenClaw CLI doesn't have a wait-for-selector command
        # We just wait and hope the element appears
        await asyncio.sleep(min(timeout, 3))
        return True

    async def wait_for_page_load(self, timeout: float = 30.0) -> None:
        """Wait for page load — simple delay in CLI mode."""
        await asyncio.sleep(3)

    async def stop(self) -> None:
        """Stop the managed browser if we started it."""
        if self._started:
            try:
                await self._run_cli("close")
                logger.info("OpenClaw managed browser closed")
            except Exception as e:
                logger.debug("Error closing OpenClaw browser: %s", e)
            self._started = False
