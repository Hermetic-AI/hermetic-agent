import type { ReactNode } from 'react';
import type { CardDescriptor } from '../../types';
import './CardShell.css';

interface CardShellProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  children: ReactNode;
  footer?: ReactNode;
}

export function CardShell({ card, suspended, submitted, children, footer }: CardShellProps) {
  const title = card.title ?? card.message ?? defaultTitle(card.card_type);
  const cls = [
    'aui-card',
    `aui-card-${String(card.card_type).toLowerCase()}`,
    suspended ? 'is-suspended' : '',
    submitted ? 'is-submitted' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className={cls} data-card-id={card.card_id}>
      <header className="aui-card-header">
        <div className="aui-card-icon" aria-hidden="true">
          {iconFor(card.card_type)}
        </div>
        <div className="aui-card-title-block">
          <h4 className="aui-card-title">{title}</h4>
          {card.schema_version && (
            <span className="aui-card-version" title={`Schema v${card.schema_version}`}>
              v{card.schema_version}
            </span>
          )}
        </div>
        {suspended && <span className="aui-card-badge">等待您输入</span>}
        {submitted && <span className="aui-card-badge aui-card-badge-done">已提交</span>}
      </header>
      <div className="aui-card-body">{children}</div>
      {footer && <footer className="aui-card-footer">{footer}</footer>}
    </div>
  );
}

function defaultTitle(cardType: string): string {
  switch (cardType) {
    case 'OD_INPUT':
      return '请补充出行信息';
    case 'FLIGHT_LIST':
      return '请选择航班';
    case 'CABIN_LIST':
      return '请选择舱位';
    case 'PASSENGER_FORM':
      return '乘机人信息';
    case 'OAT_BINDING':
      return '选择出差单与成本中心';
    case 'PRICE_VERIFY':
      return '价格确认';
    case 'POLICY_DECISION':
      return '差旅政策决策';
    case 'ORDER_CONFIRM':
      return '订单确认';
    case 'ORDER_SUCCESS':
      return '下单成功';
    case 'CANNOT_ORDER':
      return '暂无法下单';
    case 'CHAT_FALLBACK':
      return '请补充信息';
    default:
      return '请处理';
  }
}

function iconFor(cardType: string): ReactNode {
  const c = '#0051A1';
  switch (cardType) {
    case 'FLIGHT_LIST':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2">
          <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
        </svg>
      );
    case 'CABIN_LIST':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2">
          <path d="M4 19h16M6 19v-7a3 3 0 0 1 3-3h6a3 3 0 0 1 3 3v7M9 9V6a3 3 0 0 1 6 0v3" />
        </svg>
      );
    case 'PRICE_VERIFY':
    case 'POLICY_DECISION':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M12 8v4M12 16h.01" />
        </svg>
      );
    case 'ORDER_CONFIRM':
    case 'ORDER_SUCCESS':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2">
          <path d="M9 12l2 2 4-4" />
          <circle cx="12" cy="12" r="10" />
        </svg>
      );
    case 'CANNOT_ORDER':
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#C0392B" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <path d="M4.93 4.93l14.14 14.14" />
        </svg>
      );
    default:
      return (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={c} strokeWidth="2">
          <path d="M4 6h16M4 12h16M4 18h10" />
        </svg>
      );
  }
}
