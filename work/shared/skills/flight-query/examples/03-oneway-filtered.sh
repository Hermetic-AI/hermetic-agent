#!/usr/bin/env bash
# ============================================================================
# 03-oneway-filtered.sh — 单程 · 多维筛选
# ----------------------------------------------------------------------------
# 场景: 用户说 "明天北京到上海,只要东航上午走的,经济舱,含行李,按价格排"
# 真实样本: tools/samples/queryFlightBasic.北京-上海.oneway.filtered.json
#   - 真实结果 filteredCount=0 (东航上午+含行李无符合)
#   - flightList=[] 但 citys/airways/types/cityWeatherList 字典照旧返
#   - LLM 处置: 提示用户放宽条件
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
          "departureCity":   "北京",
          "arrivalCity":     "上海",
          "departureDate":   "2026-06-05",
          "cabinClass":      "ECONOMY",
          "baggage":         true,
          "airlineName":     "东航",
          "departureDayPart":"MORNING",
          "sortBy":          "PRICE"
        }
      }
  }' | python -c "import sys,json; d=json.load(sys.stdin); t=json.loads(d['result']['content'][0]['text']); print(f\"filtered={t['filteredCount']} flightList=[]  -> 提示用户放宽条件\")"
