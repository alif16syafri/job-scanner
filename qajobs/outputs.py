"""Output writers: CSV, HTML dashboard, Telegram, search-URL helper."""

from __future__ import annotations

import csv
import html
import json
import logging
import os
import re
import urllib.parse
from datetime import datetime, timedelta, timezone
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
    "ANZ": "anz",
    "Europe": "eu",
}


def _js_str(value: str) -> str:
    """Serialize a string as a safe JS string literal (for inlining in <script>)."""
    import json as _json
    # json.dumps gives a valid JS string; also neutralize </script> breakouts.
    return _json.dumps(value or "").replace("</", "<\\/")


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


def _status_cell(job: Job, apps_on: bool) -> str:
    """Render the Status column: a badge (filled by JS) + action buttons.

    The buttons call window.setJobStatus(uid, status) defined in the page JS,
    which upserts to Supabase and updates the row. Data attributes drive both
    the badge and the filter toggles.
    """
    uid = html.escape(job.uid)
    j = json_dumps_attr(job)
    return (
        f'\n        <td data-label="Status" class="statuscell">'
        f'<span class="statusbadge" data-uid="{uid}"></span>'
        f'<span class="statusbtns">'
        f'<button type="button" class="stbtn st-applied" title="Applied" '
        f'onclick=\'setJobStatus("{uid}","applied",{j})\'>&#10003;</button>'
        f'<button type="button" class="stbtn st-interested" title="Interested" '
        f'onclick=\'setJobStatus("{uid}","interested",{j})\'>&#9733;</button>'
        f'<button type="button" class="stbtn st-hidden" title="Hide" '
        f'onclick=\'setJobStatus("{uid}","hidden",{j})\'>&#128683;</button>'
        f'<button type="button" class="stbtn st-clear" title="Clear" '
        f'onclick=\'setJobStatus("{uid}","",{j})\'>&#8635;</button>'
        f'</span></td>'
    )


def json_dumps_attr(job: Job) -> str:
    """Compact JSON for a job (title/company/url) safe to embed in an onclick.

    The attribute is wrapped in SINGLE quotes in the HTML, so double quotes in
    the JSON are fine; we only need to neutralize single quotes and angle
    brackets so the attribute/tag can't be broken out of.
    """
    import json as _json
    payload = {"title": job.title, "company": job.company, "url": job.url}
    s = _json.dumps(payload, ensure_ascii=True)
    return s.replace("&", "&amp;").replace("'", "&#39;").replace("<", "&lt;").replace(">", "&gt;")


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

    # --- Indonesia focus (top priority): domains + local boards ---
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

    # --- Extra boards with no usable API/feed (Wellfound, FlexJobs, etc.) ---
    # We can't fetch these safely, so we generate a Google site: dork per board
    # per region -- one-click search without scraping.
    eb_cfg = dcfg.get("extra_boards", {}) or {}
    if eb_cfg.get("enabled", False) and role_or:
        eb_links = []
        for site in _dedup(eb_cfg.get("sites", []) or [], min_len=3):
            for rname, rgroup in region_groups.items():
                q = f"site:{site} {role_or} {rgroup}".strip()
                eb_links.append(
                    {"label": f"{site} \u2014 {rname}",
                     "url": _google_url(q, freshness), "query": q}
                )
        if eb_links:
            groups.append({"name": "Other boards (Wellfound / FlexJobs / etc.)", "links": eb_links})

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


# Map our google_dorks.freshness (d/w/m/y) to LinkedIn's f_TPR seconds window.
_LI_TPR = {"d": "r86400", "w": "r604800", "m": "r2592000", "y": "r31536000"}


