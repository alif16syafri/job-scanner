"""Shared HTTP helpers with a polite user-agent, timeouts and retries."""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests

log = logging.getLogger("qajobs.http")

USER_AGENT = (
    "remote-qa-jobs/1.0 (+https://github.com/) "
    "personal-job-search-bot; contact via config"
)

DEFAULT_TIMEOUT = 25


def get(url: str, *, params: Optional[dict] = None, headers: Optional[dict] = None,
        retries: int = 2) -> Optional[requests.Response]:
    """GET with retries. Returns Response or None on failure."""
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, text/*"}
    if headers:
        hdrs.update(headers)

    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, params=params, headers=hdrs, timeout=DEFAULT_TIMEOUT)
            if resp.status_code == 200:
                return resp
            log.warning("GET %s -> HTTP %s (attempt %s)", url, resp.status_code, attempt + 1)
        except requests.RequestException as exc:
            log.warning("GET %s failed: %s (attempt %s)", url, exc, attempt + 1)
        if attempt < retries:
            time.sleep(1.5 * (attempt + 1))
    return None
