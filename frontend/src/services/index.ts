// Barrel export for the service layer.
export { http, ApiError } from './http';
export { parseSSE } from './sse';
export { chatService } from './chat';
export type { ChatRequest, ChatResponse, ChatSyncResult, ChatToolCall, SendStreamOptions } from './chat';
export { sessionService } from './session';
export type { CreateSessionRequest, CreateSessionResponse, SessionMessagesResponse, DeleteSessionResponse } from './session';
export { skillsService } from './skills';
export { toolsService } from './tools';
export { poolService } from './pool';
export { systemService } from './system';
