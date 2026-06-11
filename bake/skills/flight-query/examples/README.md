# `examples/` — 真实可跑的 curl 模板

> **本目录是 skill 自包含的** — LLM / 开发人员可直接复制,把 `${MCP_TOKEN}` 换成实际值即可跑。
> 调通前提:
> 1. 已有有效 MCP token(从 `X-MCP-Token` header 拿,或在 OpenAgent 对话里由 system_prompt 注入)
> 2. `jq` / `python` 装好(用来解 `result.content[0].text` 的二次 JSON 字符串)
> 3. 服务端 MCP 正常(2026-06-04 实测可用)

## 5 个模板

| 文件 | 场景 | 真实样本 | 用法 |
|---|---|---|---|
| `01-oneway-full.sh` | 单程 · 全量(无筛选) | `tools/samples/...oneway.full.json` (193 航班) | `MCP_TOKEN=... bash 01-oneway-full.sh` |
| `02-oneway-cheapest.sh` | 单程 · 最便宜 | `tools/samples/...oneway.cheapest.json` (服务端推 searchType=经济舱最低价) | 同上 |
| `03-oneway-filtered.sh` | 单程 · 多维筛选(舱等+行李+航司+时段+排序) | `tools/samples/...oneway.filtered.json` (filteredCount=0 演示空结果) | 同上 |
| `04-roundtrip-recommended.sh` | 往返 · RECOMMENDED | `tools/samples/...roundtrip.recommended.json` (isError=true 演示业务错误) | 同上 |
| `05-filter-on-loaded.sh` | filterFlightList 内存二次筛选(planeSize/maxDuration) | 暂无 | `MCP_TOKEN=... SESSION_ID=... bash 05-filter-on-loaded.sh` |

## 与 skill 的对应

- `01-04` 调主工具 `queryFlightBasic`
- `05` 调次工具 `filterFlightList`(需先调 `01` 拿 `serialNumber` 作 `sessionId`)
- 对应 use case 见 `flight-query:query_flight_basic` §6

## ⚠️ 已知问题(2026-06-04)

- `filterFlightList` 的 `sessionId` 来源 — 实际接入时需确认:
  - 是 `queryFlightBasic.返回.serialNumber`?
  - 还是 MCP 端独立给个 `sessionId`?
  - **本 skill 当前用 `serialNumber` 兜底,等真实接入后修正**
- `MCP_TOKEN` **不**进 git;生产路径是 OpenAgent 注入到 system_prompt,LLM 自己取
