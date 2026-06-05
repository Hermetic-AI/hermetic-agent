#!/usr/bin/env bash
# ============================================================================
# 01-oneway-full.sh — 单程 · 全量
# ----------------------------------------------------------------------------
# 场景: 用户说 "明天北京到上海,看看有哪些航班" (无 cheapest / 舱等 / 排序)
# 真实样本: tools/samples/queryFlightBasic.北京-上海.oneway.full.json (193 航班)
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
          "departureCity": "北京",
          "arrivalCity":   "上海",
          "departureDate": "2026-06-05"
        }
      }
  }' | python -c "import sys,json; d=json.load(sys.stdin); t=json.loads(d['result']['content'][0]['text']); print(f\"serial={t['serialNumber']} searchType={t['searchType']} flightCount={t['flightCount']} filtered={t['filteredCount']} top5=\"); [print(f\"  {f['serialNo']:>3} {f['flightNo']:<7} {f['legs'][0]['airlineName']:<6} {f['depAirportCode']} {f['legs'][0]['depTime']} -> {f['arrAirportCode']} {f['legs'][0]['arrTime']}  ¥{f['lowestPrice']}\") for f in t['flightList'][:5]]"
