# ADR-0023: Agent ownership is enforced by a required scope argument in the repos

Status: **Accepted 2026-10-28** (user chose the repo-level scope at `/spec-design agent-ownership`; also confirmed: 409 for a taken name, creator email shown to the owner role only, owner-created agents are owned by their creator, `/api/admin/*` paths kept)

## Context
Agents had no creator, so every admin and owner saw and managed every agent. The `agent-ownership` spec records a creator per agent and applies one rule: a user sees and manages only their own agents and subscriptions, the `owner` role (and the admin token) see all. Every signed-in role may now use the agent routes, so a missed check becomes a cross-user leak. Where should the rule live?

## Options
1. **Required `scope` argument in the repos** (chosen proposal): `scope_for(principal)` is a pure domain function; every repo method that reads or writes agents or subscriptions takes it and applies it in the same SQL statement. A route cannot skip it without a type error.
2. **Check in each route:** load the agent, compare `owner_id`, then act. Simple to read, but a forgotten check or a time-of-check/time-of-use gap leaks data, and each route does two queries.
3. **Postgres row-level security** with a per-request `SET` of the current user: strongest guarantee, but it needs a session variable on every pooled connection, a second DB role split, and cannot express the "owner sees all, token sees all" rule without extra policy code. Heavy for a one-service local project.

## Decision
Option 1. `agents.owner_id` is a nullable FK to `users.id` with `ON DELETE SET NULL`, so agents outlive their creator as ownerless agents that only the `owner` role and the admin token can manage. Foreign, ownerless (to non-owners) and unknown ids all answer 404. `manage_agents` is held by every role. The agent-facing paths (`/mcp`, `/api/subscriptions*`) keep their key-based resolver and never use the scope.

## Consequences
+ Isolation is enforced in one place and in one statement per operation; fakes in unit tests must honour the scope, which makes the contract testable. + Additive migration; running agents see no change.
− Every future agent or subscription query must take a scope, which is a small ceremony. − The repo protocols and their fakes change. − Name uniqueness stays global, so a taken name is a 409 that reveals the name exists (spec D-8). − Postgres row-level security remains an option if the project later runs more than one service against the same tables.
− Amends ADR-0016 and ADR-0020 (who may use the agent routes and what `manage_agents` means); those ADRs get a dated amendment line when this one is accepted.
