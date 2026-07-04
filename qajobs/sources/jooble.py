"""Jooble source (requires a free API key: https://jooble.org/api/about).

Global aggregator -- unlike Adzuna it covers Indonesia + GCC, so it's the most
useful optional source for those priorities. Uses a POST to
https://jooble.org/api/{key} with a JSON body. OFF by default; enable in
config.yaml and set JOOBLE_API_KEY.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List

import requests

from ..http import USER_AGENT
from ..models import Job

log = logging.getLogger("qajobs.jooble")

API_TMPL = "https://jooble.org/api/{key}"
TIMEOUT = 25


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _query(key: str, keywords: str, location: str, page: int) -> list:
    body = {"keywords": keywords, "page": str(page)}
    if location:
        body["location"] = location
    try:
        resp = requests.post(
            API_TMPL.format(key=key),
            json=body,
            headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            log.warning("Jooble HTTP %s for '%s'/'%s'", resp.status_code, keywords, location)
            return []
        return resp.json().get("jobs", []) or []
    except (requests.RequestException, ValueError) as exc:
        log.warning("Jooble request failed (%s/%s): %s", keywords, location, exc)
        return []


def fetch(source_cfg: dict) -> List[Job]:
    key = os.environ.get(source_cfg.get("api_key_env", "JOOBLE_API_KEY"), "")
    if not key:
        log.info("Jooble enabled but JOOBLE_API_KEY missing; skipping.")
        return []

    keywords = source_cfg.get("keywords", ["QA Engineer", "SDET"]) or ["QA Engineer"]
    locations = source_cfg.get("locations", ["Indonesia", "Remote"]) or [""]
    max_pages = int(source_cfg.get("max_pages", 1) or 1)

    jobs: List[Job] = []
    seen_ids = set()

    for kw in keywords:
        for loc in locations:
            for page in range(1, max_pages + 1):
                for item in _query(key, kw, loc, page):
                    jid = item.get("id") or item.get("link")
                    if not jid or jid in seen_ids:
                        continue
                    seen_ids.add(jid)
                    jobs.append(
                        Job(
                            source="Jooble",
                            title=(item.get("title") or "").strip(),
                            company=(item.get("company") or "").strip(),
                            url=item.get("link", ""),
                            location=item.get("location", "") or loc or "Remote",
                            description=item.get("snippet", "") or "",
                            posted_at=_parse_date(item.get("updated")),
                            salary=item.get("salary", "") or "",
                            tags=[t for t in [item.get("type", "")] if t],
                        )
                    )

    log.info("Jooble: %s raw jobs", len(jobs))
    return jobs
