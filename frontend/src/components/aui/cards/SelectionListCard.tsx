import { useState } from 'react';
import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';

export interface SelectionListCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  /** Extract the per-item id. Defaults to `id` / `flightId` / `cabId`. */
  idKey?: string;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// Renders FLIGHT_LIST, CABIN_LIST, and any other "pick one of N" cards.
// Each item must include at least: id, title (or label), and a price string.
export function SelectionListCard({
  card,
  suspended,
  submitted,
  idKey,
  onSubmit,
}: SelectionListCardProps) {
  const items = (card.flights ?? card.cabins ?? card.options ?? []) as Array<
    Record<string, unknown>
  >;
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const resolveId = (item: Record<string, unknown>): string => {
    const key = idKey ?? pickIdKey(card.card_type);
    const v = item[key] ?? item.id ?? item.flightId ?? item.cabId;
    return v == null ? '' : String(v);
  };

  const handleConfirm = () => {
    if (!picked || busy || suspended || submitted) return;
    setBusy(true);
    onSubmit({ selectedId: picked, [resolveIdKey(card.card_type)]: picked }, 'select');
  };

  return (
    <CardShell
      card={card}
      suspended={suspended}
      submitted={submitted}
      footer={
        <button
          type="button"
          className="aui-action aui-action-primary"
          disabled={!picked || suspended || submitted}
          onClick={handleConfirm}
        >
          {submitted ? '已选择' : '确认选择'}
        </button>
      }
    >
      {card.message && <p className="aui-card-message">{String(card.message)}</p>}
      <div className="aui-card-body">
        {items.length === 0 && <p className="aui-card-message">暂无可选项</p>}
        {items.map((item, idx) => {
          const id = resolveId(item);
          const title = String(
            item.title ?? item.flightNo ?? item.name ?? item.label ?? `选项 ${idx + 1}`,
          );
          const sub = item.subtitle ?? item.flightDesc ?? item.description ?? '';
          const price = item.price ?? item.fare;
          const tags = Array.isArray(item.tags) ? (item.tags as string[]) : [];
          const selected = picked === id;
          return (
            <button
              type="button"
              key={id || idx}
              className={`aui-list-item ${selected ? 'selected' : ''}`}
              onClick={() => setPicked(id)}
              disabled={suspended || submitted}
            >
              <div className="aui-list-item-main">
                <div className="aui-list-item-title">{title}</div>
                {sub ? <div className="aui-list-item-sub">{String(sub)}</div> : null}
                {tags.length > 0 && (
                  <div className="aui-list-item-tags">
                    {tags.map((t) => (
                      <span key={t} className="aui-tag">
                        {t}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              {price != null && (
                <div className="aui-list-item-meta">
                  <div className="aui-list-item-price">¥{Number(price).toFixed(0)}</div>
                </div>
              )}
            </button>
          );
        })}
      </div>
    </CardShell>
  );
}

function pickIdKey(cardType: string): string {
  if (cardType === 'FLIGHT_LIST') return 'flightId';
  if (cardType === 'CABIN_LIST') return 'cabId';
  return 'id';
}

function resolveIdKey(cardType: string): string {
  if (cardType === 'FLIGHT_LIST') return 'flightId';
  if (cardType === 'CABIN_LIST') return 'cabId';
  return 'selectedId';
}
