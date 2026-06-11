#!/usr/bin/env bash
# ============================================================================
# 04-roundtrip-recommended.sh — 往返 · 推荐 (RECOMMENDED)
# ----------------------------------------------------------------------------
# 场景: 用户说 "6 月 8 号北京到上海,13 号回"
# 真实样本: tools/samples/queryFlightBasic.北京-上海.roundtrip.recommended.json
#   - 真实结果 isError=true, text="请求航信超时" (TMS 上游超时)
#   - LLM 处置: 按 errorMsg 提示用户,建议稍后重试
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
          "departureDate": "2026-06-08",
          "returnDate":    "2026-06-13"
        }
      }
  }' | python -c "import sys,json; d=json.load(sys.stdin); r=d['result']; print(f\"isError={r.get('isError')}  text={r['content'][0]['text']}\")"
