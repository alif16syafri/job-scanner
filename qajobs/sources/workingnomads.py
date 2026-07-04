"""Working Nomads source (free JSON feed: /api/exposed_jobs/).

No auth/key required, but the endpoint expects a browser-like User-Agent. It
returns the full remote-jobs list as JSON; we filter for QA-ish roles in
core.py. `tags` is a comma-separated string; `pub_date` is ISO w/ offset.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.workingnomads")

API_URL = "https://www.workingnomads.com/api/exposed_jobs/"
# The exposed feed rejects our default UA; use a browser-like one.
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def fetch(source_cfg: dict) -> List[Job]:
    resp = get(API_URL, headers={"User-Agent": BROWSER_UA})
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        log.warning("Working Nomads returned non-JSON")
        return []
    if not isinstance(data, list):
        return []

    jobs: List[Job] = []
    for item in data:
        raw_tags = item.get("tags") or ""
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()] if isinstance(raw_tags, str) else []
        category = item.get("category_name", "") or ""
        if category:
            tags.append(category)

        jobs.append(
            Job(
                source="WorkingNomads",
                title=(item.get("title") or "").strip(),
                company=(item.get("company_name") or "").strip(),
                url=item.get("url", ""),
                location=item.get("location", "") or "Remote",
                description=item.get("description", "") or "",
                posted_at=_parse_date(item.get("pub_date")),
                tags=tags,
            )
        )

    log.info("WorkingNomads: %s raw jobs", len(jobs))
    return jobs
