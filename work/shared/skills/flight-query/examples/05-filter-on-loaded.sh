#!/usr/bin/env bash
# ============================================================================
# 05-filter-on-loaded.sh — filterFlightList 内存二次筛选
# ----------------------------------------------------------------------------
# 场景: 用户在已加载的航班列表上,追加 "只要大飞机的 / 飞行时长 ≤ 2 小时"
#   - TMS 不支持这两个维度(planeSize / maxDuration)
#   - 走 filterFlightList, 不重调 TMS
#   - 用 queryFlightBasic 返的 serialNumber 作 sessionId
#
# ⚠️ 真实样本: 当前 MCP 端未在 queryFlightBasic 返 flightId/cabId 时暴露独立 sessionId,
#    用 serialNumber 兜底(实际接入前确认 sessionId 来源 — 查 tools/flight-mcp.json 的
#    filterFlightList.inputSchema.required)
# ============================================================================
set -euo pipefail

: "${MCP_TOKEN:?Set MCP_TOKEN env var (do NOT commit a real token)}"
: "${SESSION_ID:?Set SESSION_ID env var (use serialNumber from previous queryFlightBasic response)}"

ENDPOINT='https://traveldev.feiheair.com/api/mcp'

curl -s --location --request POST "${ENDPOINT}" \
  --header 'Accept: application/json,text/event-stream' \
  --header "Authorization: Bearer ${MCP_TOKEN}" \
  --header 'Content-Type: application/json' \
  --data-raw '{
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "filterFlightList",
        "arguments": {
          "sessionId":    "'"${SESSION_ID}"'",
          "planeSize":    "大",
          "maxDuration":  120
        }
      }
  }' | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['result'], ensure_ascii=False, indent=2)[:1500])"
