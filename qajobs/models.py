"""Shared data model for a normalized job posting."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import List, Optional


@dataclass
class Job:
    """A normalized job posting from any source."""

    source: str
    title: str
    company: str
    url: str
    location: str = ""
    description: str = ""
    posted_at: Optional[datetime] = None
    salary: str = ""
    tags: List[str] = field(default_factory=list)

    # Derived / annotated fields (filled in by core.py).
    regions: List[str] = field(default_factory=list)
    is_senior: bool = False

    # Priority scoring (filled in by core.py). `priority_tier` is the highest
    # matched tier label (e.g. "Indonesia"); `score` is the numeric rank used
    # for sorting; `priority_reasons` explains why (shown as badges).
    score: int = 0
    priority_tier: str = ""
    priority_reasons: List[str] = field(default_factory=list)

    @property
    def uid(self) -> str:
        """Stable unique id used for dedup and 'new job' detection.

        Based on company + title + url so the same job from two sources or
        two runs collapses to one entry.
        """
        raw = f"{self.company.strip().lower()}|{self.title.strip().lower()}|{self.url.strip()}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def posted_at_str(self) -> str:
        if not self.posted_at:
            return ""
        return self.posted_at.strftime("%Y-%m-%d")

    def to_row(self) -> dict:
        """Flat dict for CSV / HTML rendering."""
        d = asdict(self)
        d.pop("posted_at", None)
        d["posted_at"] = self.posted_at_str()
        d["regions"] = ", ".join(self.regions)
        d["tags"] = ", ".join(self.tags)
        d["priority_reasons"] = ", ".join(self.priority_reasons)
        d["uid"] = self.uid
        return d
