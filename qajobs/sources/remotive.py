"""Remotive source (free public API: https://remotive.com/api/remote-jobs).

We query their software-dev category and a couple of QA-ish search terms to
keep the payload focused.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.remotive")

API_URL = "https://remotive.com/api/remote-jobs"
SEARCH_TERMS = ["qa", "test", "sdet", "quality"]


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        # e.g. "2026-07-02T20:01:13"
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def fetch(source_cfg: dict) -> List[Job]:
    seen_ids = set()
    jobs: List[Job] = []

    for term in SEARCH_TERMS:
        resp = get(API_URL, params={"search": term, "limit": 200})
        if resp is None:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue

        for item in data.get("jobs", []):
            jid = item.get("id")
            if jid in seen_ids:
                continue
            seen_ids.add(jid)

            jobs.append(
                Job(
                    source="Remotive",
                    title=(item.get("title") or "").strip(),
                    company=(item.get("company_name") or "").strip(),
                    url=item.get("url", ""),
                    location=item.get("candidate_required_location", "") or "Remote",
                    description=item.get("description", "") or "",
                    posted_at=_parse_date(item.get("publication_date")),
                    salary=item.get("salary", "") or "",
                    tags=[t for t in (item.get("tags") or []) if t],
                )
            )
    log.info("Remotive: %s raw jobs", len(jobs))
    return jobs
