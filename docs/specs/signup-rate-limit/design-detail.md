# signup-rate-limit — Design detail

Reference only; not required reading for approval. Overview: [design.md](design.md).

## 1. SignupLimiter (C-30, `apps/api/src/newsdock_api/domain/signuplimit.py`)

```python
class SignupLimiter:
    def __init__(
        self,
        max_per_address: int,
        max_total: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        *,
        max_entries: int = 10_000,
        prune_above: int = 1_000,
    ) -> None: ...

    def attempt(self, address: str) -> Decision:
        """Count one sign-up attempt unless a window refuses it."""
```

State: `_per_address: dict[str, tuple[int, float]]` (count, window start), `_total: tuple[int, float]`, one `threading.Lock`.

Algorithm for `attempt(address)` under the lock, `now = clock()`:

1. For each enabled limit (max > 0), read its window; a window whose `now - start >= window_seconds` counts as empty.
2. A limit refuses when `count >= max` inside a live window; its wait is `ceil(start + window - now)`, at least 1.
3. If any limit refuses: return `Decision(False, max(waits))` and record nothing.
4. Otherwise record in every enabled limit: a new window `(1, now)` when empty or expired, else `(count + 1, start)` (the window is never extended), then prune and return `Decision(True)`.

Both maxima 0 means `attempt` always returns `Decision(True)` and keeps no state (AC-8, AC-5 "limiter holds no entry").

Pruning matches `LoginLimiter`: the per-address dict is re-inserted last on update (dict order = recency); above `prune_above` entries, expired windows are dropped; above `max_entries` the oldest are evicted. `tracked()` returns the number of address entries for tests (AC-9).

Settings property: `Settings.signup_window_seconds = auth_signup_window_minutes * 60`.

## 2. Sign-up route (C-31)

`build_accounts_router(..., signup_limiter: SignupLimiter, ...)`; in `create_app` the limiter is built from settings, with an optional `signup_limiter` argument for tests (as `login_limiter`).

```python
@router.post("/signup", status_code=201)
def signup(body: Credentials, request: Request) -> PublicUser:
    ensure_signup_open(...)  # 403 signup_closed
    email = normalize_email(...)
    check_password(...)  # 422
    address = request.client.host if request.client else "unknown"
    decision = signup_limiter.attempt(address)
    if not decision.allowed:
        raise HTTPException(
            429, "too_many_signups", headers={"Retry-After": str(decision.retry_after)}
        )
    user = store.create_user(email, hasher.hash(body.password))  # 201 / 409
```

The limiter runs before `hasher.hash`, so a refused request costs no CPU beyond validation. The first-account path is untouched (AC-7). Logging: `signup limited` at info, without the address or email (the address is personal enough for a log line to omit; the count is what matters).

## 3. Agent quota (C-32)

```python
# domain/agents.py
def agent_quota_reached(owned: int, maximum: int) -> bool:
    return maximum > 0 and owned >= maximum
```

- `SqlAgentsRepo.count_owned(owner_id: str) -> int`: `SELECT count(*) FROM agents WHERE owner_id = :o`, all statuses. Added to the `AgentRegistry` protocol and to the unit fakes.
- `adapters/admin.py` `create_agent`, before `registry.create_agent`: if `not scope_for(who).everything` (so a non-owner user) and `agent_quota_reached(registry.count_owned(who.user_id), max_agents_per_user)`: `HTTPException(409, "too_many_agents")`.
- `build_admin_router` receives `max_agents_per_user: int` from settings.
- A taken name still returns 409 `name_taken`; the quota check runs first, so at the cap a user sees `too_many_agents` for any name.

## 4. Settings (C-33)

| Key (api section) | Default | Meaning |
|---|---|---|
| `auth_signup_max_per_address` | 5 | counted sign-ups per peer address per window; 0 = off |
| `auth_signup_max_total` | 50 | counted sign-ups, all addresses, per window; 0 = off |
| `auth_signup_window_minutes` | 60 | length of both windows |
| `agents_max_per_user` | 10 | agents one non-owner user may own; 0 = off |

Env names follow the loader (`NEWSDOCK_AUTH_SIGNUP_MAX_PER_ADDRESS`, …). `infra/config/newsdock.yaml` gets the four rows with the default values and a comment each; `make config-python` (AC-15) checks key existence and default equality.

## 5. Web (C-34)

- `signupMessage(failure)`: add `if (failure.status === 429)` → `Too many sign-ups from here. Try again in <formatWait(retryAfter)>.` (or `later` without a wait), reusing `formatWait`.
- `agentActionMessage(failure)`: add `too_many_agents` → `You have reached the agent limit. Ask an owner to raise it.`
- Both are plain strings rendered as React text (the existing XSS rule). `SignupForm` and `Agents` already show whatever message the helpers return; no component change beyond tests.

## 6. Failure table

| Case | Result |
|---|---|
| 6th valid sign-up from one address in a window | 429 `too_many_signups`, `Retry-After` > 0, no row |
| 51st valid sign-up overall in a window | 429, even from a fresh address |
| Invalid email / short password | 422, nothing counted |
| Sign-up closed | 403, nothing counted |
| Same email twice | 201 then 409, both counted |
| Window ends | next attempt 201, count restarts at 1 |
| 11th agent by a viewer | 409 `too_many_agents` |
| 11th agent by the owner role or the token | 201 |
| Database down at `count_owned` | 503 (existing handler) |

## 7. Security notes

- The limiter holds addresses and counters only, never emails or passwords.
- `X-Forwarded-For` is ignored: a client could forge it to dodge the limit.
- Refusing before hashing keeps argon2 CPU out of the flood path.
- The quota is enforced in the API, not the UI; a direct API call hits the same 409.

## 8. Test seams (for /spec-plan)

- Unit: `SignupLimiter` with a fake clock (AC-1…AC-4, AC-8, AC-9 and "refused attempts are free"), `agent_quota_reached`, sign-up route with a fake store/hasher and a tiny limiter (AC-5, AC-6, AC-7), admin router quota with the in-memory fakes (AC-11…AC-13), `Settings` defaults.
- Integration (Docker, `side_db`): sign-up with the real app and different peer addresses through `TestClient(app, client=(host, port))`; the quota with real counts.
- Web: `messages.test.ts` additions, `SignupForm.test.tsx` and `Agents.test.tsx` cases.
- Config: `make config-python`.
