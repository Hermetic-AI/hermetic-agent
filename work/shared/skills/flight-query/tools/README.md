# `tools/flight-mcp.json` — Provenance & Refresh

> **这个目录是 skill 自包含的,工具接口源在 skill 内部。**

## 文件来源

| 项 | 值 |
|---|---|
| 本文件 | `tools/flight-mcp.json`(MCP `tools/list` 响应的整包,JSON-RPC 2.0 envelope 原样保留) |
| 源快照 | `docs/api/mcp-response-0604.json`(项目级历史快照) |
| 抓取时间 | 2026-06-04 |
| 抓取人 | 手动 curl |

> **本文件是 skill 的运行时权威源**;`docs/api/mcp-response-0604.json` 仅作历史归档,
> 不应再被 SKILL.md / 子 skill 直接引用。

## 为什么不在 SKILL.md 里

- SKILL.md = 行为契约、路由决策、铁律(LLM 必读)
- `tools/*.json` = 工具接口(LLM 按需 read)
- 二者分离:SKILL.md 不会随工具 schema 变动而膨胀,工具 schema 也不会污染 LLM 上下文

## 如何刷新

服务端改了 MCP 工具后:

```bash
# 1) 调 tools/list 拿最新响应(用占位 token,MCP 端 token 认证已通过即返回)
curl.exe -s --location --request POST 'https://traveldev.feiheair.com/api/mcp' \
  --header 'Accept: application/json,text/event-stream' \
  --header 'Authorization: Bearer ${MCP_TOKEN}' \
  --header 'Content-Type: application/json' \
  --data-raw '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  -o tools/flight-mcp.json

# 2) 同步归档快照(带日期)
cp tools/flight-mcp.json ../../../docs/api/mcp-response-$(date +%y%m%d).json

# 3) 跑 smoke 校验:本文件能 JSON parse + 含 15 个工具(已知)
python -c "import json; d=json.load(open('tools/flight-mcp.json',encoding='utf-8')); print(len(d['result']['tools']),'tools'); print([t['name'] for t in d['result']['tools']])"

# 4) 同步子 skill 的"实测/未实测"标记
#    - tools 数变了 → 改 flight-query/SKILL.md §3
#    - 任一工具的 inputSchema 字段变了 → 改对应子 skill 的 §2
#    - 改了 Bump 子 skill 版本号 + §7 changelog
```

## 已知问题(2026-06-04)

- MCP 端 `tools/list` 在 Spring 反序列化层有 bug,**偶发**返 HTTP 400 `Invalid message format`。
  本次抓取是手测多次后成功那次的响应。
- 修复后:抓新响应时**先打 1 次**确认不是 400,再覆盖。

## 引用约定

| 引用方 | 引哪个文件 |
|---|---|
| `flight-query/SKILL.md` §3 | `tools/flight-mcp.json`(相对 skill 根) |
| `flight-query.query_flight_basic/SKILL.md` §2 | `tools/flight-mcp.json` → `result.tools[?(@.name=="queryFlightBasic")].inputSchema` |
| `flight-query.filter_flight_list/SKILL.md`(待建) §2 | `tools/flight-mcp.json` → `result.tools[?(@.name=="filterFlightList")].inputSchema` |
| 任何 LLM 临时查 | 同上,直接 `jq` / `python -c "import json; ..."` 抽 |
