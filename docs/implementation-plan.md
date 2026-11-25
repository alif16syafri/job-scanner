# Discovery and triage implementation plan

Goal: discover software QA jobs across the agreed markets every four hours, retain history, and explain triage. No application code.

Architecture: Node.js 22, pinned Playwright CLI for LinkedIn, public employer feeds and HTML/JSON-LD extraction, rotating web searches, JSON history committed by GitHub Actions. No paid AI service is required. Brave Search is optional; Bing RSS is the default search source and may be limited.

- [x] Test salary, location, hours, manual-role eligibility, identity deduplication, and rotating coverage.
- [x] Implement employer adapters and bounded discovery of new sources.
- [x] Implement read-only LinkedIn CLI adapter that stops on challenges.
- [x] Implement persistent job state, explainable reports, and source health.
- [x] Prepare four-hour workflow, secret handling, and deployment documentation.
- [x] Validate live employer sources, CLI output, and document limited web coverage and missing LinkedIn authentication.
- [ ] Deploy after GitHub authentication and repository selection are available.

Constraints: no auto-apply, no CAPTCHA bypass, no committed CV or browser sessions. Source failures must be visible. Unpublished salary and visa/remote eligibility are unknown, never inferred from title or search query.
