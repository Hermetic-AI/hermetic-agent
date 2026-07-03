// useWorkPanel — subscribes to a shared SSE source and accumulates TraceEvents.
//
// Designed to share a StreamSource with useChatStream: both consume the same
// `/agent/chat/stream` SSE feed via independent AsyncIterables, so the network
// is hit once per chat turn regardless of how many panels observe it.

import { useEffect, useRef, useState } from 'react';
import type { StreamSource, StreamEvent } from '../types';

export type TraceKind =
  | 'tool_io'
  | 'state'
  | 'todo'
  | 'question'
  | 'scenario'
  | 'card'
  | 'suspend'
  | 'product'
  | 'error';

export interface TraceEvent {
  seq: number;
  at: string;
  kind: TraceKind;
  payload: Record<string, unknown>;
}

const TRACE_KINDS: ReadonlySet<TraceKind> = new Set<TraceKind>([
  'tool_io', 'state', 'todo', 'question', 'scenario',
  'card', 'suspend', 'product', 'error',
]);

export function useWorkPanel(
  source: StreamSource | null,
  signal?: AbortSignal,
): TraceEvent[] {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const seqRef = useRef(0);
  const resetKeyRef = useRef<symbol | null>(null);

  // Reset events when the source changes (e.g., new turn started).
  useEffect(() => {
    if (!source) {
      setEvents([]);
      seqRef.current = 0;
      return;
    }
    resetKeyRef.current = Symbol('source');
    setEvents([]);
    seqRef.current = 0;
  }, [source]);

  useEffect(() => {
    if (!source) return;
    let cancelled = false;
    const token = resetKeyRef.current;

    (async () => {
      try {
        for await (const ev of source.attach(signal)) {
          if (cancelled || token !== resetKeyRef.current) break;
          const traceEv = adaptEvent(ev, seqRef);
          if (traceEv) {
            setEvents((prev) => [...prev, traceEv]);
          }
        }
      } catch {
        // Stream errors are surfaced via useChatStream; keep silent here.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [source, signal]);

  return events;
}

function adaptEvent(ev: StreamEvent, seqRef: React.MutableRefObject<number>): TraceEvent | null {
  const k = ev.type as TraceKind;
  if (!TRACE_KINDS.has(k)) return null;
  const payload = (ev.data ?? {}) as Record<string, unknown>;
  return {
    seq: seqRef.current++,
    at: new Date().toISOString(),
    kind: k,
    payload,
  };
}