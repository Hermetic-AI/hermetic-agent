// Chat event timeline helpers — useChatStream uses these.
// Only the generic event types (text / reasoning / tool) live here.

import type { ChatEvent } from '../types';

/** Generate a unique id for a new event. */
export function newEventId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * Append a text event.  If the tail is already a `text` event, **merge**
 * the content — otherwise N stream chunks would render as N bubbles.
 */
export function appendText(
  events: ChatEvent[],
  content: string,
  at: string,
): ChatEvent[] {
  if (!content) return events;
  const last = events[events.length - 1];
  if (last && last.type === 'text') {
    const merged: ChatEvent = { ...last, content: last.content + content, at };
    return [...events.slice(0, -1), merged];
  }
  return [...events, { type: 'text', id: newEventId('evt-text'), content, at }];
}

export function appendReasoning(
  events: ChatEvent[],
  content: string,
  at: string,
): ChatEvent[] {
  if (!content) return events;
  const last = events[events.length - 1];
  if (last && last.type === 'reasoning') {
    const merged: ChatEvent = { ...last, content: last.content + content, at };
    return [...events.slice(0, -1), merged];
  }
  return [...events, { type: 'reasoning', id: newEventId('evt-rsn'), content, at }];
}

/** New tool call (phase='call').  The matching result is paired via `updateToolResult`. */
export function appendToolCall(
  events: ChatEvent[],
  name: string,
  input: unknown,
  at: string,
): ChatEvent[] {
  return [
    ...events,
    {
      type: 'tool',
      id: newEventId('evt-tool'),
      name,
      phase: 'call',
      input,
      at,
    },
  ];
}

/**
 * Write the result onto the most recent matching tool call event.
 * If no call exists yet, append an orphan result (harmless, useful for debugging).
 */
export function updateToolResult(
  events: ChatEvent[],
  name: string,
  output: unknown,
): ChatEvent[] {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const e = events[i];
    if (e.type === 'tool' && e.name === name && e.phase === 'call') {
      const updated: ChatEvent = { ...e, phase: 'result', output };
      return [...events.slice(0, i), updated, ...events.slice(i + 1)];
    }
  }
  return [
    ...events,
    {
      type: 'tool',
      id: newEventId('evt-tool'),
      name,
      phase: 'result',
      output,
      at: new Date().toISOString(),
    },
  ];
}

/** Group adjacent events of the same type for rendering. */
export type ChatEventGroup<T extends ChatEvent = ChatEvent> = {
  type: T['type'];
  events: T[];
};

export function groupConsecutiveEvents(events: ChatEvent[]): ChatEventGroup[] {
  const groups: ChatEventGroup[] = [];
  for (const evt of events) {
    const last = groups[groups.length - 1];
    if (last && last.type === evt.type) {
      last.events.push(evt);
    } else {
      groups.push({ type: evt.type, events: [evt] });
    }
  }
  return groups;
}