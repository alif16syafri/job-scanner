#!/usr/bin/env python3
"""Remote QA / Senior QA Engineer job scanner.

Scans multiple remote job boards, filters for QA-ish roles, and writes a CSV +
HTML dashboard. Optionally sends Telegram notifications for NEW jobs.

Usage:
    python main.py                      # use config.yaml
    python main.py --config other.yaml
    python main.py --no-telegram        # skip notifications this run
    python main.py --all                # ignore the "only new" telegram setting
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import List

import yaml

from qajobs import core, outputs, state
from qajobs.models import Job
from qajobs.sources import (
    adzuna,
    arbeitnow,
    greenhouse,
    himalayas,
    jobicy,
    jobspresso,
    jooble,
    lever,
    nodesk,
    remoteok,
    remotive,
    weworkremotely,
    workingnomads,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("qajobs.main")

# Map config source keys -> (fetch fn, needs source_cfg dict?)
API_SOURCES = {
    "remoteok": remoteok.fetch,
    "remotive": remotive.fetch,
    "weworkremotely": weworkremotely.fetch,
    "himalayas": himalayas.fetch,
    "arbeitnow": arbeitnow.fetch,
    "jobicy": jobicy.fetch,
    "workingnomads": workingnomads.fetch,
    "jobspresso": jobspresso.fetch,
    "nodesk": nodesk.fetch,
    "adzuna": adzuna.fetch,
    "jooble": jooble.fetch,
}
BOARD_SOURCES = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
}


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def gather(cfg: dict) -> List[Job]:
    sources_cfg = cfg.get("sources", {}) or {}
    raw: List[Job] = []

    for key, fn in API_SOURCES.items():
        sc = sources_cfg.get(key, {}) or {}
        if not sc.get("enabled", False):
            continue
        log.info("Fetching source: %s", key)
        try:
            raw.extend(fn(sc))
        except Exception as exc:  # keep going even if a source breaks
            log.warning("Source %s failed: %s", key, exc)

    for key, fn in BOARD_SOURCES.items():
        sc = sources_cfg.get(key, {}) or {}
        if not sc.get("enabled", False):
            continue
        log.info("Fetching board source: %s (%s companies)", key, len(sc.get("companies", [])))
        try:
            raw.extend(fn(sc))
        except Exception as exc:
            log.warning("Board source %s failed: %s", key, exc)

    log.info("Total raw jobs gathered: %s", len(raw))
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Remote QA job scanner")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-telegram", action="store_true", help="Skip Telegram this run")
    parser.add_argument("--all", action="store_true",
                        help="Notify all matches, not just new ones")
    args = parser.parse_args()

    if not os.path.exists(args.config):
        log.error("Config file not found: %s", args.config)
        return 2

    cfg = load_config(args.config)

    raw = gather(cfg)
    jobs = core.process(raw, cfg)
    log.info("Jobs after filtering/dedup: %s (senior: %s)",
             len(jobs), sum(1 for j in jobs if j.is_senior))

    # New-job detection.
    state_cfg = cfg.get("state", {}) or {}
    seen_path = state_cfg.get("seen_cache_file", "output/seen_jobs.json")
    seen = state.load_seen(seen_path)
    new_jobs = state.split_new(jobs, seen)
    log.info("New jobs since last run: %s", len(new_jobs))

    # --- Outputs ---
    out_cfg = cfg.get("output", {}) or {}
    out_dir = out_cfg.get("dir", "output")
    os.makedirs(out_dir, exist_ok=True)

    search_cfg = (cfg.get("sources", {}) or {}).get("search_url_helper", {}) or {}
    search_links = []
    if search_cfg.get("enabled", True):
        search_links = outputs.build_search_urls(search_cfg.get("queries", []))

    dork_groups = outputs.build_google_dorks(cfg)
    if dork_groups:
        total_dorks = sum(len(g["links"]) for g in dork_groups)
        log.info("Google dorks: %s links across %s groups", total_dorks, len(dork_groups))

    stats = {
        "matches": len(jobs),
        "senior": sum(1 for j in jobs if j.is_senior),
        "new": len(new_jobs),
    }

    if out_cfg.get("csv", True):
        outputs.write_csv(jobs, os.path.join(out_dir, "qa_jobs.csv"))
    if out_cfg.get("html", True):
        outputs.write_html(jobs, os.path.join(out_dir, "index.html"), search_links, stats,
                           dork_groups)
    if out_cfg.get("json", False):
        outputs.write_json(jobs, os.path.join(out_dir, "qa_jobs.json"))

    # --- Telegram ---
    tg_cfg = cfg.get("telegram", {}) or {}
    if not args.no_telegram:
        only_new = tg_cfg.get("only_new", True) and not args.all
        notify = new_jobs if only_new else jobs
        outputs.send_telegram(notify, cfg)

    # Update seen cache last, so a crash mid-run doesn't hide jobs next time.
    state.save_seen(seen_path, jobs, seen)

    log.info("Done. Open %s/index.html", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
