#!/usr/bin/env bash
# ============================================================================
# 02-oneway-cheapest.sh — 单程 · 最便宜
# ----------------------------------------------------------------------------
# 场景: 用户说 "明天上海到深圳,最便宜的"
# 真实样本: tools/samples/queryFlightBasic.上海-深圳.oneway.cheapest.json
#   - 服务端把 cheapest:true 推导为 searchType="经济舱最低价"
#   - filteredCount=1 (只要 1 条)
# ============================================================================
set -euo pipefail

: "${MCP_TOKEN:?Set MCP_TOKEN env var (do NOT commit a real token)}"

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
        "name": "queryFlightBasic",
        "arguments": {
          "departureCity": "上海",
          "arrivalCity":   "深圳",
          "departureDate": "2026-06-05",
          "cheapest":      true
        }
      }
  }' | python -c "import sys,json; d=json.load(sys.stdin); t=json.loads(d['result']['content'][0]['text']); print(f\"searchType={t['searchType']} filtered={t['filteredCount']}\"); [print(f\"  {f['flightNo']} {f['legs'][0]['airlineName']} {f['legs'][0]['depTime']}->{f['legs'][0]['arrTime']}  ¥{f['lowestPrice']}  {f['lowestCabinName']}\") for f in t['flightList']]"
