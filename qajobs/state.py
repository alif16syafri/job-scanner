"""Persist which jobs we've already seen, for 'new job' detection."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List

from .models import Job

log = logging.getLogger("qajobs.state")


def load_seen(path: str) -> Dict[str, str]:
    if not path or not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (ValueError, OSError) as exc:
        log.warning("Could not read seen-cache %s: %s", path, exc)
        return {}


def split_new(jobs: Iterable[Job], seen: Dict[str, str]) -> List[Job]:
    """Return only jobs whose uid isn't in the seen cache."""
    return [j for j in jobs if j.uid not in seen]


def save_seen(path: str, jobs: Iterable[Job], seen: Dict[str, str]) -> None:
    if not path:
        return
    now = datetime.now(timezone.utc).isoformat()
    for j in jobs:
        seen.setdefault(j.uid, now)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(seen, fh, indent=2)
    except OSError as exc:
        log.warning("Could not write seen-cache %s: %s", path, exc)
