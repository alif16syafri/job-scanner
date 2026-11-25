# Verification

- Unit suite: 23 passing cases cover triage, rotating searches, canonical URLs, durable deduplication, job extraction, navigation-only failures, private URL rejection, CLI search parameters, and challenge detection.
- Public live smoke test: 15 records, 13 retained for manual review. Two records rejected. Salary/eligibility are not confirmed. Candidate count is a point-in-time observation, not an application-ready count.
- Public feeds verified: Cermati SmartRecruiters list/details, PayPay Greenhouse, YouTrip Workable list/details, Marex Breezy. Public detail extraction verified for Stockbit, Justlife, idataraya and Brankas. Stockbit pagination verified through three pages.
- Browser smoke test: isolated Chrome on example.com; CLI `eval --raw` returned valid JSON. No LinkedIn account was accessed. Authenticated LinkedIn discovery remains unverified pending saved session.
- GitHub Actions YAML parsed successfully using YAML 1.2 validator. Schedule reviewed as six runs/day four hours apart. No GitHub workflow has run yet.
- Review fixes: preserve individual JSON-LD posting URLs; detect negative visa-sponsorship wording; reject recognized non-target onsite locations; prefer configured seed settings over persisted adapters; reject navigation-only extraction. Regression suite passed after fixes.
- Limits: heuristic matching requires human review; unknown city/country, hours, salary and work authorization cannot be proven by keyword checks. Generic HTML location fields may remain empty. URL deduplication does not guarantee all cross-board reposts collapse. LinkedIn reads first visible page per rotated query. Generic search fallback is weak; a dedicated search key is required for dependable broad web coverage.
