import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface PriceVerifyCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// PRICE_VERIFY — show current vs original price, policy overrun, and
// a confirm/reject action.  Acts as the S10/S11 confirm step.
export function PriceVerifyCard({ card, suspended, submitted, onSubmit }: PriceVerifyCardProps) {
  const current = card.current_price ?? card.total_price ?? 0;
  const original = card.original_price ?? current;
  const diff = card.price_diff ?? Math.max(0, current - original);
  const overrun = Boolean(card.policy_overrun);

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
            disabled={suspended || submitted}
            onClick={() => onSubmit({ confirmed: false, accept: false }, 'reject')}
          >
            暂不预订
          </button>
          <button
            type="button"
            className="aui-action aui-action-primary"
            disabled={suspended || submitted}
            onClick={() => onSubmit({ confirmed: true, accept: true }, 'confirm')}
          >
            {overrun ? '确认超额并继续' : '确认价格'}
          </button>
        </>
      }
    >
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      <div className="aui-summary-list">
        <div className="aui-summary-row">
          <span>当前价格</span>
          <span>
            ¥{Number(current).toFixed(0)}
            {overrun && <span className="aui-price-diff">+¥{Number(diff).toFixed(0)}</span>}
          </span>
        </div>
        {original !== current && (
          <div className="aui-summary-row">
            <span>原价格</span>
            <span>¥{Number(original).toFixed(0)}</span>
          </div>
        )}
        {overrun && (
          <div className="aui-summary-row" style={{ color: '#92400e' }}>
            <span>超出差旅标准</span>
            <span>差额由员工承担</span>
          </div>
        )}
      </div>
    </CardShell>
  );
}
