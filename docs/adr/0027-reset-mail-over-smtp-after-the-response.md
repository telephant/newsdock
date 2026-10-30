# ADR-0027: Reset mail goes over plain SMTP, sent after the response, and the feature is off without configuration

Status: **Accepted 2026-10-29** (user chose sending after the response at `/spec-design forgot-password`; SMTP and the feature-off default follow spec D-1 and D-5)

## Context
The user chose a free email service to deliver the codes (spec D-1). Free plans differ and change: Brevo's free plan offers an SMTP relay with 300 mails a day; Resend wants a verified domain to reach arbitrary recipients; Mailgun's free tier without a card only reaches 5 authorized addresses; SendGrid ended its free plan on 2025-05-27; Gmail needs an app password and Google discourages them. The endpoint must also not reveal whether an account exists, including by how long it takes to answer.

## Options
**How mail is sent:** (a) **standard SMTP through the standard library (`smtplib`), provider = settings**; (b) one provider's HTTP API and SDK; (c) a mail library from PyPI.
**When it is sent:** (a) **after the HTTP response, in a background job that also does the user lookup and the database write**; (b) inside the request; (c) through a queue and a separate worker.
**Without configuration:** (a) **the feature is off (503, no link)**; (b) print the code in the server log.

## Decision
(a), (a), (a). SMTP is supported by every free provider, so switching provider is a settings change, and the standard library needs no dependency or vendor lock-in. Doing the lookup, the write and the send after the response means the foreground work is identical for known and unknown emails, so neither the body nor the timing tells them apart. A queue and worker would be heavier than one account flow needs. Printing codes in a log is a recovery backdoor for anyone with log access and is not offered. TLS is mandatory except for loopback hosts. A failed send deletes the unsent code and is only logged.

## Consequences
+ No new dependency; provider-neutral; Brevo's free plan works with settings only. + No enumeration through timing. + Easy to test with a fake mailer and a tiny local SMTP server.
− A database or send error after the response cannot be shown to the user (they see the generic confirmation and simply get no mail); it is logged. − `BackgroundTasks` run in the API process: a restart can drop a pending send (the user asks again), and bursts are bounded by the rate limits only. − The reset flow needs outbound access on port 587 or 465 and a provider account the owner must create. − No local way to try the flow without a provider (a mail catcher is in the backlog).
