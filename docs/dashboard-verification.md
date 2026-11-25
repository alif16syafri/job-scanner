# Dashboard verification

28 unit tests pass. Dashboard export and filter tests cover combined filters, hidden excluded jobs, latest-run detection, missing timestamps, removal of HTML markup, unsafe URLs and field allowlisting.

Isolated headless Chrome exercised every filter, both reset buttons, sorting, latest-run checkbox, job details, coverage anchor, healthy-source expansion, theme toggle, failed-data state and retry. Corrected a native form reset timing defect; the same browser test then passed.

Rendered at 390, 640, 900 and 1440 pixels wide with no document overflow. Desktop, mobile and dark screenshots inspected. No page JavaScript errors. Testing used a separate temporary headless browser, not the user's Chrome profile or LinkedIn session.

Delivery gate:

- Hard Gate PASS: real saved data, no generated imagery or statistics, labeled controls, empty/loading/error states, focus styles, viewport checks, HTTPS links, no third-party scripts.
- Purpose Gate PASS: forest accent identifies matching evidence; amber identifies checks; design reasons are documented in dashboard-design.md. No gradients, glow or decorative icons.
- Liveliness PASS: editorial shortlist heading, ranked job list as focal point, clear filter/list/coverage hierarchy; energy 1, rhythm 2, motion 1.
- Craftsmanship PASS: tested controls and dark/light states, no content clipping at tested widths, review found no important security or workflow defects. Public-field exporter avoids publishing browser/session or CV data.

Re-run with `npm run build:dashboard` then `node scripts/check-dashboard.mjs`. Uses installed Chrome on macOS; elsewhere install Playwright's Chromium or specify `DASHBOARD_BROWSER`. Screenshots are written to the temporary directory.
