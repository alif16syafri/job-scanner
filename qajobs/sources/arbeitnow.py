"""Arbeitnow source (free public API: https://www.arbeitnow.com/api/job-board-api).

No auth/key required. The feed is Europe-heavy and includes both remote and
on-site roles, so we paginate a few pages and let core.py handle keyword/region
filtering. `created_at` is epoch seconds.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.arbeitnow")

API_URL = "https://www.arbeitnow.com/api/job-board-api"


def _parse_epoch(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def fetch(source_cfg: dict) -> List[Job]:
    max_pages = int(source_cfg.get("max_pages", 5) or 5)
    jobs: List[Job] = []
    seen_slugs = set()

    for page in range(1, max_pages + 1):
        resp = get(API_URL, params={"page": page})
        if resp is None:
            break
        try:
            data = resp.json()
        except ValueError:
            break

        items = data.get("data", []) if isinstance(data, dict) else data
        if not items:
            break

        for item in items:
            slug = item.get("slug") or item.get("url")
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            remote = item.get("remote")
            location = item.get("location", "") or ""
            if remote and location:
                location = f"{location} (remote)"
            elif remote:
                location = "Remote"

            jobs.append(
                Job(
                    source="Arbeitnow",
                    title=(item.get("title") or "").strip(),
                    company=(item.get("company_name") or "").strip(),
                    url=item.get("url", ""),
                    location=location or "Remote",
                    description=item.get("description", "") or "",
                    posted_at=_parse_epoch(item.get("created_at")),
                    tags=[t for t in (item.get("tags") or []) if t]
                    + [t for t in (item.get("job_types") or []) if t],
                )
            )

    log.info("Arbeitnow: %s raw jobs", len(jobs))
    return jobs
