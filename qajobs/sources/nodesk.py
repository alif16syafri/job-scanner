"""NoDesk source (free RSS feed: https://nodesk.co/remote-jobs/index.xml).

No auth/key required. The feed is minimal: titles look like "Role at Company"
and there's no dedicated location/salary field, so we split the title and leave
location as "Remote".
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime
from typing import List

import feedparser

from ..models import Job

log = logging.getLogger("qajobs.nodesk")

FEED_URL = "https://nodesk.co/remote-jobs/index.xml"

feedparser.USER_AGENT = "remote-qa-jobs/1.0 (personal-job-search-bot)"


def _split_title(raw: str) -> tuple[str, str]:
    """"Role at Company" -> (title, company). Split on the LAST ' at '."""
    raw = (raw or "").strip()
    idx = raw.rfind(" at ")
    if idx > 0:
        return raw[:idx].strip(), raw[idx + 4 :].strip()
    return raw, ""


def _parse_date(entry) -> datetime | None:
    for attr in ("published_parsed", "updated_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime.fromtimestamp(mktime(val), tz=timezone.utc)
            except (ValueError, OverflowError):
                continue
    return None


def fetch(source_cfg: dict) -> List[Job]:
    try:
        parsed = feedparser.parse(FEED_URL)
    except Exception as exc:
        log.warning("NoDesk feed failed: %s", exc)
        return []

    jobs: List[Job] = []
    seen_links = set()
    for entry in parsed.entries:
        link = getattr(entry, "link", "")
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        title, company = _split_title(getattr(entry, "title", ""))
        jobs.append(
            Job(
                source="NoDesk",
                title=title,
                company=company,
                url=link,
                location="Remote",
                description=getattr(entry, "summary", "") or "",
                posted_at=_parse_date(entry),
            )
        )

    log.info("NoDesk: %s raw jobs", len(jobs))
    return jobs
