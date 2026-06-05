// ChatEvent 时间线操作 — useChatStream 用.
// 把同类事件合并 + 工具调用/结果配对的逻辑集中在这里, 别处不直接动 events[].

import type { ChatEvent } from '../types';

/** 给新事件生成唯一 id. */
export function newEventId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/**
 * 追加一个 text / reasoning 事件.  若末尾已是同类型, **合并** content —
 * 这是流式 markdown / 思考过程必要的, 否则 N 个 text chunk 会变 N 个气泡.
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

/** 新增 tool call (phase='call').  配套的 tool_result 会用 updateToolResult 配对. */
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
 * 把对应 tool_use 的 result 写进最后一个同名的 call 事件.
 * 若没找到 call, 降级为追加一个孤儿 result 事件 (不影响渲染, 调试可见).
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

export function appendCard(
  events: ChatEvent[],
  card: import('../types').CardView,
): ChatEvent[] {
  return [
    ...events,
    {
      type: 'card',
      id: newEventId('evt-card'),
      card: card.card,
      correlationId: card.correlation_id,
      at: new Date().toISOString(),
    },
  ];
}

/** 把最近一张匹配 card_id 的 card 事件标记为 suspended (suspend 事件触发). */
export function suspendCard(events: ChatEvent[], cardId: string): ChatEvent[] {
  return events.map((e) =>
    e.type === 'card' && e.card.card_id === cardId ? { ...e, suspended: true } : e,
  );
}

export function appendState(
  events: ChatEvent[],
  state: string,
  note: string | undefined,
  at: string,
): ChatEvent[] {
  return [...events, { type: 'state', id: newEventId('evt-st'), state, note, at }];
}

export function appendQuestion(
  events: ChatEvent[],
  payload: {
    requestId: string;
    sessionId: string;
    questions: import('../types').QuestionItem[];
  },
  at: string,
): ChatEvent[] {
  return [
    ...events,
    {
      type: 'question',
      id: newEventId('evt-q'),
      requestId: payload.requestId,
      sessionId: payload.sessionId,
      questions: payload.questions,
      at,
    },
  ];
}

export function markQuestionSubmitted(events: ChatEvent[], requestId: string): ChatEvent[] {
  return events.map((e) =>
    e.type === 'question' && e.requestId === requestId ? { ...e, submitted: true } : e,
  );
}

export function markQuestionRejected(events: ChatEvent[], requestId: string): ChatEvent[] {
  return events.map((e) =>
    e.type === 'question' && e.requestId === requestId ? { ...e, rejected: true } : e,
  );
}

/**
 * 渲染时把 events[] 折成"同类型相邻合并"后的组.
 * 同一组的事件在 UI 上当成一个块 (例如 100 个 text chunk → 1 个 text 段).
 */
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
