"""Adzuna source (requires a free API key: https://developer.adzuna.com/).

Set credentials via env vars (defaults ADZUNA_APP_ID / ADZUNA_APP_KEY). Adzuna
only covers a fixed country set (gb, us, au, ca, de, fr, in, nl, pl, sg, ...) --
notably NOT Indonesia or GCC -- so it's OFF by default. Enable + set countries
you care about (e.g. "sg", "in") in config.yaml.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import List

from ..http import get
from ..models import Job

log = logging.getLogger("qajobs.adzuna")

API_TMPL = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


def _parse_date(raw) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _salary(item: dict) -> str:
    lo = item.get("salary_min")
    hi = item.get("salary_max")
    if lo and hi:
        return f"{int(lo):,} - {int(hi):,}"
    return ""


def fetch(source_cfg: dict) -> List[Job]:
    app_id = os.environ.get(source_cfg.get("app_id_env", "ADZUNA_APP_ID"), "")
    app_key = os.environ.get(source_cfg.get("app_key_env", "ADZUNA_APP_KEY"), "")
    if not app_id or not app_key:
        log.info("Adzuna enabled but ADZUNA_APP_ID/KEY missing; skipping.")
        return []

    countries = source_cfg.get("countries", ["gb"]) or ["gb"]
    queries = source_cfg.get("queries", ["QA engineer", "SDET"]) or ["QA engineer"]
    max_pages = int(source_cfg.get("max_pages", 1) or 1)
    per_page = int(source_cfg.get("results_per_page", 50) or 50)

    jobs: List[Job] = []
    for country in countries:
        for what in queries:
            for page in range(1, max_pages + 1):
                resp = get(
                    API_TMPL.format(country=country, page=page),
                    params={
                        "app_id": app_id,
                        "app_key": app_key,
                        "results_per_page": per_page,
                        "what": what,
                        "content-type": "application/json",
                    },
                )
                if resp is None:
                    break
                try:
                    data = resp.json()
                except ValueError:
                    break

                results = data.get("results", []) or []
                if not results:
                    break

                for item in results:
                    company = ((item.get("company") or {}).get("display_name") or "").strip()
                    location = ((item.get("location") or {}).get("display_name") or "").strip()
                    jobs.append(
                        Job(
                            source=f"Adzuna:{country}",
                            title=(item.get("title") or "").strip(),
                            company=company,
                            url=item.get("redirect_url", ""),
                            location=location or "Remote",
                            description=item.get("description", "") or "",
                            posted_at=_parse_date(item.get("created")),
                            salary=_salary(item),
                            tags=[(item.get("category") or {}).get("label", "")]
                            if item.get("category")
                            else [],
                        )
                    )

    log.info("Adzuna: %s raw jobs", len(jobs))
    return jobs
