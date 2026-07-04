"""Job source fetchers.

Each fetcher exposes `fetch(source_cfg: dict) -> List[Job]` and should never
raise; on error it logs and returns an empty list so one bad source doesn't
kill the whole run.
"""

from . import remoteok, remotive, weworkremotely, himalayas, greenhouse, lever

__all__ = [
    "remoteok",
    "remotive",
    "weworkremotely",
    "himalayas",
    "greenhouse",
    "lever",
]
