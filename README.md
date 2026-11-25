# Dita job discovery

Discovery and explainable triage only. No application submission, recruiter messaging, or application-form interaction exists in this project.

## Run

Requires Node.js 22+ and Google Chrome.

```sh
npm ci --ignore-scripts
npm test
npm run discover
```

Outputs: `reports/latest.md`, `reports/latest.json`, and durable `data/state.json`. A nonzero discovery exit means incomplete coverage; partial results are still saved. Never delete or silently replace unreadable state.

## Search coverage

The initial eight employers are seeds, not a ceiling. Each run checks seeds, rotates through previously discovered sources, searches 12 role/market combinations on the web and six on LinkedIn, and adds up to 20 new sources. The 66 combinations cover Jakarta, Indonesia remote, Singapore, Malaysia, UAE, Australia, Japan, UK, Germany, Netherlands, and APAC remote with six QA title variants. Edit `config/search.json` to expand them. Counts bound the work; this does not claim exhaustive coverage of every market or LinkedIn page.

LinkedIn searches sort newest first with a seven-day lookback to overlap missed runs. Only the first visible page per query is read. Search engines can return stale or irrelevant postings. Search snippets are unverified until the employer page can be parsed. The system distinguishes first-seen and posted dates. Do not interpret a missing listing as closed.

Web search uses Bing RSS by default. Live checks returned weak coverage, so runs without `BRAVE_SEARCH_API_KEY` explicitly report limited web coverage and finish with a warning/failure status. Configure the key for a dedicated search provider; its availability and result quality still need validation. Search engine limits, robots policies, JavaScript-only pages and job-board layout changes can reduce coverage. Failures appear in the summary rather than becoming zero-job successes. Dedicated adapters cover Greenhouse, SmartRecruiters, Workable, Breezy and Stockbit pagination; generic HTML adapters do not support every ATS.

## LinkedIn session

LinkedIn prohibits third-party automated access and may restrict accounts. This read-only adapter stops on login walls, access challenges, and unreadable pages. It does not bypass restrictions.

Sign in manually on your machine, then save state:

```sh
mkdir -p .secrets
npx playwright-cli -s=dita-login open https://www.linkedin.com/login --headed --browser chrome
# Complete sign-in in the browser, then:
npx playwright-cli -s=dita-login state-save .secrets/linkedin.json
npx playwright-cli -s=dita-login close
chmod 600 .secrets/linkedin.json
```

The default runtime session path is `.secrets/linkedin.json`; override with `LINKEDIN_STATE_PATH`. Upload its base64 content as GitHub Actions secret `LINKEDIN_STATE_B64`, without printing it to logs:

```sh
python3 -c 'import base64,pathlib; print(base64.b64encode(pathlib.Path(".secrets/linkedin.json").read_bytes()).decode())' | gh secret set LINKEDIN_STATE_B64 --repo OWNER/REPO
```

Session state grants account access. Never commit or upload it as an artifact. Cloud runners may trigger login verification despite a valid local session. Renew manually when needed. Missing state is reported as `needs_login`, with other sources continuing.

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
3. Add `LINKEDIN_STATE_B64`; optionally add `BRAVE_SEARCH_API_KEY`.
4. Enable workflow write permissions; trigger a manual run.
5. Inspect source health, candidate relevance, and history persistence before trusting scheduled runs.

This replacement does not publish the old GitHub Pages dashboard. Current results are in Actions summaries, report artifacts and `data/state.json`. Any previously published Pages site is historical and must not be used as the current scan result. The previous implementation remains available in Git history.
