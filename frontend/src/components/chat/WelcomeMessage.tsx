import type { ChatMessage } from '../../types';
import { ChatBubble } from './ChatBubble';
import './WelcomeMessage.css';

interface WelcomeMessageProps {
  onQuickReply: (value: string) => void;
  backendReady?: boolean;
  scenarioLabel?: string;
}

export function WelcomeMessage({ onQuickReply, backendReady = true, scenarioLabel }: WelcomeMessageProps) {
  const isFlight = scenarioLabel === 'flight_query' || scenarioLabel === 'flight_booking';
  const isBooking = scenarioLabel === 'flight_booking';
  const isGeneric = !scenarioLabel;

  const content = backendReady
    ? scenarioLabel
      ? welcomeForScenario(scenarioLabel, isBooking)
      : welcomeGeneric()
    : '您好！我是您的差旅助手。\n\n当前无法连接后端服务，请检查服务是否已启动（默认 http://localhost:8000）。';

  const quickReplies = !backendReady
    ? [{ label: '差旅规则', value: '差旅规则是什么' }]
    : isBooking
      ? [
          { label: '订机票', value: '帮我订明天北京到上海的经济舱' },
          { label: '查航班', value: '帮我查下周二上海到深圳的航班' },
          { label: '差旅规则', value: '差旅规则是什么' },
        ]
      : isFlight
        ? [
            { label: '查机票', value: '帮我查一下北京到上海的机票' },
            { label: '看订单', value: '查看我的订单' },
            { label: '差旅规则', value: '差旅规则是什么' },
          ]
        : isGeneric
          ? [
              { label: '查机票', value: '帮我查一下北京到上海的机票' },
              { label: '看订单', value: '查看我的订单' },
              { label: '差旅规则', value: '差旅规则是什么' },
            ]
          : [];

  const welcomeMsg: ChatMessage = {
    id: 'welcome',
    role: 'assistant',
    content,
    timestamp: new Date().toISOString(),
    quickReplies,
  };

  return (
    <div className="welcome-container">
      <div className="welcome-header">
        <div className="welcome-avatar">
          <AIIcon />
        </div>
        <div className="welcome-info">
          <h2>{scenarioLabel ? `${scenarioLabel} 助手` : '差旅AI助手'}</h2>
          <p>{isFlight ? '7×24小时为您查询 / 预订机票' : '7×24小时为您服务'}</p>
        </div>
      </div>
      <div className="welcome-bubble">
        <ChatBubble message={welcomeMsg} onQuickReply={onQuickReply} />
      </div>
    </div>
  );
}

function welcomeGeneric(): string {
  return '您好！我是您的差旅助手。我可以帮您：\n• 查询和预订机票、火车票、酒店\n• 管理您的差旅订单\n• 查看差旅规则和费用标准\n• 智能推荐最合适的出行方案';
}

function welcomeForScenario(label: string, isBooking: boolean): string {
  if (isBooking) {
    return `您好！我是飞鹤差旅 AI 助手 — 机票预订专责。\n• 帮我订 ${new Date().toISOString().slice(0, 10)} 北京到上海的经济舱\n• 严格遵守公司差标, 关键节点会主动向您确认\n• 可预订国际机票, 提前 7 天起`;
  }
  if (label === 'flight_query') {
    return `您好！我是飞鹤差旅 AI 助手 — 机票查询专责。\n• 用城市名查 (例: "北京到上海明天的航班")\n• 支持筛选舱位、航司、起飞时段\n• 不下订单, 只返回可订航班信息`;
  }
  return `您好！我是 ${label} 助手, 请问有什么可以帮您?`;
}

function AIIcon() {
  return (
    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#0051A1" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 6v6l4 2" />
    </svg>
  );
}
