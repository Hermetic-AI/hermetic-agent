import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface CannotOrderCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// CANNOT_ORDER — terminal fallback.  Shows the reason and any
// recovery action (e.g. "联系管理员", "去 OA 申请").
export function CannotOrderCard({ card, suspended, submitted, onSubmit }: CannotOrderCardProps) {
  const reason = card.reason ?? card.message ?? '系统检测到无法继续下单';
  const fallback = card.fallback;
  return (
    <CardShell
      card={card}
      suspended={suspended}
      submitted={submitted}
      footer={
        <button
          type="button"
          className="aui-action aui-action-secondary"
          disabled={submitted}
          onClick={() => onSubmit({ acknowledged: true }, 'ack')}
        >
          我知道了
        </button>
      }
    >
      <p className="aui-card-message" style={{ color: '#991b1b' }}>
        {String(reason)}
      </p>
      {fallback && (
        <p className="aui-card-message" style={{ color: '#475569' }}>
          {String(fallback)}
        </p>
      )}
    </CardShell>
  );
}
