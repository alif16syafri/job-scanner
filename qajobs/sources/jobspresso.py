"""Jobspresso source (free WordPress RSS feed).

No auth/key required. Jobspresso encodes company + location in the RSS <author>
field as "Company<br>⚲ Location". We split that out; the <summary> is the job
description.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from time import mktime
from typing import List

import feedparser

from ..models import Job

log = logging.getLogger("qajobs.jobspresso")

FEED_URL = "https://jobspresso.co/jobs/feed/"

feedparser.USER_AGENT = "remote-qa-jobs/1.0 (personal-job-search-bot)"


def _split_author(author: str) -> tuple[str, str]:
    """"Company<br>⚲ Location" -> (company, location)."""
    if not author:
        return "", ""
    # Normalize the <br> separator, strip the location pin glyph.
    parts = re.split(r"<br\s*/?>", author, maxsplit=1)
    company = parts[0].strip()
    location = ""
    if len(parts) > 1:
        location = re.sub(r"[⚲\u2690\u2691\s]+", " ", parts[1]).strip()
    return company, location


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
    except Exception as exc:  # feedparser is tolerant, but be safe
        log.warning("Jobspresso feed failed: %s", exc)
        return []

    jobs: List[Job] = []
    seen_links = set()
    for entry in parsed.entries:
        link = getattr(entry, "link", "")
        if not link or link in seen_links:
            continue
        seen_links.add(link)

        company, location = _split_author(getattr(entry, "author", "") or "")
        jobs.append(
            Job(
                source="Jobspresso",
                title=(getattr(entry, "title", "") or "").strip(),
                company=company,
                url=link,
                location=location or "Remote",
                description=getattr(entry, "summary", "") or "",
                posted_at=_parse_date(entry),
            )
        )

    log.info("Jobspresso: %s raw jobs", len(jobs))
    return jobs
