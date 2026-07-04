"""RemoteOK source (free public API: https://remoteok.com/api).

Per their ToS we link back to Remote OK as the source (job URLs point there).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.remoteok")

API_URL = "https://remoteok.com/api"


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        # e.g. "2026-07-03T09:08:50+00:00"
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def fetch(source_cfg: dict) -> List[Job]:
    resp = get(API_URL)
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        log.warning("RemoteOK returned non-JSON")
        return []

    jobs: List[Job] = []
    for item in data:
        # First element is a metadata/legal object, skip anything without a position.
        if not isinstance(item, dict) or not item.get("position"):
            continue

        url = item.get("url") or (
            "https://remoteok.com/remote-jobs/" + str(item.get("slug", "")).strip("/")
        )
        posted = _parse_date(item.get("date"))
        if posted is None and item.get("epoch"):
            try:
                posted = datetime.fromtimestamp(int(item["epoch"]), tz=timezone.utc)
            except (ValueError, OSError):
                posted = None

        jobs.append(
            Job(
                source="RemoteOK",
                title=item.get("position", "").strip(),
                company=item.get("company", "").strip(),
                url=url,
                location=item.get("location", "") or "Remote",
                description=item.get("description", "") or "",
                posted_at=posted,
                salary=_salary(item),
                tags=[t for t in (item.get("tags") or []) if t],
            )
        )
    log.info("RemoteOK: %s raw jobs", len(jobs))
    return jobs


def _salary(item: dict) -> str:
    lo = item.get("salary_min")
    hi = item.get("salary_max")
    if lo and hi:
        return f"${lo:,} - ${hi:,}"
    return ""
