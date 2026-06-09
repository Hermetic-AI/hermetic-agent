import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface OrderSuccessCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// ORDER_SUCCESS — terminal state.  Shows order id, pay url, and lets the
// the user click "去支付" / "完成" actions.
export function OrderSuccessCard({ card, suspended, submitted, onSubmit }: OrderSuccessCardProps) {
  const orderNo = card.order_no ?? '';
  const payUrl = card.pay_url;

  return (
    <CardShell card={card} suspended={suspended} submitted={submitted}>
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      <div className="aui-summary-list">
        {orderNo && (
          <div className="aui-summary-row">
            <span>订单号</span>
            <span>{orderNo}</span>
          </div>
        )}
        {card.total_price != null && (
          <div className="aui-summary-row">
            <span>实付金额</span>
            <span>¥{Number(card.total_price).toFixed(0)}</span>
          </div>
        )}
      </div>
      <div className="aui-card-footer">
        {payUrl && (
          <a
            className="aui-action aui-action-primary"
            href={payUrl}
            target="_blank"
            rel="noreferrer"
          >
            去支付
          </a>
        )}
        <button
          type="button"
          className="aui-action aui-action-secondary"
          disabled={submitted}
          onClick={() => onSubmit({ acknowledged: true }, 'ack')}
        >
          完成
        </button>
      </div>
    </CardShell>
  );
}
