# push-delivery — Verification

Date: 2026-10-14 · Spec: [spec.md](spec.md) · Tests: [tests.md](tests.md) · Verdict: **pass with follow-ups**

## Run summary (this session, after the last code change)

| Check | Result |
|---|---|
| `uv run pytest` (unit, all packages) | 366 passed, 1 failed: `test_check_layout::test_real_repo_passes`, only because the /loop harness writes `.claude/scheduled_tasks.lock` at the repo root (DR-1) |
| `make check` | ruff, ruff format, mypy (175 files), import-linter (4 contracts), `check_config`, web lint/format/types/tests (13) pass; only `layout-python` fails on that lock file (a copy without `.claude/` passed in the agent-platform verify) |
| `make test-infra` (all Docker scenes) | **107 passed**, exit 0 (run after the last code change; later edits were docs only) |
| Live stack (TC-14) | done 2026-10-14 on real GDELT data, details below |

## Acceptance criteria

| AC | TC | Result | Evidence |
|---|---|---|---|
| AC-1 create subscription | TC-1, TC-22 | pass | `test_subscriptions_api.py`; persistence in `test_subscriptions_repo.py`; live: two subscriptions created and still listed after an API restart |
| AC-2 invalid filters rejected | TC-2, TC-16 | pass | `test_subscriptions.py` (10 invalid cases), `test_subscriptions_api.py` (422 and 409 cap) |
| AC-3 only own subscriptions | TC-3 | pass | list scoped (`test_list_and_delete_are_scoped_to_the_owner`), stream of another agent's id → 404 (`test_other_agents_subscription_is_404`) |
| AC-4 delete only own | TC-4 | pass | same unit test (204 / 404, row remains) |
| AC-5 stream needs a valid key | TC-5 | pass | `test_stream_needs_a_valid_key` (no key, junk, unknown, revoked → 401) |
| AC-6 matching pushed | TC-6, TC-17, TC-18, TC-19, TC-20 | pass | `test_matching_articles_are_pushed…` (via NOTIFY with a 60 s fallback), trigger/listener/filter tests; live: 266 events |
| AC-7 non-matching not pushed | TC-7, TC-18 | pass | same test (other.org skipped); live: the unrelated stream stayed silent |
| AC-8 resume | TC-8 | pass | `test_resume_with_last_event_id` (exactly the missed two, malformed → 400); live: resume after first id → 265, after last id → 0 |
| AC-9 default start | TC-9 | pass | `test_default_start_and_cursor_untouched` (after stored cursor / first-run window) |
| AC-10 cursor not moved | TC-10 | pass | same test; live: no cursor row created for the streaming agent |
| AC-11 revocation ends stream | TC-11 | pass | `test_revoking_the_key_ends_the_stream`, `test_deleting_the_subscription…`, `test_revocation_is_noticed_under_constant_traffic` |
| AC-12 keep-alive | TC-12 | pass | `test_idle_streams_get_keepalive_pings`; live: 3 pings in 50 s |
| AC-13 stream cap | TC-13 | pass | `test_streams.py` + `test_stream_cap_per_agent` (429 + Retry-After, other agent fine, slot freed) |
| AC-14 live push | TC-14 | manual-ok | below |
| AC-15 admin list | TC-15 | pass | `test_admin_lists_all_subscriptions_with_agent_names` (200 / 403 / 401, 404 without a token) |

### TC-14 live evidence
Stack: compose `--profile apps` with migration 0005, real GDELT, subscriptions `ECON_*` and `{"domain":"nonexistent.invalid"}` open via `curl -N`. The ingester published slot 20261014134500 (1,440 rows): the ECON_* stream received **266 events with 266 distinct article ids, equal to the 266 ECON_ rows stored in that window** (each with `id:`, `event: article`, summary JSON); the other stream got none. Idle pings, resume (265 / 0 / 400), subscriptions surviving an API restart (open streams dropped and reconnected cleanly), untouched agent cursor: all as specified.

## Measurements (provisional targets, not pass/fail)

| What | Measured |
|---|---|
| Delivery latency (insert → event) | 50 samples through a live app with a 60 s fallback poll (so via NOTIFY): median **12 ms**, p95 18 ms, max 20 ms |
| Keep-alive interval | 15 s default held a live idle stream open and visible to curl; sampled 50 s |
| Fallback poll after a lost listener | killed listener connection: delivery within the 8 s test window (reconnect backoff 1 s wakes everyone); a full outage falls back to the 30 s poll (not forced longer) |
| Query cost per wake-up | `EXPLAIN ANALYZE` on 4,780 articles: filtered prefix + domain `seq`-ordered query 0.10 ms, plain `seq > n` 0.02 ms (index range scan) |
| Caps | 5 streams and 20 subscriptions per agent were enough for the demo; kept as defaults |

## Doc drift

Fixed in this run: `design-detail.md` §2 and the failure table (the key re-check runs on a timer, not only on quiet ticks, found in the live run); ADR-0018 replaced the polling draft (which was deleted) and is Accepted; README, `CLAUDE.md`, roadmap updated in T-08.
Open (accepted): `docs/specs/mvp/design.md` still describes polling for the agent (M1 record).

## Scope

Nothing from `backlog.md` leaked in (no webhook, no MCP notifications, no demo-agent-on-push, no UI, no richer filters). Beyond the spec but required by the tasks: UUID-shape guard making malformed admin ids 404 instead of a database error (an agent-platform bug found in T-03).

## Findings during implementation (all fixed)

1. Malformed uuid in admin routes returned a database error (T-03).
2. The revoked-key re-check could be starved by steady NOTIFY wake-ups (T-08), regression test added.

## Follow-ups (in backlog)

1. Webhook and MCP-notification channels, demo agent consuming the stream (already P2).
2. Reads stay open until `ui-login` (agent-platform D-7).
3. `.claude/` lock vs layout rule DR-1 (agent-platform follow-up).
4. A subscription cap of 20 with a hard 409 is a default I chose (design checklist R-1); change if you prefer another behaviour.
