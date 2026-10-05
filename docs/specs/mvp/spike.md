# mvp — T-01 spike findings (2026-10-05)

Throwaway code lived in the session scratchpad; nothing committed. All claims below **[verified 2026-10-05]**.

## 1. `mcp` SDK v2 — confirmed, no 1.x fallback needed
- `mcp` **2.3.0**: hello-world round-trip ran (server + client, streamable HTTP, Python 3.12).
- Server pattern for C-6: `MCPServer("name")` + `@mcp.tool()`; mount into FastAPI with `app.mount("/", mcp.streamable_http_app())`; the host app's lifespan **must** enter `async with mcp.session_manager.run()` or requests fail with `RuntimeError: Task group is not initialized`. `/api/*` routes coexist fine; MCP endpoint lands at `/mcp`.
- Client: `async with Client(url) as c:` → `await c.list_tools()` (`.tools[].name`), `await c.call_tool(name, args)` → `.structured_content`.

## 2. Model choice (R-11): **llama3.2:3b** (user decision 2026-10-05)
Benchmark: 22 real titles from live slot `20261005131500`, Ollama 0.35.1, structured output (JSON schema), temperature 0, macOS arm64.

| Model | mean | median | p95 | malformed |
|---|---|---|---|---|
| **llama3.2:3b** | **1.37 s** | 1.27 s | 1.82 s | 0/22 |
| qwen3:4b-instruct | 3.51 s | 3.14 s | 3.86 s | 0/22 |
| llama3.2:1b (old prompt) | 0.75 s | 0.35 s | — | 6/22 |

- **Gotcha:** Ollama's structured output enforces JSON *shape*, not numeric bounds — without "decimal between 0.0 and 1.0" in the prompt, llama3.2:3b returned scores like `8.5` (3/22). With the range stated: 0 malformed. The agent must still validate/clamp (TC-29).

## 3. Throughput (R-2): keeps up, ~2× headroom
- Slot sizes vary more than sampled: 342 (10-04 07:15), 527 (10-04 08:15), **1210 rows** (10-05 13:15).
- Pre-filter measured on the 1210-row slot (prefix match on parsed V2 theme codes, V1 fallback): `ECON_` 277 (23 %) — matches the design's ~24 %; bare `WB_` 880 (**73 %**); either 75 %.
- **Design correction (user decision 2026-10-05): `AGENT_THEME_PREFIXES` defaults to `ECON_` only.** Bare `WB_` is the whole World Bank taxonomy, not finance, and would overwhelm the agent (75 % × 1210 × 1.37 s ≈ 21 min per 15-min slot). Curated WB finance codes can be added via config later.
- Budget check: 1210 × 23 % ≈ 280 scores × 1.37 s ≈ **6.4 min per 15-min slot** → fits with ~2× headroom.

## 4. Carried into
design.md §6 (model, mcp re-tag) · design-detail.md §2 agent loop (prefix default, prompt range note) · ADR-0003 (v2 confirmed).
