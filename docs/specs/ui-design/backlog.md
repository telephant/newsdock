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
- **Owner review of the screenshots (P2):** `docs/specs/ui-design/screens/`; the visual call is subjective and only the implementer has looked (found at verify).
- **Other browsers (P3):** verified in Chrome only; repeat in Safari and Firefox (dark-mode first paint, `mask-image` fade, `Intl.RelativeTimeFormat`).
- **Hand run on the real stack (P3):** the review used a mock API; try `make up` with a real login cookie and live GDELT data.
- **Dark-theme Lighthouse and a frame-by-frame flash check (P3):** the light-theme Lighthouse score is 100; the dark theme and the first-paint flash were checked only by the class being set before DOMContentLoaded.
- **Config page showing effective settings (P3):** from the externalize-config backlog.
