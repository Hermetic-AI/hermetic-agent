// Barrel export for the service layer.
export { http, ApiError } from './http';
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
export { turnService } from './turn';
export type { SendResumeStreamOptions } from './turn';
export { scenarioService } from './scenarios';
export { skillsService } from './skills';
export { toolsService } from './tools';
export { poolService } from './pool';
export { systemService } from './system';
// P7: opencode 原生 question / todo
export { questionService } from './question';
export type { QuestionReplyRequest, QuestionListResponse } from './question';
export { todoService } from './todo';
export type { TodoListResponse } from './todo';
