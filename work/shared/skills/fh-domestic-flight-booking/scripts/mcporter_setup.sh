#!/bin/bash
# Setup script for FH domestic flight booking MCP via mcporter CLI
#
# Registers feihe-travel as an MCP server in mcporter's home config,
# then verifies connectivity by listing available tools.
#
# Environment: FLIGHT_API_KEY must be set (injected by container env).

set -e

echo "[setup] Configuring mcporter for feihe-travel MCP..."

if ! command -v mcporter &> /dev/null; then
    echo "[setup] mcporter not found, installing..."
    npm install -g mcporter@latest
    echo "[setup] mcporter installed: $(mcporter --version)"
fi

# Register feihe-travel MCP server (Streamable HTTP transport)
# --transport http: use Streamable HTTP (not SSE) — feihe's endpoint returns application/json
# --scope home: write to ~/.mcporter/mcporter.json (tmpfs in container)
# --header "token=...": auth header for feihe MCP API
if [ -z "${FLIGHT_API_KEY:-}" ]; then
    echo "[setup] WARN: FLIGHT_API_KEY is empty; feihe-travel API calls will fail with auth error"
fi

mcporter config add feihe-travel "https://traveldev.feiheair.com/api/mcp" \
    --header "token=${FLIGHT_API_KEY:-}" \
    --transport http \
    --scope home

echo "[setup] Verifying mcporter configuration..."
if mcporter list 2>&1 | grep -q "feihe-travel"; then
    echo "[setup] OK: feihe-travel registered in mcporter"
    mcporter list | grep -A 1 "feihe-travel" || true
else
    echo "[setup] WARN: feihe-travel not found in mcporter list"
    echo "[setup]   running 'mcporter list' output:"
    mcporter list 2>&1 || true
    echo "[setup]   continuing — tool calls will fail until this is resolved"
fi

echo "[setup] Done."