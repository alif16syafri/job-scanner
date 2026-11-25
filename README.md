# Dita job discovery

Discovery and explainable triage only. No application submission, recruiter messaging, or application-form interaction exists in this project.

## Run

Requires Node.js 22+ and Google Chrome.

```sh
npm ci --ignore-scripts
npm test
npm run discover
```

Outputs: `reports/latest.md`, `reports/latest.json`, and durable `data/state.json`. Discovery exit code 2 means partial coverage: GitHub Actions shows a warning and retains reports. Other nonzero exits are scanner failures and fail the workflow. Never delete or silently replace unreadable state.

## Search coverage

Every four-hour run checks the employer feeds in `config/sources.json`, refreshes previously discovered sources, and runs targeted searches across all configured markets. A rotating query list adds searches for individual QA titles. Search uses Bing RSS by default and supports `BRAVE_SEARCH_API_KEY` as an optional alternative. Search coverage and source failures appear on the dashboard.

Direct feeds include Greenhouse, Ashby, SmartRecruiters, Workable, Breezy and Stockbit. Search results stay unverified until the employer's page can be read. Remote roles still require confirmation of country eligibility and working hours.

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
