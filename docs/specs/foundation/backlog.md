# foundation — Backlog (after Milestone 0)

Priority: P1 next, P2 soon, P3 later. Project-level milestones live in `../../roadmap.md` and `../mvp/backlog.md`; this file holds only foundation follow-ups.

- **OpenAPI → generated TS types (P1):** prove the API-to-UI contract link. Why: CLAUDE.md requires generated UI types; needs a real API route, so it lands in M1.
- **Run all services in compose with healthchecks (P1):** heartbeat pattern for workers. Why: M1 AC-15 needs it; M0 only builds the images.
- **Pre-commit hooks (P2):** format/lint on commit. Why: faster feedback than CI.
- **Dependency update bot and secret scanning in CI (P2):** Dependabot/Renovate, gitleaks-style scan. Why: hygiene before the repo is public.
- **CI speed (P3):** layer and dependency caching, per-app build matrix.
- **Dev container (P3):** reproducible editor environment for contributors.
- **Linux and Windows setup notes (P3):** M0 documents macOS arm64 only.
- **Runner image (P2):** `ubuntu-latest` becomes Ubuntu 26 on 2026-10-19 (GitHub notice in the CI run). Pin `ubuntu-24.04` or run the workflow once on the new image before that date.
- **Image scanning and SBOM (P3):** supply-chain checks, relevant for M5 cloud deploy.
