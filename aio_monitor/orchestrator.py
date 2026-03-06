"""Main orchestrator — ties together browser, SERP checker, storage, and reporting.

This is the entry point for a daily monitoring run. It:
1. Loads configuration
2. Reads the keyword list
3. Initializes the browser engine and storage backend
4. Runs the SERP checker for each keyword
5. Saves results to the database
6. Generates the daily summary report
7. Exports CSV alongside the report
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml

from aio_monitor.browser.base import BrowserEngine
from aio_monitor.models import DailyRunSummary, KeywordResult
from aio_monitor.reporting.daily_report import ReportGenerator
from aio_monitor.serp_checker import SerpChecker
from aio_monitor.storage.base import StorageBackend
from aio_monitor.storage.sqlite_store import SQLiteStore

logger = logging.getLogger(__name__)


def load_config(config_path: str = "aio_monitor/config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}\n"
            f"Copy aio_monitor/config/config.yaml and customize it."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_keywords(keywords_file: str) -> list[str]:
    """Load keywords from a text file (one per line, # comments ignored)."""
    path = Path(keywords_file)
    if not path.exists():
        raise FileNotFoundError(f"Keywords file not found: {keywords_file}")

    keywords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                keywords.append(line)

    logger.info("Loaded %d keywords from %s", len(keywords), keywords_file)
    return keywords


def setup_logging(config: dict, base_dir: Path) -> None:
    """Configure logging based on config settings."""
    log_config = config.get("logging", {})
    level = getattr(logging, log_config.get("level", "INFO").upper(), logging.INFO)

    handlers: list[logging.Handler] = []

    # File handler
    log_file = log_config.get("log_file", "aio_monitor.log")
    log_path = base_dir / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_path), encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    handlers.append(file_handler)

    # Console handler
    if log_config.get("console", True):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        handlers.append(console_handler)

    logging.basicConfig(level=level, handlers=handlers, force=True)


def create_browser_engine(config: dict) -> BrowserEngine:
    """Create the appropriate browser engine based on config."""
    engine_type = config.get("browser_engine", "openclaw")

    if engine_type == "openclaw":
        from aio_monitor.browser.openclaw_engine import OpenClawEngine
        oc_config = config.get("openclaw", {})
        return OpenClawEngine(
            browser_profile=oc_config.get("browser_profile", "openclaw"),
            cli_path=oc_config.get("cli_path", ""),
            action_timeout=oc_config.get("action_timeout", 30),
        )
    elif engine_type == "playwright":
        from aio_monitor.browser.playwright_engine import PlaywrightEngine
        pw_config = config.get("playwright", {})
        return PlaywrightEngine(
            headless=pw_config.get("headless", True),
            viewport_width=pw_config.get("viewport_width", 1280),
            viewport_height=pw_config.get("viewport_height", 900),
            user_agent=pw_config.get("user_agent", ""),
        )
    elif engine_type == "selenium":
        from aio_monitor.browser.selenium_engine import SeleniumEngine
        se_config = config.get("selenium", config.get("playwright", {}))  # Fall back to playwright settings if no selenium section
        return SeleniumEngine(
            headless=se_config.get("headless", True),
            viewport_width=se_config.get("viewport_width", 1280),
            viewport_height=se_config.get("viewport_height", 900),
            user_agent=se_config.get("user_agent", ""),
        )
    else:
        raise ValueError(
            f"Unknown browser engine: {engine_type}. "
            f"Supported: openclaw, playwright, selenium"
        )


def create_storage(config: dict, base_dir: Path) -> StorageBackend:
    """Create the storage backend based on config."""
    output_config = config.get("output", {})
    db_name = output_config.get("db_name", "aio_monitor.db")
    db_path = base_dir / db_name
    return SQLiteStore(db_path)


async def run_daily_check(
    config_path: str = "aio_monitor/config/config.yaml",
    date_override: Optional[str] = None,
) -> DailyRunSummary:
    """Execute a full daily monitoring run.

    Args:
        config_path: Path to the YAML configuration file.
        date_override: Optional date string (YYYY-MM-DD) to use instead of today.

    Returns:
        DailyRunSummary with all results.
    """
    # Load config
    config = load_config(config_path)
    output_config = config.get("output", {})
    search_config = config.get("search", {})

    # Set up paths
    base_dir = Path(output_config.get("base_dir", "output"))
    base_dir.mkdir(parents=True, exist_ok=True)

    screenshots_dir = base_dir / output_config.get("screenshots_dir", "screenshots")
    reports_dir = base_dir / output_config.get("reports_dir", "reports")

    # Set up logging
    setup_logging(config, base_dir)

    # Date for this run
    date_str = date_override or datetime.utcnow().strftime("%Y-%m-%d")
    logger.info("=" * 60)
    logger.info("AI Overview Monitor — Daily Run: %s", date_str)
    logger.info("=" * 60)

    # Load keywords
    keywords = load_keywords(config.get("keywords_file", "aio_monitor/config/keywords.txt"))
    if not keywords:
        logger.warning("No keywords to check. Exiting.")
        return DailyRunSummary(run_date=date_str)

    # Initialize components
    browser = create_browser_engine(config)
    storage = create_storage(config, base_dir)
    storage.initialize()

    report_gen = ReportGenerator(reports_dir)

    serp_checker = SerpChecker(
        browser=browser,
        target_domains=config.get("target_domains", []),
        google_domain=search_config.get("google_domain", "https://www.google.com"),
        search_params=search_config.get("search_params", {"hl": "en", "gl": "us"}),
        screenshots_dir=str(screenshots_dir),
        delay_between_searches=search_config.get("delay_between_searches", 5),
        page_load_timeout=search_config.get("page_load_timeout", 30),
        max_retries=search_config.get("max_retries", 2),
    )

    results: list[KeywordResult] = []

    try:
        # Start browser
        logger.info("Starting browser engine: %s", config.get("browser_engine", "openclaw"))
        await browser.start()

        # Run checks
        results = await serp_checker.check_keywords(keywords, date_str)

        # Save results
        storage.save_results(results)
        logger.info("Results saved to database")

        # Export CSV
        csv_path = str(reports_dir / f"results_{date_str}.csv")
        storage.export_csv(csv_path, date_str)

    except Exception as e:
        logger.error("Fatal error during monitoring run: %s", e, exc_info=True)
    finally:
        # Always try to stop the browser
        try:
            await browser.stop()
        except Exception as e:
            logger.debug("Error stopping browser: %s", e)
        storage.close()

    # Generate summary and reports
    summary = DailyRunSummary.from_results(results, date_str)
    md_path, html_path = report_gen.generate(summary)

    logger.info("=" * 60)
    logger.info("Run complete. Summary:")
    logger.info("  Total keywords:      %d", summary.total_keywords)
    logger.info("  AI Overviews found:  %d", summary.ai_overview_count)
    logger.info("  Target domains cited: %d", summary.target_domain_cited_count)
    logger.info("  Failed checks:       %d", summary.failed_count)
    logger.info("  Markdown report:     %s", md_path)
    logger.info("  HTML report:         %s", html_path)
    logger.info("=" * 60)

    return summary
