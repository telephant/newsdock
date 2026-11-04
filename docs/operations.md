# Operating newsdock

The operator's guide: accounts and roles, password reset by mail, agent API keys, push streams, and the longer troubleshooting list. Setup and the quick start are in the [project README](../README.md). Every setting named here lives in [`infra/config/newsdock.yaml`](../infra/config/newsdock.yaml) unless it is a secret — secrets stay in `.env`.

## Accounts and login (M2)

The UI needs a login. Open **http://127.0.0.1:3000** (the compose default; `http://localhost:3000` is redirected there, because the login cookie only works when page and API share a hostname). Use *Sign up*: **the first account becomes the `owner`**, every later one a `viewer`.

| Role | May |
|---|---|
| `viewer` | read the feed and articles, watch `/live`, manage its own agents, keys and subscriptions |
| `admin` | the same (admin and viewer hold equal permissions since agent ownership, M2d) |
| `owner` | also change roles and delete users (`/admin/users`), and see every agent; the last owner can never be demoted or deleted |

- **Sign-up is open by default.** Anyone who can reach the web port can register a `viewer` account, which can read articles and create its own agents and API keys. Close it with `api.auth_signup_open: false` (then create accounts by temporarily re-opening it); there is no email verification, invite or CAPTCHA.
- **Sign-ups and agents are rate limited** (`0` turns a limit off): `auth_signup_max_per_address` (5) counted sign-ups per client address and `auth_signup_max_total` (50) in total per `auth_signup_window_minutes` (60) answer HTTP 429 with `Retry-After`; `agents_max_per_user` (10) agents per non-owner user answers 409 `too_many_agents` (the `owner` role and the admin token are exempt, disabled agents count). The counters live in memory in the single API process and reset on restart. The address is the TCP peer address, and `X-Forwarded-For` is ignored because a client can forge it; behind Docker Desktop every browser on the host arrives as the Docker gateway address, so locally the per-address limit (5 per hour) is in effect the total: raise `auth_signup_max_per_address` if you create more accounts than that on one machine.
- **Locked-out owner:** `make user-reset-password EMAIL=<email>` asks for a new password twice (not echoed), ends that user's sessions and lifts a login lockout. It needs `NEWSDOCK_ADMIN_TOKEN` in `.env` and the api up; a session cannot do this, only the token.
- **Reads are not open:** `GET /api/articles*` accepts a browser session or an agent key. `api.auth_required: false` (with `web.login_required: false`) switches login off for local experiments.
- Passwords are hashed with argon2id; sessions are server-side (12 h idle, 7 days absolute, both in the config file); five wrong passwords for one account lock it for 15 minutes.

## Password reset by email (M2f)

A user who forgot their password can ask for a 6-digit code by email on `/forgot-password`, then set a new one on `/reset-password`. The code works once, for `auth_reset_code_minutes` (15), and dies after `auth_reset_max_attempts` (5) wrong tries. A reset ends all of that user's sessions and lifts a login lockout. **The feature is off until you configure mail**: without it the routes answer 503 `password_reset_unavailable` and the login page shows no link (`GET /api/auth/options` says `password_reset_enabled: false`). The operator path `make user-reset-password` is unchanged.

