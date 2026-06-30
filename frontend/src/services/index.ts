// Barrel export for the service layer.
export { http, ApiError, registerTokenGetter, resolveAuthToken } from './http';
export { parseSSE } from './sse';
export { chatService, buildStreamUrl, buildStreamHeaders, joinUrl } from './chat';
export type {
  ChatRequest,
  ChatResponse,
  ChatSyncResult,
  ChatToolCall,
  SendStreamOptions,
} from './chat';
export { sessionService } from './session';
export type {
  CreateSessionRequest,
  CreateSessionResponse,
  SessionMessagesResponse,
  DeleteSessionResponse,
} from './session';
export { poolService } from './pool';
export { systemService } from './system';