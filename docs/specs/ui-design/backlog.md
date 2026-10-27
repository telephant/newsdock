# ui-design — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Feed filters and search bar in the UI (P2):** `search_articles` exists on the API; the UI only lists. Needs its own spec (behaviour change).
- **Story drill-down view (P2):** show all `sources[]` of a story in a side sheet.
- **Editing subscriptions in the UI (P3):** from the ui-login backlog; agents own them today.
- **Storybook or visual regression tests (P3):** screenshots are reviewed by hand in this spec.
- **Brand identity: logo, wordmark, favicon set (P3):** this spec ships a text wordmark only.
- **i18n and CJK typography (P3):** GDELT titles are mixed-language (`docs/research.md`); check CJK font fallbacks on real titles.
- **Card layout for tables on phones (P3):** below 640 px the users, subscriptions and key tables hide their timestamp columns; a card per row would keep that information (found at T-09).
- **Repeatable screenshot review (P3):** the mock API and `puppeteer-core` script used at T-09 live outside the repo; commit them (or move to Playwright) if the review should be rerun in CI.
- **Lighthouse accessibility score (P3):** the 95+ target was not measured at T-09 (no tool installed).
- **Config page showing effective settings (P3):** from the externalize-config backlog.
