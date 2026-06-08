# OpenCode MCP Invocation

Use OpenCode's configured MCP tool invocation path. Do not handcraft HTTP calls unless the user explicitly asks to debug transport.

## Invocation Shape

Represent every MCP call internally as:

```json
{
  "tool": "queryFlightBasic",
  "arguments": {
    "departureCity": "Beijing",
    "arrivalCity": "Shanghai",
    "departureDate": "2026-06-10"
  }
}
```

Let the OpenCode execution engine convert this to the actual MCP request. Keep tokens, headers, and auth outside prompts and output.

## Before Calling MCP

1. Build a normalized plan matching `schemas/booking-plan.schema.json`.
2. Run `scripts/normalize_request.py` if dates/cabin/time values need normalization.
3. Run `scripts/stage_guard.py` when current stage is available.
4. Pass only MCP-supported arguments. Do not include conversational explanations inside `arguments`.

## After Calling MCP

1. If the result is a flight list, run `scripts/compact_mcp_payload.py`.
2. Render only compact options unless the user asks for details.
3. Store or preserve `sessionId` in agent state.
4. Choose the next workflow file based on current task.

## Error Handling

Map MCP errors by intent:

- Invalid parameter: normalize or ask for the missing field.
- Access denied: stop booking and report permission issue.
- Missing session/context: requery with same session, or reset only after user confirms.
- Internal/network error: do not retry blindly more than once.

Do not expose raw auth tokens, full MCP envelopes, or large vendor payloads to the user.
