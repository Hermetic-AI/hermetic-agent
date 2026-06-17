# OpenCode MCP Invocation via MCPorter Bridge

Use the mcporter bridge as the MCP invocation path. The bridge is a local MCP server named `mcporter` registered in opencode config that proxies to the feihe-travel upstream. This avoids loading all 21 fh-travel tools directly into the LLM context.

## Tool Name Format

opencode prefixes local MCP server tools with `<server>_`. Combined with mcporter's own `<upstream>__<tool>` namespace, the final tool names are:

```
mcporter_feihe-travel__<nativeToolName>
```

Examples:
- `mcporter_feihe-travel__queryFlightBasic`
- `mcporter_feihe-travel__chooseFlight`
- `mcporter_feihe-travel__chooseCabin`

Do not use native tool names (`queryFlightBasic`) or old-style prefixed names (`feihe-travel_queryFlightBasic`). Only use the `mcporter_feihe-travel__*` format.

## Invocation Shape

Represent every MCP call internally as:

```json
{
  "tool": "mcporter_feihe-travel__queryFlightBasic",
  "arguments": {
    "departureCity": "北京",
    "arrivalCity": "上海",
    "departureDate": "2026-06-10"
  }
}
```

Let the OpenCode execution engine convert this to the actual MCP request. Keep tokens, headers, and auth outside prompts and output.

## Why MCPorter Bridge?

Without the bridge, fh-travel is loaded as a remote MCP server and all 21 tools appear in the LLM context at once — consuming tokens and polluting the tool list. The mcporter bridge:

1. Acts as a single local MCP server from opencode's perspective
2. Proxies to feihe-travel upstream with auth headers (`token: $env:FLIGHT_API_KEY`)
3. `allowedTools` in `work/mcp/mcporter.json` controls which tools are exposed
4. Per-scenario, on-demand tool loading is possible by editing `mcporter.json`

## Before Calling MCP

1. For a clear first search, call `mcporter_feihe-travel__queryFlightBasic` immediately after local
   date normalization. Do not call helper scripts or other tools first.
2. Build a normalized plan matching `schemas/booking-plan.schema.json` when the
   request is not a simple clear first search.
3. Run `scripts/normalize_request.py` only if dates/cabin/time values need
   normalization beyond obvious relative dates.
4. Run `scripts/stage_guard.py` when current stage is available and the next
   tool is uncertain.
5. Pass only MCP-supported arguments. Do not include conversational
   explanations inside `arguments`.

## After Calling MCP

1. If the result is a flight list, run `scripts/compact_mcp_payload.py`.
2. **MUST emit an `ask_user` call with `card_type: "FLIGHT_RESULT"` and populate `body.contentJson`** with the full flight list in AGUI v2 format (see SKILL.md "MANDATORY" section).
3. Render only compact options unless the user asks for details.
4. Store or preserve `sessionId` in agent state.
5. Choose the next workflow file based on current task.

## Error Handling

Map MCP errors by intent:

- Invalid parameter: normalize or ask for the missing field.
- Access denied: stop booking and report permission issue.
- Missing session/context: requery with same session, or reset only after user confirms.
- Internal/network error: do not retry blindly more than once.
- mcporter bridge unavailable: report MCP connection failure, suggest checking `work/mcp/mcporter.json` and container environment.
- Any connection/network/timeout error on `mcporter_feihe-travel__*` calls: **do NOT fall back to `webfetch`, `curl`, Bash HTTP, or any direct HTTP call**. Emit `ask_user` with `card_type=CANNOT_ORDER`, Chinese `reason`, and `fallback`. See `workflows/intent-and-permission.md`.

Do not expose raw auth tokens, full MCP envelopes, or large vendor payloads to the user.