import { useEffect, useState } from 'react';
import type { Order } from '../../types';
import { Modal, StatusBadge, Button } from '../common';
import './OrderDetail.css';

interface OrderDetailProps {
  order: Order | null;
  open: boolean;
  onClose: () => void;
  onPay?: (order: Order) => void;
  onCancel?: (order: Order) => void;
  onAskAI?: (prompt: string) => void;
}

export function OrderDetail({
  order,
  open,
  onClose,
  onPay,
  onCancel,
  onAskAI,
}: OrderDetailProps) {
  if (!order) return null;

  const flight = order.flights[0];
  const showChange = order.status === 'confirmed';
  const showRefund = order.status !== 'completed' && order.status !== 'refunded';
  const showInvoice = order.status === 'completed';
  const showContact = true;

  return (
    <Modal open={open} onClose={onClose} title="订单详情" size="medium">
      <div className="order-detail">
        <div className="detail-section">
          <div className="detail-row">
            <span className="detail-label">订单号</span>
            <span className="detail-value detail-value-mono">{order.orderNo}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">订单状态</span>
            <StatusBadge status={order.status} />
          </div>
          <div className="detail-row">
            <span className="detail-label">下单时间</span>
            <span className="detail-value">{order.createdAt}</span>
          </div>
          {order.status === 'pending' && (
            <div className="detail-row">
              <span className="detail-label">剩余支付</span>
              <PayCountdown createdAt={order.createdAt} />
            </div>
          )}
        </div>

        <div className="detail-divider" />

        <div className="detail-section">
          <h4 className="section-title">航班信息</h4>
          <div className="flight-detail">
            <div className="flight-route-large">
              <div className="route-point">
                <span className="city">{flight.departure.city}</span>
                <span className="airport">{flight.departure.airport}</span>
                <span className="code">{flight.departure.airportCode}</span>
              </div>
              <div className="route-arrow">
                <AirplaneIcon />
              </div>
              <div className="route-point">
                <span className="city">{flight.arrival.city}</span>
                <span className="airport">{flight.arrival.airport}</span>
                <span className="code">{flight.arrival.airportCode}</span>
              </div>
            </div>
            <div className="flight-meta">
              <span className="meta-item">{flight.flightNumber}</span>
              <span className="meta-item">{flight.airline}</span>
              <span className="meta-item">{flight.departure.date}</span>
              <span className="meta-item">{flight.duration}</span>
            </div>
          </div>
        </div>

        <div className="detail-divider" />

        <div className="detail-section">
          <h4 className="section-title">乘机人</h4>
          <div className="passenger-list">
            {order.passengers.map((p, idx) => (
              <div key={idx} className="passenger-item">
                <UserIcon />
                <div className="passenger-info">
                  <span className="passenger-name">{p.name}</span>
                  <span className="passenger-id">{p.idType}: {p.idNumber}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {order.violation && (
          <>
            <div className="detail-divider" />
            <div className="detail-section">
              <h4 className="section-title violation-title">违规信息</h4>
              <div className="violation-info">
                <AlertIcon />
                <div>
                  <p className="violation-type">{order.violation.type}</p>
                  <p className="violation-desc">{order.violation.description}</p>
                </div>
              </div>
            </div>
          </>
        )}

        <div className="detail-divider" />

        <div className="detail-section">
          <h4 className="section-title">费用明细</h4>
          <div className="price-breakdown">
            <div className="price-row">
              <span>票价</span>
              <span>¥{flight.price}</span>
            </div>
            <div className="price-row">
              <span>税费</span>
              <span>¥{order.tax}</span>
            </div>
            <div className="price-row total">
              <span>合计</span>
              <span className="total-amount">¥{order.totalPrice}</span>
            </div>
          </div>
        </div>

        {onAskAI && (
          <div className="detail-divider" />
        )}
        {onAskAI && (
          <div className="detail-section">
            <h4 className="section-title">订单服务</h4>
            <div className="detail-quick-actions">
              {showChange && (
                <button
                  type="button"
                  className="detail-quick-action"
                  onClick={() => onAskAI(`帮我改签订单 ${order.orderNo}, 想变更出发日期或航班`)}
                >
                  <ChangeIcon />
                  <span className="detail-quick-action-label">改签</span>
                  <span className="detail-quick-action-hint">变更日期/航班</span>
                </button>
              )}
              {showRefund && (
                <button
                  type="button"
                  className="detail-quick-action"
                  onClick={() => onAskAI(`帮我退票订单 ${order.orderNo}`)}
                >
                  <RefundIcon />
                  <span className="detail-quick-action-label">退票</span>
                  <span className="detail-quick-action-hint">按航司政策退款</span>
                </button>
              )}
              {showInvoice && (
                <button
                  type="button"
                  className="detail-quick-action"
                  onClick={() => onAskAI(`帮我申请订单 ${order.orderNo} 的报销发票`)}
                >
                  <InvoiceIcon />
                  <span className="detail-quick-action-label">申请发票</span>
                  <span className="detail-quick-action-hint">电子发票秒开</span>
                </button>
              )}
              {showContact && (
                <button
                  type="button"
                  className="detail-quick-action"
                  onClick={() => onAskAI(`订单 ${order.orderNo} 遇到问题, 想联系航司客服`)}
                >
                  <ContactIcon />
                  <span className="detail-quick-action-label">联系客服</span>
                  <span className="detail-quick-action-hint">7×24 在线</span>
                </button>
              )}
            </div>
          </div>
        )}

        <div className="detail-actions">
          {order.status === 'pending' && (
            <>
              <Button variant="secondary" onClick={() => onCancel?.(order)}>
                取消订单
              </Button>
              <Button onClick={() => onPay?.(order)}>
                去支付
              </Button>
            </>
          )}
          {order.status !== 'pending' && (
            <Button variant="secondary" onClick={onClose}>
              关闭
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}

/**
 * 简单倒计时: 演示数据, 模拟"还剩 X 分钟需要支付".
 * 真实接入会用真实 createdAt + 航司/平台超时规则.
 */
function PayCountdown({ createdAt }: { createdAt: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);
  const created = Date.parse(createdAt.replace(' ', 'T')) || now;
  const deadline = created + 30 * 60 * 1000; // 30 分钟支付窗口
  const ms = Math.max(0, deadline - now);
  if (ms === 0) {
    return <span className="detail-value detail-countdown-expired">已超时</span>;
  }
  const min = Math.floor(ms / 60000);
  const sec = Math.floor((ms % 60000) / 1000);
  const urgent = min < 5;
  return (
    <span
      className={`detail-value detail-countdown ${urgent ? 'is-urgent' : ''}`}
      title="支付窗口 30 分钟, 超时自动取消"
    >
      {String(min).padStart(2, '0')}:{String(sec).padStart(2, '0')}
      {urgent && <span className="detail-countdown-tag">尽快</span>}
    </span>
  );
}

function AirplaneIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#4A9BE8" strokeWidth="2">
      <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#999" strokeWidth="2">
      <circle cx="12" cy="12" r="4" />
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#FF3B30" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}

function ChangeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  );
}

function RefundIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="3 7 3 13 9 13" />
      <path d="M3 13a9 9 0 0 0 15.39 5.39L21 16" />
      <path d="M21 7v6h-6" />
    </svg>
  );
}

function InvoiceIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="9" y1="13" x2="15" y2="13" />
      <line x1="9" y1="17" x2="15" y2="17" />
    </svg>
  );
}

function ContactIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  );
}
