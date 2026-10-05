# ADR-0003: One API process serves MCP (streamable HTTP) and REST

Status: **Accepted 2026-10-04**

## Context
D-2: MCP + REST. Official `mcp` Python SDK is at 2.3.0 (2026-10-02), v1.30 legacy line still maintained; streamable HTTP is the deploy transport **[verified from PyPI page]**. v2 API/migration notes not read yet **[assumption]**.

## Options
1. One FastAPI app: REST routes plus MCP mounted at `/mcp`, shared service layer.
2. Two processes.
3. stdio MCP only.

## Decision
Option 1, `mcp>=2,<3`. If v2 proves awkward at implementation, drop to `mcp` 1.x with the same tool contract (tool names/schemas are the contract, not the SDK).

## Consequences
+ One DB role, one deploy, shared validation (AC-9 identical for UI and agents). − UI and agents share a failure domain; split later (backlog M6). − SDK major version risk.
