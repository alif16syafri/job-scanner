# Dita job discovery

Discovery and explainable triage only. No application submission, recruiter messaging, or application-form interaction exists in this project.

## Run

Requires Node.js 22+ and Google Chrome.

```sh
npm ci --ignore-scripts
npm test
npx --no-install playwright-cli install-browser chromium --only-shell
npm run discover
```

Outputs: `reports/latest.md`, `reports/latest.json`, and durable `data/state.json`. Discovery exit code 2 means partial coverage: GitHub Actions shows a warning and retains reports. Other nonzero exits are scanner failures and fail the workflow. Never delete or silently replace unreadable state.

## Search coverage

The initial eight employers are seeds, not a ceiling. Each run checks seeds, rotates through previously discovered sources, searches 12 role/market combinations on the web and one combined QA search per market on LinkedIn, and adds up to 20 new sources. The markets cover Jakarta, Indonesia remote, Singapore, Malaysia, UAE, Australia, Japan, UK, Germany, Netherlands, and APAC remote with six QA title variants. Edit `config/search.json` to expand them. Counts bound the work; this does not claim exhaustive coverage of every market or LinkedIn page.

LinkedIn searches sort newest first with a 24-hour lookback. Every scheduled run searches all configured markets and reads up to five pages per market. It stops sooner when the next page is unavailable or yields no new listings. Search engines can return stale or irrelevant postings. Search snippets are unverified until the employer page can be parsed. The system distinguishes first-seen and posted dates. Do not interpret a missing listing as closed.

Web search uses Bing RSS by default. Live checks returned weak coverage, so runs without `BRAVE_SEARCH_API_KEY` explicitly report limited web coverage and finish with a warning/failure status. Configure the key for a dedicated search provider; its availability and result quality still need validation. Search engine limits, robots policies, JavaScript-only pages and job-board layout changes can reduce coverage. Failures appear in the summary rather than becoming zero-job successes. Dedicated adapters cover Greenhouse, SmartRecruiters, Workable, Breezy and Stockbit pagination; generic HTML adapters do not support every ATS.

## Headless LinkedIn discovery

The scanner uses Playwright CLI with isolated headless Chromium. It restores a signed-in LinkedIn session from `.secrets/linkedin.json` locally, or from the `LINKEDIN_STATE_PATH` file if set. GitHub Actions can use the `LINKEDIN_STATE_B64` secret when configured. The scanner keeps only LinkedIn data from the supplied session and never publishes it. Treat the session file like a signed-in browser. Keep it private and out of Git, reports, and artifacts.

On macOS, the signed-in Jobs tab can supply the session without a browser extension. Enable Chrome remote debugging at `chrome://inspect/#remote-debugging`, leave the intended Jobs tab open, run `node scripts/import-linkedin-session.mjs`, and approve Chrome's connection dialog. This stores LinkedIn cookies locally and leaves the existing tab open. Turn remote debugging off after the import.

Searches use LinkedIn's location, date posted and most recent settings. Jakarta searches use Full-time. Indonesia-wide remote searches use Full-time and Remote. Overseas searches leave employment type open for triage. The job listing must confirm salary, working hours, and eligibility.

Source health reports missing or expired sessions, access restrictions and unreadable results. Other sources continue and GitHub Pages still publishes available results. Set `LINKEDIN_PAUSED=1` to skip LinkedIn for a local run.

## Triage

Mid-level and senior software QA, including manual roles. Jakarta/Indonesia target: IDR 16M net monthly, with IDR 15M for a suitable mid-level role. Gross or undisclosed amounts require review. India is excluded. Required US working hours are rejected; US geography and unknown hours require review. International salary, relocation, visa, language and country eligibility require confirmation. Scores use keyword matches to the confirmed stack, not invented skill proficiency. Listed unfamiliar technologies become checks, not claimed experience. Full-time is required for Indonesia roles; overseas contracts remain eligible.

The profile is deliberately non-sensitive: CV, phone, email, photo and employment documents are not read or uploaded. A `review` result is a candidate for manual evaluation, not authorization to apply. Keyword rules cannot prove salary, sponsorship, team pace or skill fit; inspect source text.

## GitHub Actions

This project is deployed to `alif16syafri/job-scanner`, a public repository explicitly selected by its owner. Only code and public job-listing history belong here. CVs, photos, account sessions and other personal documents must remain outside the repository. Existing `documents/` and `test/` folders are ignored. Do not use `git add -f` on personal documents.

The schedule is 01:17, 05:17, 09:17, 13:17, 17:17, 21:17 UTC: **08:17, 12:17, 16:17, 20:17, 00:17, 04:17 Jakarta**. Start times may be delayed. Workflow must be on the default branch. Manual `workflow_dispatch` is available.

Repository Actions settings must permit read/write workflow tokens. History is committed to the default branch after each run; branch rules must allow these commits or persistence fails visibly. One concurrency group prevents overlapping writers. Reports appear in run summaries and downloadable artifacts. GitHub failure notifications signal source problems; successful-run external notifications are not configured. Hosted-runner minutes and optional search API usage depend on your plan.

Deployment checklist:

1. Use the personal GitHub identity (`gitpersonal`).
2. Push this project to `alif16syafri/job-scanner`.
3. Optionally add `BRAVE_SEARCH_API_KEY` for broader web search.
4. Enable workflow write permissions; trigger a manual run.
5. Inspect source health, candidate relevance, and history persistence before trusting scheduled runs.

The current dashboard is published at https://alif16syafri.github.io/job-scanner/ after each scan. It includes search, company/location/source/score/triage filters, match reasons, eligibility checks, source health and scan freshness. Unknown salary or eligibility is not treated as a confirmed match. Scores are keyword heuristics. The scanner runs without a visible browser. No applications are submitted.

Run `npm run build:dashboard` to export the current saved scan to `dist/`. The exporter allowlists public job fields; CVs and browser session data are never included. GitHub Actions publishes this static directory through Pages. Reports and source history remain available through Actions and `data/state.json`.
