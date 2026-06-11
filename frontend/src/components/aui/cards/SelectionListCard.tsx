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
  const items = getSelectionItems(card);
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const resolveId = (item: Record<string, unknown>): string => {
    const key = idKey ?? pickIdKey(card.card_type);
    const v = item[key] ?? item.id ?? item.flightId ?? item.cabId ?? item.__selectionId;
    return v == null ? '' : String(v);
  };

  const handleConfirm = () => {
    if (!picked || busy || submitted) return;
    setBusy(true);
    const selectedItem = items.find((item) => resolveId(item) === picked);
    onSubmit(
      { selectedId: picked, [resolveIdKey(card.card_type)]: picked, selectedItem },
      'select',
    );
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
          disabled={!picked || submitted}
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
            item.title ?? formatFlightTitle(item) ?? item.name ?? item.label ?? `选项 ${idx + 1}`,
          );
          const sub =
            item.subtitle ?? item.flightDesc ?? item.description ?? formatFlightSubtitle(item);
          const price = item.price ?? item.fare;
          const tags = getItemTags(item);
          const selected = picked === id;
          return (
            <button
              type="button"
              key={id || idx}
              className={`aui-list-item ${selected ? 'selected' : ''}`}
              onClick={() => setPicked(id)}
              disabled={submitted}
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

function getSelectionItems(card: CardDescriptor): Array<Record<string, unknown>> {
  const directItems = card.flights ?? card.cabins ?? card.options;
  if (Array.isArray(directItems) && directItems.length > 0) {
    return withSelectionIds(directItems as Array<Record<string, unknown>>);
  }
  const plans = card.body?.plans;
  return Array.isArray(plans) ? withSelectionIds(plans as Array<Record<string, unknown>>) : [];
}

function withSelectionIds(items: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return items.map((item, idx) => ({
    ...item,
    __selectionId: buildSelectionId(item, idx),
  }));
}

function buildSelectionId(item: Record<string, unknown>, idx: number): string {
  const existing = item.id ?? item.flightId ?? item.cabId;
  if (existing != null && String(existing)) return String(existing);
  const parts = [
    item.flightNo,
    item.departureTime,
    item.arrivalTime,
    item.departureAirport,
    item.arrivalAirport,
    item.price,
    idx,
  ]
    .filter((part) => part != null && String(part))
    .map(String);
  return parts.length > 0 ? parts.join('|') : `option-${idx}`;
}

function formatFlightTitle(item: Record<string, unknown>): string | undefined {
  const flightNo = item.flightNo == null ? '' : String(item.flightNo);
  const airline = item.airline == null ? '' : String(item.airline);
  if (flightNo && airline) return `${flightNo} · ${airline}`;
  return flightNo || airline || undefined;
}

function formatFlightSubtitle(item: Record<string, unknown>): string {
  const time = [item.departureTime, item.arrivalTime].filter(Boolean).join(' - ');
  const airports = [item.departureAirport, item.arrivalAirport].filter(Boolean).join(' → ');
  const details = [time, airports, item.duration].filter(Boolean).map(String);
  return details.join(' · ');
}

function getItemTags(item: Record<string, unknown>): string[] {
  const tags = Array.isArray(item.tags) ? (item.tags as string[]) : [];
  const generatedTags = [
    item.seats ? `余票${String(item.seats)}` : '',
    item.stops === 0 ? '直飞' : item.stops != null ? `${String(item.stops)}次经停` : '',
    item.meal === true ? '含餐' : item.meal === false ? '无餐' : '',
    item.baggageInfo ?? item[' baggageInfo'] ?? '',
  ]
    .filter(Boolean)
    .map(String);
  return [...tags, ...generatedTags];
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