def build_linkedin_locations(cfg: dict) -> List[Dict[str, str]]:
    """Build native LinkedIn job-search deeplinks (by geoId) per location.

    These open LinkedIn's OWN filtered results directly -- not a Google dork.
    Returns [{"name","url","keywords"}].
    """
    dcfg = cfg.get("google_dorks", {}) or {}
    li_cfg = dcfg.get("linkedin_locations", {}) or {}
    if not li_cfg.get("enabled", False):
        return []

    locations = li_cfg.get("locations", []) or []
    if not locations:
        return []

    # Keyword query for every deeplink. Prefer an explicit `keywords` string;
    # otherwise fall back to an OR-group of readable roles / keyword list.
    keywords = (li_cfg.get("keywords") or "").strip()
    if not keywords:
        roles = [r.strip() for r in (dcfg.get("roles", []) or []) if r and r.strip()]
        if not roles:
            roles = [r.strip() for r in (cfg.get("keywords", []) or []) if r and r.strip()]
        kw_parts = [f'"{r}"' if " " in r else r for r in roles[:8]]
        keywords = " OR ".join(kw_parts) if kw_parts else "QA Engineer"

    # Time filter: prefer the deeplink-specific `time_posted`, else the global
    # google_dorks.freshness. Both use d/w/m/y and map to LinkedIn's f_TPR.
    tpr_key = (li_cfg.get("time_posted") or dcfg.get("freshness", "") or "").strip().lower()
    tpr = _LI_TPR.get(tpr_key, "")
    remote_only = li_cfg.get("remote_only", True)
    sort_recent = li_cfg.get("sort_recent", True)

    links: List[Dict[str, str]] = []
    for loc in locations:
        name = (loc.get("name") or "").strip()
        geo_id = str(loc.get("geoId") or "").strip()
        if not name or not geo_id:
            continue
        params = {"keywords": keywords, "geoId": geo_id, "location": name}
        if tpr:
            params["f_TPR"] = tpr
        if remote_only:
            params["f_WT"] = "2"
        if sort_recent:
            params["sortBy"] = "DD"
        url = "https://www.linkedin.com/jobs/search/?" + urllib.parse.urlencode(params)
        links.append({"name": name, "url": url, "keywords": keywords})

    return links


