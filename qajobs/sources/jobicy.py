"""Jobicy source (free public API: https://jobicy.com/api/v2/remote-jobs).

No auth/key required. Remote-only listings. We query a few QA-ish search terms
and dedupe by job id. Note: the `tag` filter needs >=3 chars (e.g. "qa" returns
nothing), so we use "quality"/"test"/"sdet"/"engineer".
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.jobicy")

API_URL = "https://jobicy.com/api/v2/remote-jobs"
SEARCH_TERMS = ["quality", "test", "sdet", "qa engineer", "automation"]


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    raw = str(raw).strip().replace("Z", "+00:00")
    # Try ISO first, then a couple of common fallbacks.
    for fmt in (None, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.fromisoformat(raw) if fmt is None else datetime.strptime(raw, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _salary(item: dict) -> str:
    lo = item.get("annualSalaryMin") or item.get("salaryMin")
    hi = item.get("annualSalaryMax") or item.get("salaryMax")
    cur = item.get("salaryCurrency") or ""
    if lo and hi:
        return f"{cur}{lo:,} - {cur}{hi:,}".strip()
    return ""


def fetch(source_cfg: dict) -> List[Job]:
    seen_ids = set()
    jobs: List[Job] = []

    for term in SEARCH_TERMS:
        resp = get(API_URL, params={"count": 100, "tag": term})
        if resp is None:
            continue
        try:
            data = resp.json()
        except ValueError:
            continue

        for item in data.get("jobs", []) or []:
            jid = item.get("id")
            if jid in seen_ids:
                continue
            seen_ids.add(jid)

            geo = item.get("jobGeo", "") or "Anywhere"

            # jobLevel is usually a string; jobIndustry/jobType come back as
            # lists. Flatten everything to a clean list of string tags.
            def _as_list(val):
                if isinstance(val, list):
                    return [str(v).strip() for v in val if v]
                return [str(val).strip()] if val else []

            tags = [
                t
                for t in _as_list(item.get("jobLevel"))
                + _as_list(item.get("jobIndustry"))
                if t and t.lower() != "any"
            ]

            jobs.append(
                Job(
                    source="Jobicy",
                    title=(item.get("jobTitle") or "").strip(),
                    company=(item.get("companyName") or "").strip(),
                    url=item.get("url", ""),
                    location=geo,
                    description=item.get("jobDescription", "")
                    or item.get("jobExcerpt", "")
                    or "",
                    posted_at=_parse_date(item.get("pubDate")),
                    salary=_salary(item),
                    tags=tags,
                )
            )

    log.info("Jobicy: %s raw jobs", len(jobs))
    return jobs
