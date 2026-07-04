"""We Work Remotely source (RSS feeds).

WWR titles look like "Company: Position". Each item has a custom <region> tag
which we map into location. We pull a few relevant category feeds plus the
all-jobs feed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime
from typing import List

import feedparser

from ..models import Job

log = logging.getLogger("qajobs.weworkremotely")

FEEDS = [
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
    "https://weworkremotely.com/remote-jobs.rss",
]

# feedparser passes UA via its agent attr.
feedparser.USER_AGENT = "remote-qa-jobs/1.0 (personal-job-search-bot)"


def _split_title(raw: str) -> tuple[str, str]:
    """"Company: Position" -> (company, position). Fallback to ("", raw)."""
    if ":" in raw:
        company, _, position = raw.partition(":")
        return company.strip(), position.strip()
    return "", raw.strip()


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
    jobs: List[Job] = []
    seen_links = set()

    for feed_url in FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:  # feedparser is very tolerant, but be safe
            log.warning("WWR feed %s failed: %s", feed_url, exc)
            continue

        for entry in parsed.entries:
            link = getattr(entry, "link", "")
            if not link or link in seen_links:
                continue
            seen_links.add(link)

            company, position = _split_title(getattr(entry, "title", ""))
            region = getattr(entry, "region", "") or ""

            jobs.append(
                Job(
                    source="WeWorkRemotely",
                    title=position,
                    company=company,
                    url=link,
                    location=region or "Remote",
                    description=getattr(entry, "summary", "") or "",
                    posted_at=_parse_date(entry),
                    tags=[getattr(entry, "category", "")] if getattr(entry, "category", "") else [],
                )
            )

    log.info("WeWorkRemotely: %s raw jobs", len(jobs))
    return jobs
