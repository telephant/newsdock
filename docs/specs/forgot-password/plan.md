# forgot-password — Plan

Spec: [spec.md](spec.md) · Design: [design.md](design.md) · Tests: [tests.md](tests.md) · Tasks: [tasks/](tasks/)

## Plan validation

Run 2026-10-29 with grep over `spec.md`, `tests.md`, `design.md`, `design-detail.md`, `tasks/`:

| Check | Result |
|---|---|
| AC → test (AC-1…AC-17 each appear in a TC row of tests.md) | pass (TC-1…TC-24; AC-2 has TC-2, TC-3, TC-19; AC-5, AC-6 have TC-23; AC-11, AC-12, AC-17 share TC-20) |
| AC → design (the coverage table of design.md lists AC-1…AC-17) | pass |
| AC → task (each AC in at least one task's `Implements`) | pass |
| Orphan tests (TC-1…TC-24 each named in some task's "Tests to turn green") | pass |
| Names consistent (routes, `invalid_or_expired_code`, `password_reset_unavailable`, `too_many_reset_requests`, `too_many_reset_attempts`, `password_resets`, `NEWSDOCK_RESET_CODE_SECRET`, `NEWSDOCK_SMTP_PASSWORD`, `password_reset_enabled`, `SmtpMailer`, `FakeMailer`, `reset_clock`, the `smtp_*` and `auth_reset_*` settings) | pass after one fix (T-06 now names the three error codes and the feature-off behaviour) |
| No doc treats a Proposed ADR as decided | pass (ADR-0026 and ADR-0027 are Accepted 2026-10-29) |
| Backlog leakage (email verification, mail catcher in compose, reset link, change of email, HTML templates, persisted request limits, a provider-specific adapter) | none in tasks |
| Untagged claims | none; Brevo's connection settings stay tagged as secondary-source |
| Invented numbers presented as requirements | none; code length, lifetime, attempt cap and the three limits are listed as provisional config values |
| Terms missing from the glossary | two fixed (HMAC, upsert) and one added (background task) |
| Open questions / unchecked checklist items | none (design checklist fully ticked; one default, the lockout clear, is marked as mine) |

Findings fixed: T-06 error codes, glossary.

Risks carried into implementation:

- **R-1 (medium):** the biggest unverified claim is that a response is delivered *before* a `BackgroundTasks` job finishes under uvicorn, which AC-1 and ADR-0027 rely on. T-01 proves it first. If it fails the design changes (a thread pool), so T-01 stops and asks.
- **R-2 (medium):** nothing here talks to a real provider; the Brevo settings come from secondary sources and the only real-send check is the optional manual list in tests.md, run by the owner with their account. A wrong Brevo detail is a settings fix, not a code change.
- **R-3 (low):** the request and attempt limits are in memory (one API worker); a restart clears them. The per-code attempt cap lives in the database. Persisting the request limits is in the backlog.
- **R-4 (low):** a database or SMTP error after the response is only logged (ADR-0027): the user gets the generic confirmation and no mail, and tries again.
- **R-5 (low):** this work sits on the unmerged `semantic-search` branch; migration 0010 follows 0009, so that branch merges first.

## Order and reasons

**Spike first (T-01).** AC-1 and the "no enumeration by timing" design (ADR-0027) need the response to leave before the background job finishes, and the tests need a small SMTP server written with the standard library. T-01 proves both, plus the per-key use of `SignupLimiter`, before any production code. A real provider cannot be spiked without the owner's account (R-2).

Walking skeleton: T-02 (rules, limiters) and T-03 (mailer) and T-05 (settings) are independent pieces; T-04 adds the table and store; T-06 joins them into working routes; T-07 puts the web on top; T-08 documents and runs everything.

| Task | Title | Implements | Depends on |
|---|---|---|---|
| T-01 | Spike: SMTP stub, background-task timing, per-key limiter | de-risks AC-1, AC-2, AC-11, AC-14 | none |
| T-02 | Reset rules and limiters (pure domain) | AC-2, AC-11, AC-12, AC-17 | T-01 |
| T-03 | Mailer port and SMTP adapter | AC-2, AC-14 | T-01 |
| T-04 | Table, model and reset store (migration 0010) | AC-5, AC-6, AC-8, AC-9 | T-02 |
| T-05 | Settings, secrets and the feature switch | AC-13 | none |
| T-06 | Routes: forgot-password, reset-password, options | AC-1…AC-14, AC-17 | T-02, T-03, T-04, T-05 |
| T-07 | Web: link, email screen, code and new-password screen | AC-15, AC-16 | T-06 |
| T-08 | Docs, final checks and the manual-check kit | AC-13 (docs), all (traceability) | T-06, T-07 |

## Milestones

- **Pieces ready (after T-05):** rules, limiters, mailer, store, settings all tested on their own; AC-2 (adapter and hash), AC-5, AC-6, AC-8, AC-9 at store level.
- **API works (after T-06):** AC-1 to AC-14 and AC-17 through the routes with a fake mailer.
- **Web works (after T-07):** AC-15, AC-16.
- **Closed (after T-08):** docs agree, `make check` green, manual-check list ready for the owner.

## Effort (rough, relative)

T-01 small · T-02 small · T-03 medium · T-04 medium · T-05 small · T-06 large (the order of checks, background job, wiring, 15 tests) · T-07 medium · T-08 small. No dates.

## Definition of Done (every task)

Tests written first and green · `make check-python` (and `make check-web` for T-07) green · Docker tests only through `side_db`, run by explicit file path, never a whole folder, and the dev stack's database compared against its baseline afterwards · docs and ADRs updated where the task changes a repeated fact · no secret, real address or real mail in any file or test · task marked in "Progress" below.

## Progress

- T-01 ✅ 2026-10-29 — spike, findings in [spike.md](spike.md); no production code. Verified: a standard-library SMTP stub (EHLO, MAIL FROM, RCPT TO, DATA, QUIT) accepts `smtplib.send_message` with headers and a dot-leading body line intact, and `login` against a server without AUTH raises `SMTPNotSupportedError` (the adapter must skip login when no user is set); under uvicorn a sync route returns in 28 ms while its `BackgroundTasks` job is still blocked (R-1 retired, ADR-0027 stands), whereas `TestClient` waits for the job (1,007 ms), so only AC-1 needs the live-server test; `SignupLimiter(M, 0, window)` is a per-key counter (refuses call M+1, independent keys, retry-after > 0, 0 = off); `request.client.host` is the socket peer under uvicorn and settable in `TestClient`. No change to spec, design or ADRs. Not verified by design: a real provider.
