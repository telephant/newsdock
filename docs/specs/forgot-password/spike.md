# forgot-password — T-01 spike findings

Run 2026-10-29 with a throwaway script (not committed) against the project's own environment: FastAPI 0.142.2, Starlette 1.7.0, uvicorn 0.54.0, Python 3.12. No production code was written. Every result below was observed in this run.

## 1. A standard-library SMTP stub is enough for the adapter test

| Question | Finding |
|---|---|
| Can a ~45-line threaded `socketserver` stub that speaks only EHLO/HELO, MAIL FROM, RCPT TO, DATA (end with `.`) and QUIT accept `smtplib.SMTP(host, port, timeout).send_message(EmailMessage)`? | **Yes [verified].** The stub received the commands `EHLO, MAIL FROM, RCPT TO, DATA, QUIT`, the envelope `<noreply@example.test>` → `<ada@example.com>`, and the headers `From`, `To`, `Subject` and `Auto-Submitted: auto-generated` intact |
| Body fidelity | The body arrived intact, including a line that starts with a dot (`smtplib` doubles it; the stub removes the extra dot) **[verified]** |
| What if no `AUTH` is advertised and the adapter calls `login`? | `smtplib` raises `SMTPNotSupportedError`. So the adapter must skip `login` when no user is configured, which is the `none` mode for a local relay **[verified]** |

Consequence for T-03: `StubSmtpServer` can live inside `test_smtp_mailer.py` (no new dependency, no `aiosmtpd`). TLS ordering (`starttls` → `ehlo` → `login`) cannot be proved against this plain stub and stays a fake-`smtplib` unit test (TC-22), as planned.

## 2. The response leaves before the background job finishes (R-1 retired)

| Setup | Finding |
|---|---|
| Sync FastAPI route calling `BackgroundTasks.add_task(blocking_job)` under a live **uvicorn** server, job blocked on an event | **The response arrived in 28 ms while the job was still blocked** (started, not finished); after the event was set the job finished **[verified]** |
| The same route under Starlette's **`TestClient`**, job sleeping 1 s | **The call took 1,007 ms: the job finished before the call returned [verified]** |

Consequences: ADR-0027 (send after the response) works as designed. AC-1 (the answer arrives before a slow send finishes) needs the live-server test (TC-1) and cannot use `TestClient`; every other AC can use `TestClient` and simply assert on the mailer and the database after the call returns, because the background job has finished by then. No design change.

## 3. `SignupLimiter` works as a per-key counter

With `SignupLimiter(3, 0, 3600, clock)`: five calls for one key gave `[True, True, True, False, False]`, a second key was independent, the refusal carried a positive `Retry-After`, the key was allowed again after the window, and a limit of 0 switched it off **[verified]**. So C-45 can be built on it without new counting code, as designed.

## 4. The client address

Under uvicorn, `request.client.host` was `127.0.0.1`; under `TestClient(app, client=("10.1.2.3", 5555))` the route saw `10.1.2.3` **[verified]**. So AC-12 and AC-17 can be tested with different addresses exactly as the sign-up limiter tests do, and the limiter key is the socket peer (not `X-Forwarded-For`), the same stance as `signup-rate-limit`.

## 5. What the spike changes

- Nothing in the spec, design or ADRs. R-1 is retired.
- **Still unverified, deliberately:** a real provider. Brevo's connection settings stay **[secondary sources]**; the only real-send check is the optional manual list in tests.md, to be run by the owner.
- Test-writing notes recorded in tests.md already hold (live server for TC-1, `StubSmtpServer` in the unit test file).
