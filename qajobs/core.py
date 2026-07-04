"""Core logic: keyword matching, filtering, dedup, region flagging."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List

from .models import Job


def _text_blob(job: Job) -> str:
    # Coerce tags defensively -- a source may hand back non-string / nested
    # values, and we must never let that crash the whole run.
    tags = " ".join(str(t) for t in (job.tags or []) if t)
    return " ".join([job.title or "", job.description or "", job.location or "", tags]).lower()


def _location_blob(job: Job) -> str:
    """Text used for GEOGRAPHY decisions -- title + location + tags only.

    Deliberately excludes the description so a company listing its global
    offices ("... Japan, India, and the Philippines") doesn't get mis-tagged
    with a region it isn't actually hiring in.
    """
    tags = " ".join(str(t) for t in (job.tags or []) if t)
    return " ".join([job.title or "", job.location or "", tags]).lower()


def _contains_any(haystack: str, needles: Iterable[str], word_boundary: bool = False) -> bool:
    for n in needles:
        n = (n or "").strip().lower()
        if not n:
            continue
        # Short tokens (<=3, e.g. "qa") always use word boundaries to avoid
        # matching "equal"/"squad". When word_boundary=True (region terms like
        # "apac") we force boundaries for single alphabetic tokens so "apac"
        # won't match "capacity". Terms with dots/spaces (".co.id", "hong kong")
        # still match as substrings. 
        if word_boundary and n.isalpha():
            if re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", haystack):
                return True
        elif len(n) <= 3:
            if re.search(r"(?<![a-z])" + re.escape(n) + r"(?![a-z])", haystack):
                return True
        elif n in haystack:
            return True
    return False


def matches_keywords(job: Job, cfg: dict) -> bool:
    keywords = cfg.get("keywords", [])
    blob = _text_blob(job)
    if not _contains_any(blob, keywords):
        return False

    title = (job.title or "").lower()
    title_must = cfg.get("title_must_include", []) or []
    if title_must and not _contains_any(title, title_must):
        return False
    return True


def passes_filters(job: Job, cfg: dict) -> bool:
    filters = cfg.get("filters", {}) or {}

    # Exclude noisy titles.
    exclude_words = filters.get("exclude_title_words", []) or []
    if _contains_any((job.title or "").lower(), exclude_words):
        return False

    # Age filter.
    max_age = int(filters.get("max_age_days", 0) or 0)
    if max_age > 0 and job.posted_at is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age)
        posted = job.posted_at
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        if posted < cutoff:
            return False

    return True


def annotate_regions(job: Job, cfg: dict) -> None:
    region_flags: Dict[str, List[str]] = cfg.get("region_flags", {}) or {}
    # Use the location blob (not the description) with word-boundary matching so
    # a job is only flagged with a region it's actually in.
    blob = _location_blob(job)
    found = []
    for region, hints in region_flags.items():
        if _contains_any(blob, hints, word_boundary=True):
            found.append(region)
    job.regions = found


def annotate_seniority(job: Job, cfg: dict) -> None:
    boost = cfg.get("seniority_boost", []) or []
    job.is_senior = _contains_any((job.title or "").lower(), boost)


def _indonesia_dork_hit(job: Job, cfg: dict) -> bool:
    """True if a job matches the Indonesia dork targets (domains, or companies).

    Reuses `google_dorks.indonesia.domains` (and `companies` if you add any) as a
    single source of truth, so a .co.id/.id job from ANY API source scores in the
    Indonesia tier -- not just ones whose text says "Jakarta"/"Indonesia".
    """
    id_cfg = ((cfg.get("google_dorks", {}) or {}).get("indonesia", {}) or {})

    # Optional company names -> match against the (short, specific) company field
    # to avoid false positives from a name appearing deep in a description.
    company = (job.company or "").lower()
    for name in id_cfg.get("companies", []) or []:
        name = (name or "").strip().lower()
        if name and name in company:
            return True

    # Domains (co.id / id) -> match against the job URL, e.g. careers.gojek.co.id.
    url = (job.url or "").lower()
    for dom in id_cfg.get("domains", []) or []:
        dom = (dom or "").strip().lower().lstrip(".")
        if dom and (f".{dom}/" in url or url.endswith(f".{dom}") or f".{dom}?" in url):
            return True
    return False


def annotate_priority(job: Job, cfg: dict) -> None:
    """Score a job against the priority tiers (rank only, never filters).

    Sets job.score, job.priority_tier (highest matched tier), and
    job.priority_reasons (human-readable badges).
    """
    ps = cfg.get("priority_scoring", {}) or {}
    if not ps.get("enabled", False):
        return

    blob = _text_blob(job)
    # Region tiers are matched against the location blob (title/location/tags)
    # with word boundaries, so global-office mentions in the description don't
    # create false region hits and "apac" doesn't match "capacity".
    loc_blob = _location_blob(job)
    tiers = ps.get("tiers", []) or []
    boosts = ps.get("boosts", {}) or {}

    score = 0
    reasons: List[str] = []
    best_tier = ""
    best_points = -1

    for tier in tiers:
        name = tier.get("name", "") or ""
        points = int(tier.get("points", 0) or 0)
        matched = _contains_any(loc_blob, tier.get("match", []) or [], word_boundary=True)
        # Indonesia tier also reuses the dork company/domain targets.
        if tier.get("reuse_indonesia_dorks") and not matched:
            matched = _indonesia_dork_hit(job, cfg)
        if matched:
            score += points
            reasons.append(name)
            if points > best_points:
                best_points = points
                best_tier = name

    # Additive boosts on top of tier points.
    if job.is_senior and boosts.get("senior"):
        score += int(boosts["senior"])
        reasons.append("senior")
    remote_terms = ps.get("remote_terms", []) or []
    if boosts.get("remote") and _contains_any(blob, remote_terms):
        score += int(boosts["remote"])
        reasons.append("remote")
    if boosts.get("has_salary") and (job.salary or "").strip():
        score += int(boosts["has_salary"])
        reasons.append("salary")

    job.score = score
    job.priority_tier = best_tier
    job.priority_reasons = reasons


def process(jobs: Iterable[Job], cfg: dict) -> List[Job]:
    """Filter, annotate and dedup a stream of jobs.

    Returns a sorted list ranked by priority score (highest first), then senior,
    then newest. Scoring never filters jobs out -- it only affects ordering.
    """
    seen = {}
    for job in jobs:
        if not matches_keywords(job, cfg):
            continue
        if not passes_filters(job, cfg):
            continue
        annotate_regions(job, cfg)
        annotate_seniority(job, cfg)
        annotate_priority(job, cfg)

        # Dedup: keep the one with a real posted date if we have a choice.
        existing = seen.get(job.uid)
        if existing is None:
            seen[job.uid] = job
        elif existing.posted_at is None and job.posted_at is not None:
            seen[job.uid] = job

    result = list(seen.values())
    result.sort(
        key=lambda j: (
            -j.score,
            0 if j.is_senior else 1,
            -(j.posted_at.timestamp() if j.posted_at else 0),
            j.company.lower(),
        )
    )
    return result
