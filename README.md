# Remote QA Job Scanner

Scans multiple remote job boards for **QA / Senior QA / SDET / Test Automation**
roles, filters + de-duplicates them, and produces:

- a **CSV** you can open in Excel/Sheets,
- a **searchable HTML dashboard** (`output/index.html`),
- optional **Telegram notifications** for *new* jobs only,
- ready-to-click **LinkedIn / Indeed / Wellfound / Google Jobs** search links
  (those sites block scraping, so we link to live searches instead).

Runs locally or automatically in the cloud via **GitHub Actions** (scheduled).

## Sources scanned

| Source | Type | Notes |
| --- | --- | --- |
| RemoteOK | Public API | Worldwide remote jobs |
| Remotive | Public API | Queried for qa/test/sdet/quality |
| We Work Remotely | RSS | Dev + DevOps + all-jobs feeds |
| Himalayas | Public API | Paginated, with seniority/timezone data |
| Greenhouse | Company boards | Add company slugs in `config.yaml` |
| Lever | Company boards | Add company slugs in `config.yaml` |
| LinkedIn / Indeed | Search links | Generated URLs (not scraped) |
| Google dorks | Search links | Career pages + LinkedIn, scoped SEA/GCC (not scraped) |

## Quick start (local)

```bash
cd ~/Workplace/remote-qa-jobs

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py
open output/index.html      # macOS; use xdg-open on Linux
```

That's it — the first run downloads jobs, writes `output/qa_jobs.csv` and
`output/index.html`, and records what it saw in `output/seen_jobs.json` so the
next run can tell what's new.

## Configuration

Everything is driven by [`config.yaml`](./config.yaml). The bits you'll touch most:

- **`keywords`** — what counts as a QA job.
- **`title_must_include`** — require a QA-ish word in the *title* (cuts noise).
- **`filters.max_age_days`** — currently `14`.
- **`filters.exclude_title_words`** — e.g. removes "manager", "intern".
- **`sources.greenhouse.companies` / `sources.lever.companies`** — add the
  company slugs you care about (see below).
- **`sources.search_url_helper.queries`** — the LinkedIn/Indeed searches.
- **`region_flags`** — jobs are *labelled* with a region (APAC/EMEA/etc.); this
  does **not** filter them out, per your "flag only" preference.

### Finding company slugs for Greenhouse / Lever

- **Greenhouse:** if a company's careers page is `boards.greenhouse.io/acme`
  or `job-boards.greenhouse.io/acme`, the slug is `acme`.
- **Lever:** if it's `jobs.lever.co/acme`, the slug is `acme`.

Add them under the relevant `companies:` list. Not every company uses these ATS
platforms — many big names don't, so mix in a few you're targeting.

## Google dorking (career pages beyond Greenhouse/Lever)

Not every company posts to an API-friendly board. To catch the rest, the scanner
generates **Google "dork" search links** — precise queries using operators like
`site:`, `intitle:`, `inurl:` — and drops them into the HTML dashboard under
**"Google dorks"**. You click a link, Google runs the search in your browser.

> **Why links and not auto-fetch?** Google actively blocks automated scraping of
> its results (you'll hit a CAPTCHA/"sorry" page). Clicking these in your normal,
> logged-in browser works fine and carries zero ban risk. That's the whole point
> of generating links instead of scraping.

Four kinds of dorks are produced, scoped to your enabled regions:

- **ATS / job boards** — one big `site:` query across Greenhouse, Lever, Ashby,
  Workable, Recruitee, Workday, BambooHR, SmartRecruiters, etc.
- **LinkedIn jobs** — `site:linkedin.com/jobs "<role>" (<region terms>) remote`,
  one link per role × region.
- **Generic company career pages** — `intitle:/inurl:careers|jobs` with the
  aggregators excluded, to surface self-hosted career sites.
- **Custom** — any templates you add with `{role}` / `{region}` placeholders.

### Configure it — `google_dorks` in `config.yaml`

- **`roles`** — readable role phrases used for per-role LinkedIn dorks.
- **`reuse_keywords`** — also fold your top-level `keywords` into the wide
  `site:` dorks.
- **`ats_sites`** — the ATS domains to target (supports `*` wildcards).
- **`regions` / `regions_enabled`** — currently **SEA** (Singapore, Indonesia,
  Malaysia, Philippines, Thailand, Vietnam, APAC...) and **GCC** (UAE, Dubai,
  Saudi Arabia, Qatar, Bahrain, Kuwait, Oman...). Add your own region groups
  freely; each becomes an `("A" OR "B" OR ...)` clause.
- **`freshness`** — `d`/`w`/`m`/`y` maps to Google's time filter (default `m` =
  past month).
