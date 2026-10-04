# ADR-0001: Plain Python processor instead of Flink

Status: **Accepted 2026-10-04** (user decision; supersedes the earlier Flink 2.2 mini-cluster proposal and spec D-5 "PyFlink")

## Context
The user does not use Flink and it would sharply raise the learning curve. Volume is ~350–530 rows per 15-min slot, so Flink adds no throughput value. Also, Flink 2.3 had no Kafka connector yet **[verified 2026-10-04]**.

## Options
1. Plain Python consumer/producer (`confluent-kafka`) with the same topic contract.
2. PyFlink 2.2.x mini-cluster (previous proposal).

## Decision
Option 1. The processor is stateless: parse, validate, route to `gkg.clean` / `gkg.dlq`. Dedup moves to the Postgres write (ADR-0004).

## Consequences
+ No JVM/jars/version alignment; the learning focus stays on Kafka. − No stateful-streaming skill (Flink returns as backlog M4). − Spec D-5, AC-4 wording and glossary updated; the topic contract is unchanged so Flink can be slotted back in.
