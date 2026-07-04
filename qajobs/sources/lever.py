"""Lever-hosted company boards.

Public API: https://api.lever.co/v0/postings/<slug>?mode=json
No auth required. Add company slugs in config.yaml under sources.lever.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.lever")

API_TMPL = "https://api.lever.co/v0/postings/{slug}"


def _parse_epoch_ms(raw) -> datetime | None:
    if not raw:
        return None
    try:
        # Lever createdAt is epoch milliseconds.
        return datetime.fromtimestamp(int(raw) / 1000.0, tz=timezone.utc)
    except (ValueError, OSError, TypeError):
        return None


def _fetch_company(slug: str) -> List[Job]:
    resp = get(API_TMPL.format(slug=slug), params={"mode": "json"})
    if resp is None:
        return []
    try:
        data = resp.json()
    except ValueError:
        return []
    if not isinstance(data, list):
        return []

    jobs: List[Job] = []
    for item in data:
        categories = item.get("categories") or {}
        location = categories.get("location", "") or ""
        commitment = categories.get("commitment", "") or ""
        team = categories.get("team", "") or ""

        description = item.get("descriptionPlain") or item.get("description") or ""

        jobs.append(
            Job(
                source=f"Lever:{slug}",
                title=(item.get("text") or "").strip(),
                company=slug,
                url=item.get("hostedUrl") or item.get("applyUrl", ""),
                location=location or "Remote",
                description=description,
                posted_at=_parse_epoch_ms(item.get("createdAt")),
                tags=[t for t in [team, commitment] if t],
            )
        )
    log.info("Lever:%s -> %s jobs", slug, len(jobs))
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
        except Exception as exc:
            log.warning("Lever:%s failed: %s", slug, exc)
    return jobs