- **`linkedin.enabled`, `generic_career.enabled`** — toggle those groups.
- **`custom_templates`** — e.g. `'site:*.smartrecruiters.com "{role}" {region}'`.

These links regenerate every run, so there's nothing extra to do — just open
`output/index.html` and click.

## Telegram notifications (optional)

1. Message **@BotFather** on Telegram, `/newbot`, and copy the **bot token**.
2. Send your new bot any message, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your **chat id**.
3. Export them before running:

```bash
export TELEGRAM_BOT_TOKEN="123456:ABC..."
export TELEGRAM_CHAT_ID="987654321"
python main.py
```

By default only **new** jobs are pushed (`telegram.only_new: true`), capped at
`max_notifications` per run. Run `python main.py --all` to notify every match, or
`python main.py --no-telegram` to skip messaging.

## Application tracking (Applied / Interested / Hidden)

The dashboard can track whether you've **applied** to a job, are **interested**,
or want to **hide** it — and this status is **shared and synced** across everyone
who opens the link (e.g. you and your partner on separate browsers) via a tiny,
free **Supabase** table. Status is keyed by the job's stable `uid`, so it survives
every re-scan/redeploy. There's also a per-row **NEW** badge, a **first-seen** date,
and filter toggles (New only / Hide applied / Hide hidden / Interested only).

**One-time Supabase setup:**

1. Create a free project at [supabase.com](https://supabase.com) and copy the
   **Project URL** and **anon/public key** (Project Settings ? API). Both are
   public by design — safe to embed in the page.
2. In the Supabase **SQL editor**, run:

```sql
create table job_status (
  uid text primary key,
  status text not null default 'applied',   -- applied | interested | hidden
  title text, company text, url text,
  updated_at timestamptz default now()
);
alter table job_status enable row level security;
create policy "anon all" on job_status for all to anon using (true) with check (true);
grant select, insert, update, delete on job_status to anon;
```

> This policy lets **anyone with the link** read/write status (no login). That's
> intentional for a small shared board. Want it locked down later? Switch to a
> shared-secret column or Supabase Auth and tighten the policy.

3. Wire the keys — either in `config.yaml` under `applications:` or (preferred for
   CI) as environment variables, which override the file:

```bash
export SUPABASE_URL="https://xxxx.supabase.co"
export SUPABASE_ANON_KEY="eyJ..."
python main.py
```

For the cloud run, add `SUPABASE_URL` and `SUPABASE_ANON_KEY` as **GitHub Actions
secrets** (and expose them as env vars in the workflow). Until keys are set, the
buttons render disabled with a "not configured yet" banner — the dashboard still
works read-only.

## Run it in the cloud (GitHub Actions)

1. Create a new GitHub repo and push this folder to it.
2. In the repo: **Settings ? Secrets and variables ? Actions ? New repository
   secret**, add:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. The workflow in [`.github/workflows/scan.yml`](./.github/workflows/scan.yml)
   runs twice daily (and on-demand from the **Actions** tab). It:
   - runs the scan,
   - commits the updated CSV + seen-cache back to the repo,
   - uploads the HTML/CSV as a downloadable **artifact**.
4. (Optional) To get a **live dashboard URL**, enable **Settings ? Pages ?
   Source: GitHub Actions** and uncomment the two Pages steps at the bottom of
   the workflow.

## Scheduling locally (alternative to Actions)

macOS `cron` example — scan every day at 9am:

```bash
crontab -e
# add:
0 9 * * * cd ~/Workplace/remote-qa-jobs && ./.venv/bin/python main.py >> output/cron.log 2>&1
```

## Project layout

```
remote-qa-jobs/
??? main.py                 # entrypoint
??? config.yaml             # all settings live here
??? requirements.txt
??? qajobs/
?   ??? models.py           # Job dataclass + dedup id
?   ??? core.py             # keyword/recency filter, region flag, sort
?   ??? state.py            # "seen jobs" cache for new-job detection
?   ??? outputs.py          # CSV / HTML / Telegram / search links / Google dorks
?   ??? http.py             # shared HTTP helper (retries, UA)
?   ??? sources/            # one module per job board
??? .github/workflows/scan.yml
```

## Notes & etiquette

- We send a descriptive User-Agent and retry politely; be a good citizen and
  don't crank the schedule to run every minute.
- RemoteOK's API asks that you credit them as a source — job links point back to
  Remote OK, which satisfies that.
- LinkedIn/Indeed are intentionally **not** scraped (ToS + anti-bot). The
  generated search links get you 90% of the value with 0% of the risk.