# --------------------------------------------------------------------------- #
# HTML dashboard
# --------------------------------------------------------------------------- #
def write_html(jobs: List[Job], path: str, search_links: List[Dict[str, str]],
               stats: Dict[str, int], dork_groups: List[Dict[str, object]] = None,
               linkedin_locations: List[Dict[str, str]] = None,
               new_uids: set = None, first_seen: Dict[str, str] = None,
               app_cfg: Dict[str, object] = None) -> None:
    dork_groups = dork_groups or []
    linkedin_locations = linkedin_locations or []
    new_uids = new_uids or set()
    first_seen = first_seen or {}
    app_cfg = app_cfg or {}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # Jakarta is a fixed UTC+7 (WIB, no daylight saving).
    jakarta = timezone(timedelta(hours=7))
    generated = datetime.now(jakarta).strftime("%Y-%m-%d %H:%M WIB")

    apps_on = bool(app_cfg.get("enabled"))
    supa_url = str(app_cfg.get("supabase_url") or "")
    supa_key = str(app_cfg.get("supabase_anon_key") or "")
    supa_table = str(app_cfg.get("table") or "job_status")
    supa_ready = bool(apps_on and supa_url and supa_key)

    rows = []
    for job in jobs:
        senior_badge = '<span class="badge senior">SENIOR</span>' if job.is_senior else ""
        is_new = job.uid in new_uids
        new_badge = '<span class="badge new">NEW</span>' if is_new else ""
        regions = "".join(f'<span class="badge region">{html.escape(r)}</span>' for r in job.regions)
        salary = html.escape(job.salary) if job.salary else "&mdash;"
        posted = job.posted_at_str() or "&mdash;"
        seen_iso = first_seen.get(job.uid, "")
        seen_disp = seen_iso[:10] if seen_iso else ("today" if is_new else "&mdash;")
        prio = _priority_cell(job)
        status_cell = _status_cell(job, apps_on) if apps_on else ""
        rows.append(
            f"""
      <tr class="{_row_class(job)}" data-uid="{job.uid}" data-new="{'1' if is_new else '0'}" data-status="">
        <td data-label="Priority" data-sort="{job.score}">{prio}</td>
        <td data-label="Title">{new_badge}{senior_badge}<a href="{html.escape(job.url)}" target="_blank" rel="noopener">{html.escape(job.title)}</a></td>
        <td data-label="Company">{html.escape(job.company)}</td>
        <td data-label="Location">{html.escape(job.location)}{regions}</td>
        <td data-label="Posted">{posted}</td>
        <td data-label="First seen" class="seen">{seen_disp}</td>
        <td data-label="Salary">{salary}</td>
        <td data-label="Source"><span class="src">{html.escape(job.source)}</span></td>{status_cell}
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

    # Native LinkedIn deeplinks by location (open LinkedIn's own filtered results).
    li_loc_section = ""
    if linkedin_locations:
        li_buttons = "".join(
            f'<a class="loc-btn" href="{html.escape(lk["url"])}" target="_blank" rel="noopener">{html.escape(lk["name"])}</a>'
            for lk in linkedin_locations
        )
        li_kw = html.escape(linkedin_locations[0].get("keywords", ""))
        li_loc_section = f"""
  <h2>LinkedIn jobs by location (native deeplinks)</h2>
  <p class="hint">Opens LinkedIn's own filtered results (remote, most recent) for: <code>{li_kw}</code></p>
  <div class="locgrid">{li_buttons}</div>"""

    stat_line = " &middot; ".join(f"{k}: <strong>{v}</strong>" for k, v in stats.items())

    # Status column header (only when application tracking is enabled).
    status_th = '\n        <th data-c="8">Status</th>' if apps_on else ""

    # Filter toggles under the search box.
    toggle_items = ['<label class="tog"><input type="checkbox" id="fNew"> New only</label>']
    if apps_on:
        toggle_items += [
            '<label class="tog"><input type="checkbox" id="fHideApplied"> Hide applied</label>',
            '<label class="tog"><input type="checkbox" id="fHideHidden" checked> Hide hidden</label>',
            '<label class="tog"><input type="checkbox" id="fInterested"> Interested only</label>',
        ]
    controls_extra = f'<div class="toggles">{"".join(toggle_items)}</div>'

    # Supabase sync banner + config injected into JS. Keys are public by design.
    if apps_on and not supa_ready:
        apps_banner = ('<div class="banner warn">Application tracking is on, but Supabase '
                       'isn\'t configured yet &mdash; set <code>supabase_url</code> / '
                       '<code>supabase_anon_key</code> (or the SUPABASE_URL / SUPABASE_ANON_KEY '
                       'env vars). Buttons are disabled until then.</div>')
    elif supa_ready:
        apps_banner = ('<div class="banner ok" id="syncBanner">Applied/Interested status syncs '
                       'across everyone with this link.</div>')
    else:
        apps_banner = ""

    # "Add a job I applied to" form (only when tracking is on).
    add_form = ""
    if apps_on:
        add_form = (
            '\n  <details class="addbox"' + (' open' if not rows else '') + '>'
            '\n    <summary>+ Add a job you applied to (paste a link)</summary>'
            '\n    <div class="addrow">'
            '\n      <input id="addUrl" type="url" placeholder="https://company.com/jobs/qa-engineer  (paste the link)">'
            '\n      <input id="addTitle" type="text" placeholder="Title (auto-filled, editable)">'
            '\n      <input id="addCompany" type="text" placeholder="Company (auto-filled, editable)">'
            '\n      <button id="addBtn" type="button">Add as applied</button>'
            '\n    </div>'
            '\n    <div id="addMsg" class="addmsg"></div>'
            '\n  </details>'
        )

    supa_cdn = ('<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>'
                if supa_ready else "")
    supa_js_cfg = (
        f'const SUPA_URL={_js_str(supa_url)};'
        f'const SUPA_KEY={_js_str(supa_key)};'
        f'const SUPA_TABLE={_js_str(supa_table)};'
        f'const APPS_ON={"true" if apps_on else "false"};'
        f'const SUPA_READY={"true" if supa_ready else "false"};'
    )

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
  .toggles {{ display: flex; flex-wrap: wrap; gap: 14px; margin-top: 12px; }}
  .tog {{ font-size: 13px; opacity: .9; cursor: pointer; user-select: none; display: flex;
        align-items: center; gap: 6px; }}
  .banner {{ margin: 12px 0 0; padding: 8px 12px; border-radius: 8px; font-size: 13px; }}
  .banner.ok {{ background: #10261a; border: 1px solid #1f6f43; color: #9be0b4; }}
  .banner.warn {{ background: #2b2410; border: 1px solid #6f5a1f; color: #e6cf8a; }}
  /* Add-a-job form */
  .addbox {{ margin: 12px 0 0; background: #161b22; border: 1px solid #21262d;
        border-radius: 10px; padding: 8px 12px; }}
  .addbox summary {{ cursor: pointer; font-weight: 600; padding: 4px 0; }}
  .addrow {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }}
  .addrow input {{ flex: 1 1 200px; padding: 9px 12px; border-radius: 8px; min-width: 0;
        border: 1px solid #30363d; background: #0f1115; color: #e6e6e6; font-size: 14px; }}
  .addrow #addUrl {{ flex: 2 1 320px; }}
  .addrow button {{ flex: 0 0 auto; background: #238636; color: #fff; border: 0; cursor: pointer;
        padding: 9px 16px; border-radius: 8px; font-size: 14px; font-weight: 600; }}
  .addrow button:hover {{ background: #2ea043; }}
  .addrow button:disabled {{ opacity: .6; cursor: default; }}
  .addmsg {{ font-size: 13px; opacity: .85; margin-top: 8px; min-height: 1em; }}
  .badge.manualtag {{ background: #6e40c9; color: #fff; margin-left: 0; margin-right: 6px; }}
  tr.manual-row td[data-label="Priority"] {{ opacity: .7; }}
  /* Status column */
  .statuscell {{ white-space: nowrap; }}
  .statusbtns {{ display: inline-flex; gap: 3px; }}
  .stbtn {{ border: 1px solid #30363d; background: #161b22; color: #9db4d0; cursor: pointer;
        border-radius: 6px; font-size: 13px; line-height: 1; padding: 4px 7px; }}
  .stbtn:hover {{ border-color: #58a6ff; color: #e6e6e6; }}
  .stbtn.st-applied:hover {{ border-color: #238636; }}
  .stbtn.st-interested:hover {{ border-color: #e3b341; }}
  .stbtn.st-hidden:hover {{ border-color: #d1242f; }}
  .statusbadge {{ display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 6px;
        border-radius: 6px; margin-right: 6px; letter-spacing: .4px; }}
  .statusbadge:empty {{ display: none; }}
  .statusbadge.s-applied {{ background: #238636; color: #fff; }}
  .statusbadge.s-interested {{ background: #e3b341; color: #1a1000; }}
  .statusbadge.s-hidden {{ background: #6e7681; color: #fff; }}
  tr[data-status="hidden"] {{ opacity: .5; }}
  tr[data-status="applied"] td[data-label="Title"] a {{ text-decoration: line-through; opacity: .85; }}
  .table-wrap {{ width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }}
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
  .badge.new {{ background: #e3b341; color: #1a1000; margin-left: 0; margin-right: 6px; }}
  .badge.region {{ background: #21262d; color: #9db4d0; font-weight: 600; }}
  .badge.tier {{ margin-left: 0; color: #fff; }}
  .badge.tier-id {{ background: #d1242f; }}     /* Indonesia: top priority (red) */
  .badge.tier-gcc {{ background: #bf8700; }}    /* GCC (amber) */
  .badge.tier-sea {{ background: #1f6feb; }}    /* SEA/Asia (blue) */
  .badge.tier-anz {{ background: #1a7f6b; }}    /* Australia/NZ (teal) */
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
  .locgrid {{ display: flex; flex-wrap: wrap; gap: 10px; }}
  .loc-btn {{ display: inline-block; background: #0a66c2; color: #fff !important;
        padding: 9px 16px; border-radius: 999px; font-size: 14px; font-weight: 600; }}
  .loc-btn:hover {{ background: #1275d6; text-decoration: none; }}
  code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
        background: #161b22; padding: 2px 6px; border-radius: 5px; }}
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

  /* --- Mobile: stack table rows into cards so nothing gets zoomed out --- */
  @media (max-width: 640px) {{
    header {{ padding: 18px 16px; }}
    header h1 {{ font-size: 18px; }}
    .wrap {{ padding: 14px 14px 48px; }}
    .table-wrap {{ overflow-x: visible; }}
    table, thead, tbody, tr, th, td {{ display: block; width: 100%; }}
    thead {{ display: none; }}  /* labels move into each cell via data-label */
    table {{ font-size: 14px; }}
    tr {{ background: #161b22; border: 1px solid #21262d; border-radius: 10px;
          margin: 0 0 12px; padding: 6px 12px; }}
    tr:hover td, tr.senior-row td, tr.prio-row td {{ background: transparent; }}
    tr.senior-row {{ border-left: 3px solid #238636; }}
    td {{ border-bottom: 1px solid #21262d; padding: 8px 0;
          display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }}
    td:last-child {{ border-bottom: 0; }}
    td::before {{ content: attr(data-label); font-weight: 600; color: #9db4d0;
          flex: 0 0 84px; font-size: 12px; text-transform: uppercase; letter-spacing: .3px; }}
    td[data-label="Title"] {{ font-size: 15px; }}
    td[data-label="Title"] a {{ text-align: right; }}
    td[data-label="Status"] {{ flex-wrap: wrap; }}
    .statusbtns {{ flex-wrap: wrap; justify-content: flex-end; }}
    .stbtn {{ padding: 6px 10px; font-size: 15px; }}
    .toggles {{ gap: 10px 16px; }}
    .links {{ grid-template-columns: 1fr; }}
    .dorkq {{ display: none; }}  /* hide long query text on phones, keep the button */
    .dorkrow {{ gap: 6px; }}
  }}
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
    {controls_extra}
  </div>
  {apps_banner}
  {add_form}
  <div class="table-wrap">
  <table id="jobs">
    <thead>
      <tr>
        <th data-c="0" data-num="1">Priority</th>
        <th data-c="1">Title</th>
        <th data-c="2">Company</th>
        <th data-c="3">Location</th>
        <th data-c="4">Posted</th>
        <th data-c="5">First seen</th>
        <th data-c="6">Salary</th>
        <th data-c="7">Source</th>{status_th}
      </tr>
    </thead>
    <tbody>{''.join(rows) if rows else ''}</tbody>
  </table>
  </div>
  {'' if rows else '<div class="empty">No jobs matched your filters this run.</div>'}

  <h2>Search these on LinkedIn / Indeed (opens live searches)</h2>
  <div class="links">{''.join(link_cards)}</div>
{li_loc_section}
{dork_section}
  <footer>Built by your local remote-qa-jobs scanner. LinkedIn/Indeed &amp; Google dorks are linked, not scraped.</footer>
</div>
{supa_cdn}
<script>
  {supa_js_cfg}
  const input = document.getElementById('filter');
  // `rows` is re-read after we inject manually-added jobs so filters see them.
  let rows = Array.from(document.querySelectorAll('#jobs tbody tr'));
  function refreshRows() {{ rows = Array.from(document.querySelectorAll('#jobs tbody tr')); }}

  // ---- Supabase client (public anon key; RLS allows anon read/write) ----
  let sb = null;
  if (SUPA_READY && window.supabase) {{
    try {{ sb = window.supabase.createClient(SUPA_URL, SUPA_KEY); }}
    catch (e) {{ console.warn('Supabase init failed', e); }}
  }}

  const STATUS_LABEL = {{ applied: 'APPLIED', interested: 'INTERESTED', hidden: 'HIDDEN' }};

  function rowByUid(uid) {{ return document.querySelector('#jobs tbody tr[data-uid="' + uid + '"]'); }}

  // JS twin of Job.uid in models.py: sha1(company|title|url).lower()[:16].
  async function uidFor(company, title, url) {{
    const raw = (company||'').trim().toLowerCase() + '|' + (title||'').trim().toLowerCase() + '|' + (url||'').trim();
    const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(raw));
    const hex = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2,'0')).join('');
    return hex.slice(0, 16);
  }}

  // Best-effort title/company guess from a pasted URL (client-side only; we
  // can't fetch the page cross-origin, so we parse the URL itself).
  function deriveFromUrl(url) {{
    let host = '', title = '', company = '';
    try {{
      const u = new URL(url);
      host = u.hostname.replace(/^www\\./, '');
      company = host.split('.')[0];
      // Grab the longest path segment and turn slug-words into a title guess.
      const segs = u.pathname.split('/').filter(Boolean);
      const slug = segs.sort((a,b) => b.length - a.length)[0] || '';
      const words = decodeURIComponent(slug).replace(/[-_]+/g, ' ').replace(/\\d{{4,}}/g, '').trim();
      if (words && words.length > 2 && !/^\\d+$/.test(words)) {{
        title = words.replace(/\\b\\w/g, c => c.toUpperCase());
      }}
    }} catch (e) {{ /* invalid URL handled by caller */ }}
    return {{ host: host, title: title, company: company ? company.charAt(0).toUpperCase() + company.slice(1) : '' }};
  }}

  function paintStatus(uid, status) {{
    const r = rowByUid(uid);
    if (!r) return;
    r.dataset.status = status || '';
    const badge = r.querySelector('.statusbadge');
    if (badge) {{
      badge.textContent = status ? (STATUS_LABEL[status] || status) : '';
      badge.className = 'statusbadge' + (status ? ' s-' + status : '');
    }}
    applyFilters();
  }}

  // Build a table row for a manually-added job (source='manual') and insert it.
  function injectManualRow(rec) {{
    if (rowByUid(rec.uid)) return; // already present (also matched a scan row)
    const tbody = document.querySelector('#jobs tbody');
    const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    const jobJson = JSON.stringify({{title: rec.title||'', company: rec.company||'', url: rec.url||''}})
                    .replace(/&/g,'&amp;').replace(/'/g,'&#39;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    const tr = document.createElement('tr');
    tr.className = 'prio-row manual-row';
    tr.dataset.uid = rec.uid;
    tr.dataset.new = '0';
    tr.dataset.status = rec.status || '';
    const seen = (rec.added_at || rec.updated_at || '').slice(0,10) || '&mdash;';
    tr.innerHTML =
      '<td data-label="Priority" data-sort="0"><span class="badge tier tier-other">manual</span></td>' +
      '<td data-label="Title"><span class="badge manualtag">ADDED</span>' +
        '<a href="' + esc(rec.url) + '" target="_blank" rel="noopener">' + (esc(rec.title) || esc(rec.url)) + '</a></td>' +
      '<td data-label="Company">' + esc(rec.company) + '</td>' +
      '<td data-label="Location">' + esc(rec.location||'') + '</td>' +
      '<td data-label="Posted">&mdash;</td>' +
      '<td data-label="First seen" class="seen">' + seen + '</td>' +
      '<td data-label="Salary">&mdash;</td>' +
      '<td data-label="Source"><span class="src">manual</span></td>' +
      '<td data-label="Status" class="statuscell"><span class="statusbadge" data-uid="' + rec.uid + '"></span>' +
        '<span class="statusbtns">' +
        '<button type="button" class="stbtn st-applied" title="Applied" onclick=\\'setJobStatus("' + rec.uid + '","applied",' + jobJson + ')\\'>&#10003;</button>' +
        '<button type="button" class="stbtn st-interested" title="Interested" onclick=\\'setJobStatus("' + rec.uid + '","interested",' + jobJson + ')\\'>&#9733;</button>' +
        '<button type="button" class="stbtn st-hidden" title="Hide" onclick=\\'setJobStatus("' + rec.uid + '","hidden",' + jobJson + ')\\'>&#128683;</button>' +
        '<button type="button" class="stbtn st-clear" title="Remove" onclick=\\'setJobStatus("' + rec.uid + '","",' + jobJson + ')\\'>&#8635;</button>' +
        '</span></td>';
    tbody.insertBefore(tr, tbody.firstChild);
    refreshRows();
    paintStatus(rec.uid, rec.status || '');
  }}

  async function loadStatuses() {{
    if (!sb) return;
    const {{ data, error }} = await sb.from(SUPA_TABLE).select('*');
    if (error) {{ console.warn('load statuses', error); return; }}
    (data || []).forEach(row => {{
      if (row.source === 'manual' && !rowByUid(row.uid)) {{
        injectManualRow(row);   // not in this scan -> show as its own row
      }} else {{
        paintStatus(row.uid, row.status);
      }}
    }});
    applyFilters();
  }}

  // Called from the per-row buttons. `status` = '' clears (deletes) the row.
  window.setJobStatus = async function(uid, status, job) {{
    if (!APPS_ON) return;
    if (!sb) {{ alert('Sync is not configured yet.'); return; }}
    try {{
      if (!status) {{
        const {{ error }} = await sb.from(SUPA_TABLE).delete().eq('uid', uid);
        if (error) throw error;
        const r = rowByUid(uid);
        if (r && r.classList.contains('manual-row')) {{ r.remove(); refreshRows(); applyFilters(); }}
        else paintStatus(uid, '');
      }} else {{
        const rec = {{ uid: uid, status: status, updated_at: new Date().toISOString() }};
        if (job) {{ rec.title = job.title; rec.company = job.company; rec.url = job.url; }}
        const {{ error }} = await sb.from(SUPA_TABLE).upsert(rec, {{ onConflict: 'uid' }});
        if (error) throw error;
        paintStatus(uid, status);
      }}
    }} catch (e) {{ console.warn('setJobStatus failed', e); alert('Could not save status (see console).'); }}
  }};

  // ---- Add a job I applied to elsewhere (manual entry) ----
  const addUrl = document.getElementById('addUrl');
  const addTitle = document.getElementById('addTitle');
  const addCompany = document.getElementById('addCompany');
  const addBtn = document.getElementById('addBtn');
  const addMsg = document.getElementById('addMsg');

  if (addUrl) {{
    // Live-fill title/company guesses as you paste/type a URL (only if empty).
    addUrl.addEventListener('input', () => {{
      const d = deriveFromUrl(addUrl.value.trim());
      if (addTitle && !addTitle.dataset.touched) addTitle.value = d.title;
      if (addCompany && !addCompany.dataset.touched) addCompany.value = d.company;
    }});
    if (addTitle) addTitle.addEventListener('input', () => addTitle.dataset.touched = '1');
    if (addCompany) addCompany.addEventListener('input', () => addCompany.dataset.touched = '1');
  }}

  if (addBtn) {{
    addBtn.addEventListener('click', async () => {{
      const url = (addUrl.value || '').trim();
      if (!url) {{ addMsg.textContent = 'Paste a job URL first.'; return; }}
      let valid = true; try {{ new URL(url); }} catch (e) {{ valid = false; }}
      if (!valid) {{ addMsg.textContent = 'That doesn\\'t look like a valid URL.'; return; }}
      if (!sb) {{ addMsg.textContent = 'Sync is not configured yet.'; return; }}
      const d = deriveFromUrl(url);
      const title = (addTitle.value || '').trim() || d.title || url;
      const company = (addCompany.value || '').trim() || d.company || d.host;
      addBtn.disabled = true; addMsg.textContent = 'Saving...';
      try {{
        const uid = await uidFor(company, title, url);
        const rec = {{ uid: uid, status: 'applied', source: 'manual', title: title,
                      company: company, url: url, added_at: new Date().toISOString(),
                      updated_at: new Date().toISOString() }};
        const {{ error }} = await sb.from(SUPA_TABLE).upsert(rec, {{ onConflict: 'uid' }});
        if (error) throw error;
        // Show it now: either mark an existing scan row applied, or inject a row.
        if (rowByUid(uid)) paintStatus(uid, 'applied');
        else injectManualRow(rec);
        addUrl.value = ''; addTitle.value = ''; addCompany.value = '';
        delete addTitle.dataset.touched; delete addCompany.dataset.touched;
        addMsg.textContent = 'Added: ' + title + (company ? ' @ ' + company : '');
      }} catch (e) {{
        console.warn('add applied job failed', e);
        addMsg.textContent = 'Could not save (see console).';
      }} finally {{ addBtn.disabled = false; }}
    }});
  }}

  // ---- Filtering (search text + toggles) ----
  function applyFilters() {{
    const q = (input.value || '').toLowerCase();
    const newOnly = document.getElementById('fNew') && document.getElementById('fNew').checked;
    const hideApplied = document.getElementById('fHideApplied') && document.getElementById('fHideApplied').checked;
    const hideHidden = document.getElementById('fHideHidden') && document.getElementById('fHideHidden').checked;
    const interestedOnly = document.getElementById('fInterested') && document.getElementById('fInterested').checked;
    rows.forEach(r => {{
      const st = r.dataset.status || '';
      let show = r.innerText.toLowerCase().includes(q);
      if (show && newOnly && r.dataset.new !== '1') show = false;
      if (show && hideApplied && st === 'applied') show = false;
      if (show && hideHidden && st === 'hidden') show = false;
      if (show && interestedOnly && st !== 'interested') show = false;
      r.style.display = show ? '' : 'none';
    }});
  }}
  input.addEventListener('input', applyFilters);
  ['fNew','fHideApplied','fHideHidden','fInterested'].forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', applyFilters);
  }});

  // ---- Sorting ----
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

  applyFilters();
  loadStatuses();
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
