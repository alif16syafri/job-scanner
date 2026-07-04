"""Output writers: CSV, HTML dashboard, Telegram, search-URL helper."""

from __future__ import annotations

import csv
import html
import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List

import requests

from .http import USER_AGENT
from .models import Job

log = logging.getLogger("qajobs.outputs")

CSV_FIELDS = [
    "score",
    "priority_tier",
    "priority_reasons",
    "is_senior",
    "title",
    "company",
    "source",
    "location",
    "regions",
    "posted_at",
    "salary",
    "tags",
    "url",
    "uid",
]


def _clean(text: str) -> str:
    """Strip HTML tags/entities down to readable plain text."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# Map priority tier -> CSS modifier used for badge/row colouring.
_TIER_CSS = {
    "Indonesia": "id",
    "GCC": "gcc",
    "SEA/Asia": "sea",
    "Europe": "eu",
}


def _row_class(job: Job) -> str:
    classes = []
    if job.priority_tier:
        classes.append("prio-row")
    if job.is_senior:
        classes.append("senior-row")
    return " ".join(classes)


def _priority_cell(job: Job) -> str:
    """Render the priority column: tier badge + score, or a dash."""
    if not job.priority_tier and job.score <= 0:
        return '<span class="score-none">&mdash;</span>'
    mod = _TIER_CSS.get(job.priority_tier, "other")
    tier_label = html.escape(job.priority_tier) if job.priority_tier else "match"
    badge = f'<span class="badge tier tier-{mod}">{tier_label}</span>'
    return f'{badge}<span class="score">{job.score}</span>'


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #
def write_csv(jobs: List[Job], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for job in jobs:
            writer.writerow(job.to_row())
    log.info("Wrote CSV: %s (%s rows)", path, len(jobs))


# --------------------------------------------------------------------------- #
# JSON
# --------------------------------------------------------------------------- #
def write_json(jobs: List[Job], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump([j.to_row() for j in jobs], fh, indent=2, ensure_ascii=False)
    log.info("Wrote JSON: %s", path)


# --------------------------------------------------------------------------- #
# Search-URL helper (LinkedIn / Indeed) -- generated, not scraped.
# --------------------------------------------------------------------------- #
def build_search_urls(queries: List[str]) -> List[Dict[str, str]]:
    links = []
    for q in queries:
        enc = urllib.parse.quote_plus(q)
        links.append(
            {
                "query": q,
                "linkedin": (
                    "https://www.linkedin.com/jobs/search/?keywords="
                    f"{enc}&f_WT=2&f_TPR=r604800&sortBy=DD"  # remote, last 7d, newest
                ),
                "indeed": f"https://www.indeed.com/jobs?q={enc}&sc=0kf%3Aattr(DSQF7)%3B&sort=date",
                "wellfound": f"https://wellfound.com/role/r/{enc.replace('+', '-').lower()}",
                "google": (
                    "https://www.google.com/search?q="
                    + urllib.parse.quote_plus(f"remote {q} jobs")
                    + "&ibp=htl;jobs"
                ),
            }
        )
    return links


# --------------------------------------------------------------------------- #
# Google dorking (generated clickable search links, NOT scraped)
# --------------------------------------------------------------------------- #
def _google_url(query: str, freshness: str = "") -> str:
    """Build a Google search URL for a raw dork query string.

    `freshness` maps to Google's tbs=qdr: filter (d/w/m/y) to limit recency.
    """
    params = {"q": query}
    fresh = (freshness or "").strip().lower()
    if fresh in {"d", "w", "m", "y"}:
        params["tbs"] = f"qdr:{fresh}"
    return "https://www.google.com/search?" + urllib.parse.urlencode(params)


def _region_or_group(terms: List[str]) -> str:
    """Turn ["Singapore", "Indonesia"] into '("Singapore" OR "Indonesia")'."""
    quoted = " OR ".join(f'"{t}"' for t in terms if t)
    return f"({quoted})" if quoted else ""


def build_google_dorks(cfg: dict) -> List[Dict[str, object]]:
    """Build grouped Google dork links from the google_dorks config block.

    Returns a list of groups: [{"name": str, "links": [{"label","url","query"}]}].
    Nothing is fetched; these are links the user opens in a browser.
    """
    dcfg = cfg.get("google_dorks", {}) or {}
    if not dcfg.get("enabled", False):
        return []

    def _dedup(items: List[str], min_len: int = 3) -> List[str]:
        seen = set()
        out = []
        for it in items:
            it = (it or "").strip()
            if len(it) < min_len or it.lower() in seen:
                continue
            seen.add(it.lower())
            out.append(it)
        return out

    # `roles` = readable role phrases used for PER-ROLE dorks (e.g. LinkedIn),
    # so each generated link stays clean and specific.
    clean_roles = _dedup(dcfg.get("roles", []) or [])

    # `match_roles` = everything (readable phrases + reused keywords), used in
    # the big OR-group site dorks to cast the widest net.
    match_roles_src: List[str] = []
    if dcfg.get("reuse_keywords", True):
        match_roles_src.extend(cfg.get("keywords", []) or [])
    match_roles_src.extend(dcfg.get("roles", []) or [])
    match_roles = _dedup(match_roles_src)
    # Fallback: if no readable roles were given, use the match list for per-role.
    if not clean_roles:
        clean_roles = match_roles

    # --- Regions ---
    regions_cfg = dcfg.get("regions", {}) or {}
    enabled_regions = dcfg.get("regions_enabled", []) or []
    region_groups = {
        name: _region_or_group(regions_cfg.get(name, []) or [])
        for name in enabled_regions
        if regions_cfg.get(name)
    }

    freshness = dcfg.get("freshness", "")
    groups: List[Dict[str, object]] = []

    def _role_or_group(roles_list: List[str]) -> str:
        return "(" + " OR ".join(f'"{r}"' for r in roles_list) + ")"

    role_or = _role_or_group(match_roles) if match_roles else ""

    # --- Indonesia focus (top priority): domains, local boards, companies ---
    id_cfg = dcfg.get("indonesia", {}) or {}
    if id_cfg.get("enabled", False) and role_or:
        id_links = []

        # Domain dorks, e.g. (site:.co.id OR site:.id) <roles>.
        domains = _dedup(id_cfg.get("domains", []) or [], min_len=1)
        if domains:
            dom_or = "(" + " OR ".join(f"site:.{d.lstrip('.')}" for d in domains) + ")"
            q = f"{dom_or} {role_or}".strip()
            id_links.append(
                {"label": "Indonesian domains (.co.id / .id)",
                 "url": _google_url(q, freshness), "query": q}
            )

        # Local job-board dorks, one wide site: OR-group.
        boards = _dedup(id_cfg.get("local_boards", []) or [], min_len=3)
        if boards:
            board_or = "(" + " OR ".join(f"site:{b}" for b in boards) + ")"
            q = f"{board_or} {role_or}".strip()
            id_links.append(
                {"label": "Indonesian job boards",
                 "url": _google_url(q, freshness), "query": q}
            )

        # Named Indonesian companies -- one dork per company (career pages).
        companies = _dedup(id_cfg.get("companies", []) or [], min_len=2)
        for company in companies:
            q = (
                f'"{company}" (careers OR jobs OR hiring) {role_or} '
                f'-site:linkedin.com -site:indeed.com -site:glassdoor.com'
            ).strip()
            id_links.append(
                {"label": f"{company} careers",
                 "url": _google_url(q, freshness), "query": q}
            )

        if id_links:
            groups.append(
                {"name": "\U0001f1ee\U0001f1e9 Indonesia (top priority)", "links": id_links}
            )

    # --- ATS / board site dorks (one group per region) ---
    ats_sites = dcfg.get("ats_sites", []) or []
    if ats_sites and role_or:
        site_or = "(" + " OR ".join(f"site:{s}" for s in ats_sites) + ")"
        for rname, rgroup in region_groups.items():
            q = f"{site_or} {role_or} {rgroup}".strip()
            groups.append(
                {
                    "name": f"ATS / job boards \u2014 {rname}",
                    "links": [{"label": "Open in Google", "url": _google_url(q, freshness), "query": q}],
                }
            )

    # --- LinkedIn jobs dorks (per role x region) ---
    li_cfg = dcfg.get("linkedin", {}) or {}
    if li_cfg.get("enabled", False) and clean_roles:
        extra = (li_cfg.get("extra_terms", "") or "").strip()
        li_links = []
        for role in clean_roles:
            for rname, rgroup in region_groups.items():
                parts = ['site:linkedin.com/jobs', f'"{role}"', rgroup]
                if extra:
                    parts.append(extra)
                q = " ".join(p for p in parts if p)
                li_links.append(
                    {"label": f"{role} \u2014 {rname}", "url": _google_url(q, freshness), "query": q}
                )
        if li_links:
            groups.append({"name": "LinkedIn jobs (via Google)", "links": li_links})

    # --- Generic career-page dorks (per region) ---
    gc_cfg = dcfg.get("generic_career", {}) or {}
    if gc_cfg.get("enabled", False) and role_or:
        gc_links = []
        for rname, rgroup in region_groups.items():
            # Catch self-hosted careers/jobs pages, excluding big aggregators.
            q = (
                f'(intitle:careers OR intitle:jobs OR inurl:careers OR inurl:jobs) '
                f'{role_or} {rgroup} '
                f'-site:linkedin.com -site:indeed.com -site:glassdoor.com'
            ).strip()
            gc_links.append(
                {"label": f"Career pages \u2014 {rname}", "url": _google_url(q, freshness), "query": q}
            )
        if gc_links:
            groups.append({"name": "Generic company career pages", "links": gc_links})

    # --- Fully custom templates ({role} x {region}) ---
    templates = dcfg.get("custom_templates", []) or []
    if templates and clean_roles:
        custom_links = []
        for tmpl in templates:
            for role in clean_roles:
                for rname, rgroup in region_groups.items():
                    q = tmpl.replace("{role}", role).replace("{region}", rgroup)
                    custom_links.append(
                        {"label": f"{role} \u2014 {rname}", "url": _google_url(q, freshness), "query": q}
                    )
        if custom_links:
            groups.append({"name": "Custom dorks", "links": custom_links})

    return groups


# --------------------------------------------------------------------------- #
# HTML dashboard
# --------------------------------------------------------------------------- #
def write_html(jobs: List[Job], path: str, search_links: List[Dict[str, str]],
               stats: Dict[str, int], dork_groups: List[Dict[str, object]] = None) -> None:
    dork_groups = dork_groups or []
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rows = []
    for job in jobs:
        senior_badge = '<span class="badge senior">SENIOR</span>' if job.is_senior else ""
        regions = "".join(f'<span class="badge region">{html.escape(r)}</span>' for r in job.regions)
        salary = html.escape(job.salary) if job.salary else "&mdash;"
        posted = job.posted_at_str() or "&mdash;"
        prio = _priority_cell(job)
        rows.append(
            f"""
      <tr class="{_row_class(job)}">
        <td data-sort="{job.score}">{prio}</td>
        <td>{senior_badge}<a href="{html.escape(job.url)}" target="_blank" rel="noopener">{html.escape(job.title)}</a></td>
        <td>{html.escape(job.company)}</td>
        <td>{html.escape(job.location)}{regions}</td>
        <td>{posted}</td>
        <td>{salary}</td>
        <td><span class="src">{html.escape(job.source)}</span></td>
      </tr>"""
        )

    link_cards = []
    for lk in search_links:
        link_cards.append(
            f"""
      <div class="linkcard">
        <div class="q">{html.escape(lk['query'])}</div>
        <a href="{html.escape(lk['linkedin'])}" target="_blank" rel="noopener">LinkedIn</a>
        <a href="{html.escape(lk['indeed'])}" target="_blank" rel="noopener">Indeed</a>
        <a href="{html.escape(lk['wellfound'])}" target="_blank" rel="noopener">Wellfound</a>
        <a href="{html.escape(lk['google'])}" target="_blank" rel="noopener">Google Jobs</a>
      </div>"""
        )

    # Google dork groups -> expandable cards with per-link buttons.
    dork_html_parts = []
    for group in dork_groups:
        link_items = []
        for lk in group.get("links", []):
            link_items.append(
                f"""
        <div class="dorkrow">
          <a class="dorkbtn" href="{html.escape(str(lk['url']))}" target="_blank" rel="noopener">{html.escape(str(lk['label']))}</a>
          <code class="dorkq" title="{html.escape(str(lk['query']))}">{html.escape(str(lk['query']))}</code>
        </div>"""
            )
        dork_html_parts.append(
            f"""
      <details class="dorkgroup" open>
        <summary>{html.escape(str(group.get('name', 'Dorks')))} <span class="count">({len(group.get('links', []))})</span></summary>
        {''.join(link_items)}
      </details>"""
        )
    dork_section = ""
    if dork_html_parts:
        dork_section = f"""
  <h2>Google dorks &mdash; company career pages &amp; LinkedIn (SEA / GCC)</h2>
  <p class="hint">Click a link to run the search on Google in your browser. These are generated queries, not scraped results.</p>
  <div class="dorks">{''.join(dork_html_parts)}</div>"""

    stat_line = " &middot; ".join(f"{k}: <strong>{v}</strong>" for k, v in stats.items())

    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Remote QA Jobs</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         margin: 0; background: #0f1115; color: #e6e6e6; }}
  header {{ padding: 24px 28px; background: linear-gradient(135deg, #1f6feb, #7b2ff7); }}
  header h1 {{ margin: 0 0 6px; font-size: 22px; }}
  header .meta {{ font-size: 13px; opacity: .9; }}
  .wrap {{ padding: 20px 28px 60px; max-width: 1200px; margin: 0 auto; }}
  .controls {{ margin: 18px 0; }}
  input[type=search] {{ width: 100%; padding: 12px 14px; border-radius: 10px;
        border: 1px solid #30363d; background: #161b22; color: #e6e6e6; font-size: 15px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 14px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #21262d; vertical-align: top; }}
  th {{ position: sticky; top: 0; background: #161b22; cursor: pointer; user-select: none; }}
  tr:hover td {{ background: #12161c; }}
  tr.senior-row td {{ background: #14261c; }}
  a {{ color: #58a6ff; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .badge {{ display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 6px;
        border-radius: 6px; margin-left: 6px; letter-spacing: .5px; }}
  .badge.senior {{ background: #238636; color: #fff; }}
  .badge.region {{ background: #21262d; color: #9db4d0; font-weight: 600; }}
  .badge.tier {{ margin-left: 0; color: #fff; }}
  .badge.tier-id {{ background: #d1242f; }}     /* Indonesia: top priority (red) */
  .badge.tier-gcc {{ background: #bf8700; }}    /* GCC (amber) */
  .badge.tier-sea {{ background: #1f6feb; }}    /* SEA/Asia (blue) */
  .badge.tier-eu {{ background: #8957e5; }}     /* Europe (purple) */
  .badge.tier-other {{ background: #6e7681; }}  /* generic match */
  .score {{ display: inline-block; margin-left: 6px; font-size: 12px; font-weight: 700;
        color: #9db4d0; }}
  .score-none {{ opacity: .4; }}
  tr.prio-row td {{ border-left: 2px solid transparent; }}
  .src {{ font-size: 12px; opacity: .8; }}
  h2 {{ margin: 34px 0 10px; font-size: 16px; }}
  .links {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(230px,1fr)); gap: 12px; }}
  .linkcard {{ background: #161b22; border: 1px solid #21262d; border-radius: 10px; padding: 12px; }}
  .linkcard .q {{ font-weight: 600; margin-bottom: 8px; }}
  .linkcard a {{ display: inline-block; margin-right: 10px; font-size: 13px; }}
  .empty {{ opacity: .7; padding: 20px 0; }}
  .hint {{ font-size: 13px; opacity: .7; margin: 0 0 12px; }}
  .dorks {{ display: flex; flex-direction: column; gap: 10px; }}
  .dorkgroup {{ background: #161b22; border: 1px solid #21262d; border-radius: 10px; padding: 8px 12px; }}
  .dorkgroup summary {{ cursor: pointer; font-weight: 600; padding: 4px 0; }}
  .dorkgroup .count {{ opacity: .6; font-weight: 400; }}
  .dorkrow {{ display: flex; align-items: center; gap: 10px; padding: 6px 0;
        border-top: 1px solid #21262d; flex-wrap: wrap; }}
  .dorkbtn {{ flex: 0 0 auto; background: #1f6feb; color: #fff !important; padding: 5px 10px;
        border-radius: 7px; font-size: 12px; font-weight: 600; white-space: nowrap; }}
  .dorkbtn:hover {{ background: #388bfd; text-decoration: none; }}
  .dorkq {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
        color: #9db4d0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        flex: 1 1 260px; min-width: 0; }}
  footer {{ opacity: .6; font-size: 12px; margin-top: 40px; }}
</style>
</head>
<body>
<header>
  <h1>Remote QA / Senior QA Engineer &mdash; job scan</h1>
  <div class="meta">Generated {generated} &middot; {stat_line}</div>
</header>
<div class="wrap">
  <div class="controls">
    <input id="filter" type="search" placeholder="Filter by title, company, location, source...">
  </div>
  <table id="jobs">
    <thead>
      <tr>
        <th data-c="0" data-num="1">Priority</th>
        <th data-c="1">Title</th>
        <th data-c="2">Company</th>
        <th data-c="3">Location</th>
        <th data-c="4">Posted</th>
        <th data-c="5">Salary</th>
        <th data-c="6">Source</th>
      </tr>
    </thead>
    <tbody>{''.join(rows) if rows else ''}</tbody>
  </table>
  {'' if rows else '<div class="empty">No jobs matched your filters this run.</div>'}

  <h2>Search these on LinkedIn / Indeed (opens live searches)</h2>
  <div class="links">{''.join(link_cards)}</div>
{dork_section}
  <footer>Built by your local remote-qa-jobs scanner. LinkedIn/Indeed &amp; Google dorks are linked, not scraped.</footer>
</div>
<script>
  const input = document.getElementById('filter');
  const rows = Array.from(document.querySelectorAll('#jobs tbody tr'));
  input.addEventListener('input', () => {{
    const q = input.value.toLowerCase();
    rows.forEach(r => {{ r.style.display = r.innerText.toLowerCase().includes(q) ? '' : 'none'; }});
  }});
  document.querySelectorAll('#jobs th').forEach(th => {{
    th.addEventListener('click', () => {{
      const c = +th.dataset.c;
      const numeric = th.dataset.num === '1';
      const tbody = document.querySelector('#jobs tbody');
      const sorted = rows.sort((a,b) => {{
        if (numeric) {{
          const av = +(a.children[c].dataset.sort || 0);
          const bv = +(b.children[c].dataset.sort || 0);
          return bv - av;  // highest score first
        }}
        return a.children[c].innerText.localeCompare(b.children[c].innerText);
      }});
      sorted.forEach(r => tbody.appendChild(r));
    }});
  }});
</script>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    log.info("Wrote HTML: %s", path)


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
def send_telegram(jobs: List[Job], cfg: dict) -> None:
    tg = cfg.get("telegram", {}) or {}
    if not tg.get("enabled"):
        return

    token = os.environ.get(tg.get("bot_token_env", "TELEGRAM_BOT_TOKEN"), "")
    chat_id = os.environ.get(tg.get("chat_id_env", "TELEGRAM_CHAT_ID"), "")
    if not token or not chat_id:
        log.info("Telegram enabled but token/chat_id missing; skipping notifications.")
        return

    max_n = int(tg.get("max_notifications", 15))
    to_send = jobs[:max_n]
    if not to_send:
        log.info("Telegram: no jobs to notify.")
        return

    api = f"https://api.telegram.org/bot{token}/sendMessage"
    for job in to_send:
        senior = "\U0001f7e2 SENIOR " if job.is_senior else ""
        regions = f" [{', '.join(job.regions)}]" if job.regions else ""
        salary = f"\n\U0001f4b0 {job.salary}" if job.salary else ""
        text = (
            f"{senior}<b>{html.escape(job.title)}</b>\n"
            f"\U0001f3e2 {html.escape(job.company)}\n"
            f"\U0001f4cd {html.escape(job.location)}{html.escape(regions)}\n"
            f"\U0001f5d3 {job.posted_at_str() or 'n/a'} \u00b7 {html.escape(job.source)}"
            f"{salary}\n"
            f"\U0001f517 {html.escape(job.url)}"
        )
        try:
            requests.post(
                api,
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                headers={"User-Agent": USER_AGENT},
                timeout=20,
            )
        except requests.RequestException as exc:
            log.warning("Telegram send failed: %s", exc)

    log.info("Telegram: sent %s notifications.", len(to_send))
