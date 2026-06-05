import type { CardAction, CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface PolicyDecisionCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// POLICY_DECISION — render `decision_buttons` (or `actions`) so the user
// can pick a surcharge / downgrade / abort decision.
export function PolicyDecisionCard({ card, suspended, submitted, onSubmit }: PolicyDecisionCardProps) {
  const buttons = (card.decision_buttons ?? card.actions ?? []) as CardAction[];

  return (
    <CardShell card={card} suspended={suspended} submitted={submitted}>
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      {card.policy_hint != null && (
        <p className="aui-card-message">{String(card.policy_hint)}</p>
      )}
      <div className="aui-card-body" style={{ gap: 8 }}>
        {buttons.map((btn) => {
          const style = btn.style ?? 'secondary';
          const surcharge = (btn as unknown as { surcharge?: number }).surcharge;
          return (
            <button
              key={btn.id}
              type="button"
              className={`aui-action aui-action-${styleClass(style)}`}
              disabled={suspended || submitted}
              onClick={() =>
                onSubmit(
                  {
                    decision: btn.code ?? btn.id,
                    surcharge: surcharge ?? 0,
                  },
                  btn.id,
                )
              }
            >
              {btn.label}
              {surcharge != null && surcharge > 0 && (
                <span className="aui-price-diff" style={{ marginLeft: 8 }}>
                  +¥{Number(surcharge).toFixed(0)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </CardShell>
  );
}

function styleClass(s: string): string {
  switch (s) {
    case 'primary':
      return 'primary';
    case 'danger':
      return 'danger';
    case 'ghost':
      return 'ghost';
    default:
      return 'secondary';
  }
}
