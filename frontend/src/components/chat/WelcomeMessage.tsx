import type { ChatMessage } from '../types';
import { ChatBubble } from './ChatBubble';
import './WelcomeMessage.css';

interface WelcomeMessageProps {
  onQuickReply: (value: string) => void;
  backendReady?: boolean;
}

export function WelcomeMessage({ onQuickReply, backendReady = true }: WelcomeMessageProps) {
  const welcomeMsg: ChatMessage = {
    id: 'welcome',
    role: 'assistant',
    content: backendReady
      ? '您好！我是您的差旅助手。我可以帮您：\n• 查询和预订机票、火车票、酒店\n• 管理您的差旅订单\n• 查看差旅规则和费用标准\n• 智能推荐最合适的出行方案'
      : '您好！我是您的差旅助手。\n\n当前无法连接后端服务，请检查服务是否已启动（默认 http://localhost:8000）。',
    timestamp: new Date().toISOString(),
    quickReplies: backendReady
      ? [
          { label: '查机票', value: '帮我查一下北京到上海的机票' },
          { label: '看订单', value: '查看我的订单' },
          { label: '差旅规则', value: '差旅规则是什么' },
        ]
      : [
          { label: '差旅规则', value: '差旅规则是什么' },
        ],
  };

  return (
    <div className="welcome-container">
      <div className="welcome-header">
        <div className="welcome-avatar">
          <AIIcon />
        </div>
        <div className="welcome-info">
          <h2>差旅AI助手</h2>
          <p>7×24小时为您服务</p>
        </div>
      </div>
      <div className="welcome-bubble">
        <ChatBubble message={welcomeMsg} onQuickReply={onQuickReply} />
      </div>
    </div>
  );
}

function AIIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#0051A1" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}
