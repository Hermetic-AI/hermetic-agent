import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface OrderConfirmCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// ORDER_CONFIRM — show a flat summary of the order and let the user
// confirm or cancel.  The summary is read from `card.order_summary` or
// from individual top-level fields the backend may include.
export function OrderConfirmCard({ card, suspended, submitted, onSubmit }: OrderConfirmCardProps) {
  const summary = (card.order_summary ?? {}) as Record<string, unknown>;
  const rows: Array<[string, string]> = [];
  for (const [k, v] of Object.entries(summary)) {
    if (v == null) continue;
    rows.push([labelFor(k), typeof v === 'number' ? String(v) : String(v)]);
  }
  if (rows.length === 0 && card.total_price != null) {
    rows.push(['订单金额', `¥${Number(card.total_price).toFixed(0)}`]);
  }

  return (
    <CardShell
      card={card}
      suspended={suspended}
      submitted={submitted}
      footer={
        <>
          <button
            type="button"
            className="aui-action aui-action-ghost"
            disabled={submitted}
            onClick={() => onSubmit({ confirmed: false }, 'cancel')}
          >
            取消
          </button>
          <button
            type="button"
            className="aui-action aui-action-primary"
            disabled={submitted}
            onClick={() => onSubmit({ confirmed: true }, 'submit')}
          >
            确认下单
          </button>
        </>
      }
    >
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      {rows.length > 0 && (
        <div className="aui-summary-list">
          {rows.map(([k, v]) => (
            <div className="aui-summary-row" key={k}>
              <span>{k}</span>
              <span>{v}</span>
            </div>
          ))}
        </div>
      )}
    </CardShell>
  );
}

function labelFor(k: string): string {
  const map: Record<string, string> = {
    orderNo: '订单号',
    flightNo: '航班',
    cabin: '舱位',
    passenger: '乘机人',
    departDate: '出发日期',
    totalPrice: '订单金额',
    payDeadline: '支付截止',
  };
  return map[k] ?? k;
}
