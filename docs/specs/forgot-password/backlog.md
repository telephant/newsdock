# forgot-password — Backlog (after this spec)

Priority: P1 next, P2 soon, P3 later.

- **Email verification at sign-up (P2, from the ui-login backlog):** verifies the address with the same mailer; closes the "squatted account" risk of this spec.
- **Local mail catcher in compose (P2):** a Mailpit-style service so the whole flow can be tried locally without a provider account.
- **Reset link as an alternative to the code (P3):** a signed link in the mail; needs a trusted public URL setting.
- **Change email address (P3):** confirm the new address with a code.
- **HTML mail templates and translations (P3).**
- **Notify the user after a password change (P3):** "your password was changed" mail.
- **Persist the request rate limit (P3):** today the per-email and per-address request limits live in memory (one API worker); count open codes by creation time in the database instead.
- **Resend / provider-specific adapter (P3):** only if SMTP stops being enough.
