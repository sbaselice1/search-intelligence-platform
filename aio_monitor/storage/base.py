"""Abstract storage interface for AI Overview monitoring results.

Designed to be swappable — implement this protocol for BigQuery,
PostgreSQL, or any other backend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from aio_monitor.models import KeywordResult


class StorageBackend(ABC):
    """Abstract base class for result storage backends."""

    @abstractmethod
    def initialize(self) -> None:
        """Create tables/schema if they don't exist."""
        ...

    @abstractmethod
    def save_result(self, result: KeywordResult) -> None:
        """Persist a single keyword result."""
        ...

    @abstractmethod
    def save_results(self, results: list[KeywordResult]) -> None:
        """Persist multiple keyword results."""
        ...

    @abstractmethod
    def get_results_by_date(self, date_str: str) -> list[KeywordResult]:
        """Retrieve all results for a given date (YYYY-MM-DD)."""
        ...

    @abstractmethod
    def get_latest_result(self, keyword: str) -> Optional[KeywordResult]:
        """Get the most recent result for a keyword."""
        ...

    @abstractmethod
    def export_csv(
        self,
        output_path: str,
        date_str: Optional[str] = None,
        results: Optional[list[KeywordResult]] = None,
    ) -> str:
        """Export results to CSV. Returns the path written.

        If *results* is provided, write those directly instead of querying
        the database (avoids date-mismatch when using --date override).
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        ...
