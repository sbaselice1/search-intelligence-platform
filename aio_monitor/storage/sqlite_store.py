"""SQLite storage backend for AI Overview monitoring results."""

from __future__ import annotations

import csv
import logging
import sqlite3
from pathlib import Path
from typing import Optional

from aio_monitor.models import KeywordResult
from aio_monitor.storage.base import StorageBackend

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS keyword_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    ai_overview_present INTEGER,
    cited_domains TEXT DEFAULT '[]',
    target_domain_cited INTEGER DEFAULT 0,
    screenshot_path TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    run_status TEXT DEFAULT 'success',
    created_at TEXT DEFAULT (datetime('now'))
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_keyword_results_date
    ON keyword_results(checked_at);
CREATE INDEX IF NOT EXISTS idx_keyword_results_keyword
    ON keyword_results(keyword);
"""


class SQLiteStore(StorageBackend):
    """SQLite-backed storage for keyword monitoring results."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def initialize(self) -> None:
        """Create the results table and indexes if they don't exist."""
        logger.info("Initializing SQLite database at %s", self.db_path)
        self.conn.executescript(CREATE_TABLE_SQL + CREATE_INDEX_SQL)
        self.conn.commit()

    def save_result(self, result: KeywordResult) -> None:
        """Insert a single keyword result."""
        self.conn.execute(
            """
            INSERT INTO keyword_results
                (keyword, checked_at, ai_overview_present, cited_domains,
                 target_domain_cited, screenshot_path, notes, run_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.keyword,
                result.checked_at,
                1 if result.ai_overview_present else (0 if result.ai_overview_present is not None else None),
                result.cited_domains_json,
                1 if result.target_domain_cited else 0,
                result.screenshot_path,
                result.notes,
                result.run_status,
            ),
        )
        self.conn.commit()

    def save_results(self, results: list[KeywordResult]) -> None:
        """Insert multiple keyword results in a single transaction."""
        for result in results:
            self.conn.execute(
                """
                INSERT INTO keyword_results
                    (keyword, checked_at, ai_overview_present, cited_domains,
                     target_domain_cited, screenshot_path, notes, run_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.keyword,
                    result.checked_at,
                    1 if result.ai_overview_present else (0 if result.ai_overview_present is not None else None),
                    result.cited_domains_json,
                    1 if result.target_domain_cited else 0,
                    result.screenshot_path,
                    result.notes,
                    result.run_status,
                ),
            )
        self.conn.commit()
        logger.info("Saved %d results to SQLite", len(results))

    def get_results_by_date(self, date_str: str) -> list[KeywordResult]:
        """Retrieve all results where checked_at starts with the given date."""
        cursor = self.conn.execute(
            "SELECT * FROM keyword_results WHERE checked_at LIKE ? ORDER BY id",
            (f"{date_str}%",),
        )
        rows = cursor.fetchall()
        return [KeywordResult.from_row(dict(row)) for row in rows]

    def get_latest_result(self, keyword: str) -> Optional[KeywordResult]:
        """Get the most recent result for a keyword."""
        cursor = self.conn.execute(
            "SELECT * FROM keyword_results WHERE keyword = ? ORDER BY checked_at DESC LIMIT 1",
            (keyword,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return KeywordResult.from_row(dict(row))

    def export_csv(
        self,
        output_path: str,
        date_str: Optional[str] = None,
        results: Optional[list[KeywordResult]] = None,
    ) -> str:
        """Export results to a CSV file.

        If *results* is provided, write those directly (avoids date-mismatch
        when using --date override).  Otherwise fall back to querying the DB.
        """
        if results is None:
            if date_str:
                results = self.get_results_by_date(date_str)
            else:
                cursor = self.conn.execute(
                    "SELECT * FROM keyword_results ORDER BY checked_at DESC"
                )
                results = [KeywordResult.from_row(dict(row)) for row in cursor.fetchall()]

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "keyword", "checked_at", "ai_overview_present", "cited_domains",
            "target_domain_cited", "screenshot_path", "notes", "run_status",
        ]

        with open(output, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r.to_dict())

        logger.info("Exported %d results to %s", len(results), output_path)
        return str(output)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