Any SMTP server works; the provider is only settings. With a free [Brevo](https://www.brevo.com) account (values below are from secondary sources, not checked against Brevo's current pages):

1. Create the account, verify one sender address, and create an SMTP key (Brevo: SMTP & API).
2. In `infra/config/newsdock.yaml`, section `api:`: `smtp_host: smtp-relay.brevo.com`, `smtp_port: 587`, `smtp_security: starttls`, `smtp_user: <your SMTP login>`, `mail_from: <the verified sender>`.
3. In `.env` (never in the file): `NEWSDOCK_SMTP_PASSWORD=<the SMTP key>` and `NEWSDOCK_RESET_CODE_SECRET=$(openssl rand -hex 32)` (at least 32 characters; it keys the stored code hash, so changing it voids open codes).
4. `docker compose --env-file .env -f infra/compose.yaml up -d api`, then check `curl http://127.0.0.1:8000/api/auth/options`.

The same settings fit Gmail with an app password (`smtp.gmail.com`, 587, `starttls`) or Resend's SMTP. `smtp_security: ssl` is for port 465; `none` is accepted only for a loopback host (a local test server) and never with a login. Notes: mail is sent after the HTTP response, so a known and an unknown address answer the same way and at the same speed; the request limits (`auth_reset_max_per_email` 3, `auth_reset_max_per_address` 20, `auth_reset_max_tries_per_address` 20 per `auth_reset_window_minutes` 60) are in memory in the one API process; the code is never logged. Migration `0010` creates the `password_resets` table (`make migrate`). Details: [spec](specs/forgot-password/spec.md), [ADR-0026](adr/0026-reset-codes-keyed-hash-single-row.md), [ADR-0027](adr/0027-reset-mail-over-smtp-after-the-response.md); a manual check with a real account is listed in [tests.md](specs/forgot-password/tests.md).

## Agents and API keys (M2)

MCP (`/mcp`) needs an agent API key; `api.auth_required` (default `true`) turns that off for local experiments. Agents are registered by a signed-in user (in the UI at `/admin/agents`) or by the operator with the admin token below. **Each agent belongs to the user who created it:** a user sees and manages only their own agents, keys and subscriptions, and the `owner` role sees all of them. Agents made with the admin token (`make agent-create`), agents from before ownership existed (for example `demo-financial`) and agents whose creator was deleted have **no owner**: they keep working, but only the `owner` role (in the UI) and the admin token can manage them.

1. For the command line, put a long random `NEWSDOCK_ADMIN_TOKEN` in `.env` and start the stack (while it is empty the token opens nothing; signed-in users can still manage their own agents in the UI).
2. `make agent-create NAME=demo-financial` prints the agent's key **once**; only a hash is stored. More routes: `GET /api/admin/agents`, `POST /api/admin/agents/{id}/keys`, `DELETE /api/admin/agents/{id}/keys/{key_id}`, `POST /api/admin/agents/{id}/disable|enable` (all with `Authorization: Bearer <admin token>`, which reaches every agent, or a logged-in session, which reaches the caller's own agents, or every agent for the `owner` role; another user's agent answers 404).
3. Put the key in `.env` as `NEWSDOCK_AGENT_API_KEY` and restart the agent. Any MCP client sends `Authorization: Bearer <key>`.

The server keeps each agent's position: `list_new_articles` without a cursor resumes after the last `ack_cursor` the agent sent (call it after finishing a batch), and each agent is limited to `api.rate_limit_per_minute` requests (HTTP 429 with `Retry-After`).

## Subscriptions and push streams (M2)

An authenticated agent can save filters and have matching new articles pushed to it over Server-Sent Events, instead of polling `list_new_articles`.

```bash
KEY=ndk_...   # from `make agent-create NAME=<name>`
# the body is the filter: theme (exact, or a prefix like ECON_*), domain, title text,
# min_negativity (a number 0-100: only articles whose GDELT negative-tone share is at least that); all optional
curl -sS -X POST http://127.0.0.1:8000/api/subscriptions -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"theme":"ECON_*","domain":"example.com"}'
curl -sS -X POST http://127.0.0.1:8000/api/subscriptions -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' -d '{"min_negativity": 8}'
curl -N -H "Authorization: Bearer $KEY" http://127.0.0.1:8000/api/subscriptions/<id>/stream
curl -N -H "Authorization: Bearer $KEY" -H "Last-Event-ID: <last id>" .../stream   # resume
```

Each event is `id: <cursor>`, `event: article`, `data: <article summary JSON>`; idle streams get `: ping` comment lines every `api.sse_keepalive_seconds`. Delivery is at-least-once: a reconnect with `Last-Event-ID` resumes strictly after that article (duplicates are possible, dedupe by `article_id`). Without `Last-Event-ID` a stream starts after the agent's acknowledged cursor, or from the last hour for a new agent; streaming never moves that cursor, only `ack_cursor` does. Other routes: `GET /api/subscriptions` (own), `DELETE /api/subscriptions/{id}`; limits `api.subscriptions_max_per_agent` (409), `api.sse_max_streams_per_agent` (429); `GET /api/admin/subscriptions` lists everyone's (admin token). A revoked key or disabled agent ends its open streams within one keep-alive interval. New articles reach streams through a Postgres `NOTIFY` raised by a trigger on `articles` ([ADR-0018](adr/0018-sse-streams-wake-on-listen-notify.md)).

## Troubleshooting

The first checks (missing tools, ports, `.env`) are in the [README](../README.md#troubleshooting); these are the longer-tail ones:

- **Raw `docker compose` complains about missing variables:** pass the env file, e.g. `docker compose --env-file .env -f infra/compose.yaml ps` (compose looks for `.env` next to the compose file otherwise).
- **Embedder logs `ollama unavailable`, or `semantic_search` answers `embedding_unavailable`:** Ollama is not running on the host or `nomic-embed-text` is not pulled (`ollama pull nomic-embed-text`). Nothing is lost: articles are stored without a vector and the embedder fills them in on a later pass; `hybrid` search falls back to word matching meanwhile.
- **`semantic_search` with `scope=body` or `all` matches only words, not meaning:** body passage vectors are opt-in (`embedder.embed_passages`, default off — ADR-0036 amendment); without them the body legs use full-text search only.
- **Agent logs `batch failed`:** usually Ollama is not running on the host (`ollama list` must answer); the agent retries and, because it only acks after a finished batch, re-reads the same batch.
- **A stream stays silent:** check the subscription's filter (`GET /api/subscriptions`) and that new articles are arriving (GDELT slots land every ~15 min); `: ping` lines mean the connection is healthy. A `429` on connect means the agent already has `api.sse_max_streams_per_agent` open streams.
- **Agent logs `the API rejected this agent's key (HTTP 401)`:** `NEWSDOCK_AGENT_API_KEY` is empty, wrong or revoked; issue a new key with `make agent-create` (or set `api.auth_required: false` for local experiments).
- **Many bodies stay `pending` or `failed`:** the extractor fetches one page per site at a time and honours robots.txt and crawl delays, so a backlog right after `make up` is normal; `blocked_robots`, `not_html` and `too_large` are final statuses, not errors.
