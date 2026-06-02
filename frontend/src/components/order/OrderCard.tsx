import type { Order } from '../../types';
import { Button, StatusBadge } from '../common';
import './OrderCard.css';

interface OrderCardProps {
  order: Order;
  onPay?: (order: Order) => void;
  onCancel?: (order: Order) => void;
  onView?: (order: Order) => void;
}

export function OrderCard({ order, onPay, onCancel, onView }: OrderCardProps) {
  const flight = order.flights[0];

  return (
    <div className={`order-card ${order.violation ? 'order-card-violation' : ''}`}>
      <div className="order-card-header">
        <div className="order-no">
          <span className="order-label">订单号</span>
          <span className="order-value">{order.orderNo}</span>
        </div>
        <StatusBadge status={order.status} />
      </div>

      <div className="order-card-body">
        <div className="order-flight">
          <div className="flight-route">
            <span className="city">{flight.departure.city}</span>
            <span className="arrow">→</span>
            <span className="city">{flight.arrival.city}</span>
          </div>
          <div className="flight-datetime">
            {flight.departure.date} {flight.departure.time}
          </div>
        </div>

        <div className="order-passengers">
          <span className="passenger-label">乘机人</span>
          <span className="passenger-names">
            {order.passengers.map((p) => p.name).join(', ')}
          </span>
        </div>

        {order.violation && (
          <div className="order-violation">
            <span className="violation-icon">!</span>
            <span className="violation-text">{order.violation.description}</span>
          </div>
        )}
      </div>

      <div className="order-card-footer">
        <div className="order-total">
          <span className="total-label">合计</span>
          <span className="total-price">¥{order.totalPrice}</span>
        </div>
        <div className="order-actions">
          {onView && (
            <Button variant="text" size="small" onClick={() => onView(order)}>
              详情
            </Button>
          )}
          {order.status === 'pending' && onPay && (
            <Button size="small" onClick={() => onPay(order)}>
              去支付
            </Button>
          )}
          {order.status === 'pending' && onCancel && (
            <Button variant="text" size="small" onClick={() => onCancel(order)}>
              取消
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
