// SSE (Server-Sent Events) stream parser.
//
// The backend's /agent/chat/stream emits a sequence of records in the form:
//   data: {"type": "text", "data": {"content": "..."}}
//   data: {"type": "done", "data": {}}
//   \n
//
// We parse those records into `StreamEvent` objects.  The body is
// decoded with ReadableStream + TextDecoder so we don't have to load
// the whole response into memory.
//
// Usage:
//   for await (const evt of parseSSE(response)) { ... }

import type { StreamEvent, StreamEventType } from '../types';

type PayloadMap = StreamEvent extends infer E
  ? E extends StreamEvent<infer T>
    ? T extends StreamEventType
      ? { [K in T]: StreamEvent<K>['data'] }
      : never
    : never
  : never;

function tryParseJson(line: string): unknown {
  if (!line) return null;
  try {
    return JSON.parse(line);
  } catch {
    return null;
  }
}

function isStreamEventShape(v: unknown): v is { type: string; data: unknown } {
  return (
    typeof v === 'object' &&
    v !== null &&
    'type' in v &&
    'data' in v &&
    typeof (v as { type: unknown }).type === 'string'
  );
}

/**
 * Parse an SSE response body into a sequence of `StreamEvent`.
 *
 * @param response  A `Response` whose `Content-Type` is `text/event-stream`.
 */
export async function* parseSSE(
  response: Response,
): AsyncGenerator<StreamEvent, void, undefined> {
  if (!response.body) {
    throw new Error('SSE response had no body');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE records are separated by a blank line.
      let sepIdx: number;
      // Normalise CRLF → LF to keep parsing predictable.
      buffer = buffer.replace(/\r\n/g, '\n');
      while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
        const record = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);
        const parsed = parseRecord(record);
        if (parsed) yield parsed;
      }
    }
    // Flush any trailing record (server may omit the final blank line).
    if (buffer.trim().length > 0) {
      const parsed = parseRecord(buffer);
      if (parsed) yield parsed;
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // ignore
    }
  }
}

function parseRecord(record: string): StreamEvent | null {
  // Each line in the record is either `field: value` or just `field:value`.
  // The only field we care about is `data:`.  `event:` and `id:` are ignored.
  const lines = record.split('\n');
  const dataLines: string[] = [];
  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith(':')) continue; // comment / heartbeat
    const colon = line.indexOf(':');
    if (colon === -1) continue;
    const field = line.slice(0, colon).trim();
    let value = line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'data') dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  const payload = tryParseJson(dataLines.join('\n'));
  if (!isStreamEventShape(payload)) return null;
  const type = payload.type as StreamEventType;
  const data = (payload.data ?? {}) as PayloadMap[typeof type];
  return { type, data } as StreamEvent;
}
