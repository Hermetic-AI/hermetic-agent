import type { Order } from '../../types';
import { Modal, StatusBadge, Button } from '../common';
import './OrderDetail.css';

interface OrderDetailProps {
  order: Order | null;
  open: boolean;
  onClose: () => void;
  onPay?: (order: Order) => void;
  onCancel?: (order: Order) => void;
}

export function OrderDetail({ order, open, onClose, onPay, onCancel }: OrderDetailProps) {
  if (!order) return null;

  const flight = order.flights[0];

  return (
    <Modal open={open} onClose={onClose} title="订单详情" size="medium">
      <div className="order-detail">
        <div className="detail-section">
          <div className="detail-row">
            <span className="detail-label">订单号</span>
            <span className="detail-value">{order.orderNo}</span>
          </div>
          <div className="detail-row">
            <span className="detail-label">订单状态</span>
            <StatusBadge status={order.status} />
          </div>
          <div className="detail-row">
            <span className="detail-label">下单时间</span>
            <span className="detail-value">{order.createdAt}</span>
          </div>
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
          {order.status === 'confirmed' && (
            <Button variant="secondary" onClick={onClose}>
              关闭
            </Button>
          )}
        </div>
      </div>
    </Modal>
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
      <circle cx="12" cy="8" r="4" />
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
