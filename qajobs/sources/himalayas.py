"""Himalayas source (public jobs API: https://himalayas.app/jobs/api)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.himalayas")

API_URL = "https://himalayas.app/jobs/api"


def _parse_epoch(raw) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def _salary(item: dict) -> str:
    lo = item.get("minSalary")
    hi = item.get("maxSalary")
    cur = item.get("currency") or ""
    if lo and hi:
        return f"{cur}{lo:,} - {cur}{hi:,}".strip()
    return ""


def fetch(source_cfg: dict) -> List[Job]:
    jobs: List[Job] = []
    offset = 0
    page_size = 100
    max_pages = 10  # cap so we don't hammer the API

    for _ in range(max_pages):
        resp = get(API_URL, params={"limit": page_size, "offset": offset})
        if resp is None:
            break
        try:
            data = resp.json()
        except ValueError:
            break

        page = data.get("jobs", [])
        if not page:
            break

        for item in page:
            location = ", ".join(item.get("locationRestrictions") or []) or "Remote"
            tags = list(item.get("categories") or []) + list(item.get("seniority") or [])
            jobs.append(
                Job(
                    source="Himalayas",
                    title=(item.get("title") or "").strip(),
                    company=(item.get("companyName") or "").strip(),
                    url=item.get("applicationLink") or item.get("guid", ""),
                    location=location,
                    description=item.get("description", "") or item.get("excerpt", "") or "",
                    posted_at=_parse_epoch(item.get("pubDate")),
                    salary=_salary(item),
                    tags=[t for t in tags if t],
                )
            )

        total = data.get("totalCount", 0)
        offset += page_size
        if offset >= total:
            break

    log.info("Himalayas: %s raw jobs", len(jobs))
    return jobs
