# ADR-0015: Heartbeat carries its own max age; topic creation moves to Python

Status: **Accepted 2026-10-06** (user accepted the recommended defaults at /spec-design externalize-config)

## Context
Compose cannot read the YAML, yet two compose items depend on config values: healthcheck windows (`find /tmp/healthy -mmin -20|-2`) are tied to the poll and loop intervals, and `create-topics.sh` repeats the topic names. If intervals or topic names become configurable, these silently break or drift (spec risk 3).

## Options
**Healthcheck:** (a) template compose from the YAML with a pre-step; (b) compose reads extra `.env` variables, duplicating the values; (c) **the worker writes its own allowed age into the heartbeat file, and a small per-app `healthcheck` module compares file age to it**.
**Topics:** (a) shell script reading generated env; (b) **Python AdminClient job, using the processor image and the same settings**.

## Decision
(c) and (b). The healthcheck cannot disagree with the loop that writes the heartbeat, and compose holds no config values. The topic job uses the same `Settings` as the processor, so names, partitions and replication come from one place. Docker scheduling values (`interval`, `retries`, `start_period`) stay in compose. Host ports stay in `.env`; container ports are fixed.

## Consequences
+ No templating step, no second copy of any value. + Each healthcheck is unit-testable. − Healthcheck runs a Python interpreter every 30–60 s (small cost, same image). − `create-topics.sh` and the docs naming it (foundation design-detail, tasks, verify) become stale and are updated in the plan. − The topic job now needs the config file mounted, one more place the mount must be right.
