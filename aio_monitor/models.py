"""Data models for AI Overview monitoring results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class RunStatus(str, Enum):
    """Status of a keyword check run."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class KeywordResult:
    """Result of checking a single keyword for AI Overview presence."""

    keyword: str
    checked_at: str = ""
    ai_overview_present: Optional[bool] = None
    cited_domains: list[str] = field(default_factory=list)
    target_domain_cited: bool = False
    screenshot_path: str = ""
    notes: str = ""
    run_status: str = RunStatus.SUCCESS.value

    def __post_init__(self) -> None:
        if not self.checked_at:
            self.checked_at = datetime.utcnow().isoformat()

    @property
    def cited_domains_json(self) -> str:
        """Return cited_domains as a JSON string for storage."""
        return json.dumps(self.cited_domains)

    @classmethod
    def from_row(cls, row: dict) -> KeywordResult:
        """Create a KeywordResult from a database row dictionary."""
        cited = row.get("cited_domains", "[]")
        if isinstance(cited, str):
            try:
                cited = json.loads(cited)
            except (json.JSONDecodeError, TypeError):
                cited = []
        return cls(
            keyword=row["keyword"],
            checked_at=row.get("checked_at", ""),
            ai_overview_present=bool(row["ai_overview_present"]) if row.get("ai_overview_present") is not None else None,
            cited_domains=cited,
            target_domain_cited=bool(row.get("target_domain_cited", False)),
            screenshot_path=row.get("screenshot_path", ""),
            notes=row.get("notes", ""),
            run_status=row.get("run_status", RunStatus.SUCCESS.value),
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        d = asdict(self)
        d["cited_domains"] = self.cited_domains_json
        return d


@dataclass
class DailyRunSummary:
    """Summary statistics for a daily monitoring run."""

    run_date: str
    total_keywords: int = 0
    ai_overview_count: int = 0
    target_domain_cited_count: int = 0
    failed_count: int = 0
    top_cited_domains: dict[str, int] = field(default_factory=dict)
    results: list[KeywordResult] = field(default_factory=list)

    @classmethod
    def from_results(cls, results: list[KeywordResult], run_date: str) -> DailyRunSummary:
        """Build summary from a list of keyword results."""
        summary = cls(run_date=run_date)
        summary.results = results
        summary.total_keywords = len(results)

        domain_counts: dict[str, int] = {}
        for r in results:
            if r.run_status == RunStatus.FAILED.value:
                summary.failed_count += 1
                continue
            if r.ai_overview_present:
                summary.ai_overview_count += 1
            if r.target_domain_cited:
                summary.target_domain_cited_count += 1
            for domain in r.cited_domains:
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Sort domains by count descending
        summary.top_cited_domains = dict(
            sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)
        )
        return summary
