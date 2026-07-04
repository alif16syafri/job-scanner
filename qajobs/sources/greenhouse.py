"""Greenhouse-hosted company boards.

Public API: https://boards-api.greenhouse.io/v1/boards/<slug>/jobs?content=true
No auth required. Add company slugs in config.yaml under sources.greenhouse.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.greenhouse")

API_TMPL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        # e.g. "2026-06-05T16:18:10-04:00"
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def _fetch_company(slug: str) -> List[Job]:
    resp = get(API_TMPL.format(slug=slug), params={"content": "true"})
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []

    jobs: List[Job] = []
    for item in data.get("jobs", []):
        location = ""
        loc = item.get("location")
        if isinstance(loc, dict):
            location = loc.get("name", "") or ""

        jobs.append(
            Job(
                source=f"Greenhouse:{slug}",
                title=(item.get("title") or "").strip(),
                company=item.get("company_name") or slug,
                url=item.get("absolute_url", ""),
                location=location or "Remote",
                # content is HTML-escaped; good enough for keyword scanning.
                description=item.get("content", "") or "",
                posted_at=_parse_date(item.get("updated_at") or item.get("first_published")),
                tags=[d.get("name", "") for d in (item.get("departments") or []) if d.get("name")],
            )
        )
    log.info("Greenhouse:%s -> %s jobs", slug, len(jobs))
    return jobs


def fetch(source_cfg: dict) -> List[Job]:
    companies = source_cfg.get("companies", []) or []
    jobs: List[Job] = []
    for slug in companies:
        slug = (slug or "").strip()
        if not slug:
            continue
        try:
            jobs.extend(_fetch_company(slug))
        except Exception as exc:  # never let one board kill the run
            log.warning("Greenhouse:%s failed: %s", slug, exc)
    return jobs
