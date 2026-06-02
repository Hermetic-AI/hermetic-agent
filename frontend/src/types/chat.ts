// Re-exported chat types — the canonical home is `./domain`.
// Kept as a separate module so existing imports continue to work.

export type {
  ChatMessage,
  ChatAttachment,
  ChatRole,
  QuickReply,
  StreamEvent,
  StreamEventType,
  ToolEventView,
  ReasoningEventView,
} from './domain';
