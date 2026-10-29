# ADR-0026: Reset codes are stored as a keyed hash, one open code per user

Status: **Accepted 2026-10-29** (user chose the keyed hash with an extra secret at `/spec-design forgot-password`)

## Context
Password reset by email (spec `forgot-password`) uses a 6-digit code, so there are only 10^6 possible values. The code must be stored so the API can check it later, must work once, expire, and survive only a limited number of wrong tries. A plain or salted hash of a 6-digit code can be brute-forced in well under a second, so anyone who can read the table during the code's lifetime could recover valid codes and take accounts.

## Options
**How the code is stored:** (a) **HMAC-SHA256 keyed with a server secret from the environment (`NEWSDOCK_RESET_CODE_SECRET`), bound to the user id**; (b) SHA-256 with a per-row salt, no extra secret; (c) argon2id with the account hasher (slow, no extra secret); (d) store the code in clear.
**How many open codes:** (a) **one row per user, a new request replaces it**; (b) several rows, each with its own expiry.

## Decision
(a) and (a). A keyed hash makes a database-only leak useless for guessing: the attacker also needs the secret, which lives in the environment next to the SMTP password. Binding the user id into the message stops a row being replayed for another account. One row per user makes "a newer request replaces the older" a primary-key upsert and keeps the attempt budget per issued code. The comparison is `hmac.compare_digest`. The feature stays off unless the secret (at least 32 characters) is set.

## Consequences
+ A leaked table does not reveal codes. + Replacement, single use and the attempt cap are one row with simple SQL. + No new dependency (standard library).
− A second operator secret to create and keep (`openssl rand -hex 32`); rotating it invalidates open codes (they live 15 minutes, so that is harmless).
− Option (b) would be simpler to operate but is only as safe as the table; (c) slows an attacker by about 50 ms a guess, not enough for a 10^6 space.
− One open code per user: asking again before using the first one makes the first useless.
