// ActivityFeed — scrolling list of TraceEvents (one row per tool call, state
// transition, todo update, etc.).  Designed for terminal-style right-side
// panel: auto-scrolls to bottom, monospace font, ANSI-style background per
// event kind.

import type { TraceEvent } from '../../hooks/useWorkPanel';
import './ActivityFeed.css';

export interface ActivityFeedProps {
  events: TraceEvent[];
}

export function ActivityFeed({ events }: ActivityFeedProps) {
  if (events.length === 0) {
    return (
      <div className="activity-feed activity-feed-empty">
        No activity yet — send a message to start.
      </div>
    );
  }
  return (
    <ol className="activity-feed">
      {events.map((ev) => (
        <ActivityRow key={ev.seq} event={ev} />
      ))}
    </ol>
  );
}

function ActivityRow({ event }: { event: TraceEvent }) {
  const summary = summarize(event);
  return (
    <li className={`activity-row activity-${event.kind}`}>
      <div className="activity-row-header">
        <span className={`activity-kind activity-kind-${event.kind}`}>{event.kind}</span>
        <time className="activity-time">{formatTime(event.at)}</time>
      </div>
      <div className="activity-row-body">
        <code className="activity-summary">{summary}</code>
      </div>
    </li>
  );
}

function summarize(ev: TraceEvent): string {
  const p = ev.payload;
  switch (ev.kind) {
    case 'tool_io': {
      const phase = (p.phase as string | undefined) ?? '?';
      const name = (p.name as string | undefined) ?? '?';
      return phase === 'call'
        ? `→ ${name}(${stringifyShort(p.input)})`
        : `← ${name} ${truncate(p.output_redacted as string | undefined, 80)}`;
    }
    case 'state':
      return `${p.from as string} → ${p.to as string}`;
    case 'todo':
      return `todos: ${(p.items as unknown[] | undefined)?.length ?? 0} items`;
    case 'question':
      return `Q: ${stringifyShort(p.prompt)}`;
    case 'scenario':
      return `scenario: ${p.name as string}`;
    case 'card':
      return `card: ${p.card_type as string} (${p.card_id as string})`;
    case 'suspend':
      return `suspend @ ${p.checkpoint_id as string}`;
    case 'product':
      return `product: ${p.kind as string} ${p.path as string ?? p.url as string ?? ''}`;
    case 'error':
      return `[${p.code as string}] ${p.message as string}`;
    default:
      return JSON.stringify(p);
  }
}

function stringifyShort(v: unknown, max = 60): string {
  if (v == null) return '';
  const s = typeof v === 'string' ? v : JSON.stringify(v);
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function truncate(v: string | undefined, max: number): string {
  if (!v) return '';
  return v.length > max ? `${v.slice(0, max)}…` : v;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return iso;
  }
}