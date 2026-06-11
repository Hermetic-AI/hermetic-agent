import { useState } from 'react';
import type {
  CardDescriptor,
  FlightPlan,
  FlightResultSummary,
  FlightSegment,
} from '../../../types';
import { CardShell } from '../CardShell';
import { checkCompliance } from '../../../lib';
import '../../../lib/compliance.css';
import './FlightResultCard.css';

export interface FlightResultCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

// Renders FLIGHT_RESULT — the post-query "机票已发送" card from
// work/shared/skills/flight-query §5.1.
//
// Layout matches docs/ui/AI订票-对话卡片.png:
//   ┌──────────────────────────────────────────────────┐
//   │  ✈ 机票已发送                                     │
//   │  共查询到 50 个航班, 最终筛选出 10 个        更多▾ │
//   ├──────────────────────────────────────────────────┤
//   │  方案1: 最快抵达, 大兴机场落地 (用时最短)         │
//   │   ┌──────────────────────────────────────────┐  │
//   │   │  03月21日 深圳 → 北京                    │  │
//   │   │  13:45 ─── 2h25m ──▶ 16:40   ¥550 起    │  │
//   │   │  宝安T3                 大兴T3            │  │
//   │   │  [东航5256413] [便宜437元]                 │  │
//   │   └──────────────────────────────────────────┘  │
//   │  方案2: 便宜早班直飞, 首都机场直达 (价格最低)    │
//   │   ...                                            │
//   └──────────────────────────────────────────────────┘
export function FlightResultCard({
  card,
  suspended,
  submitted,
  onSubmit,
}: FlightResultCardProps) {
  const body = card.body ?? {};
  const summary = (body.summary ?? null) as FlightResultSummary | null;
  const plans = normalizePlans(body.plans);
  const [expanded, setExpanded] = useState(false);

  return (
    <CardShell card={card} suspended={suspended} submitted={submitted}>
      <div className="frc-card-topline">
        {summary && <SummaryLine summary={summary} expanded={expanded} onToggle={() => setExpanded((v) => !v)} />}
      </div>

      {plans.length === 0 && (
        <p className="aui-card-message frc-empty">本场景无可用方案</p>
      )}

      <div className="frc-plans">
        {plans.map((plan, idx) => (
          <PlanBlock
            key={`${plan.id}-${idx}`}
            plan={plan}
            index={idx}
            expanded={expanded}
            onPick={(seg) =>
              onSubmit(
                {
                  flightId: seg.flightId,
                  flightNo: seg.flightNo,
                  planId: plan.id,
                  cabin: seg.cabin,
                  cabinClass: seg.cabinClass,
                  price: seg.price,
                },
                'select_flight',
              )
            }
            disabled={Boolean(submitted)}
          />
        ))}
      </div>

      {!submitted && plans.length > 0 && (
        <div className="frc-footer-hint">
          你可以点选推荐航班进入预订，也可以继续说出发时段、航司或价格偏好。
        </div>
      )}
    </CardShell>
  );
}

function SummaryLine({
  summary,
  expanded,
  onToggle,
}: {
  summary: FlightResultSummary;
  expanded: boolean;
  onToggle: () => void;
}) {
  if (typeof summary === 'string') {
    return (
      <div className="frc-summary-row">
        <span className="frc-summary-text">{summary}</span>
        <button
          type="button"
          className="frc-summary-toggle"
          onClick={onToggle}
          aria-expanded={expanded}
        >
          {expanded ? '收起 ▴' : '更多 ▾'}
        </button>
      </div>
    );
  }
  const weather = summary.weather;
  return (
    <div className="frc-summary-row">
      <span className="frc-summary-text">
        共查询到 <strong>{summary.totalCount}</strong> 个航班，
        最终筛选出 <strong>{summary.filteredCount}</strong> 个
        {weather && <span className="frc-summary-weather"> · {weather}</span>}
      </span>
      <button
        type="button"
        className="frc-summary-toggle"
        onClick={onToggle}
        aria-expanded={expanded}
      >
        {expanded ? '收起 ▴' : '更多 ▾'}
      </button>
    </div>
  );
}

function PlanBlock({
  plan,
  index,
  expanded,
  onPick,
  disabled,
}: {
  plan: FlightPlan;
  index: number;
  expanded: boolean;
  onPick: (seg: FlightSegment) => void;
  disabled: boolean;
}) {
  const flights = Array.isArray(plan.flights) ? plan.flights : [];
  const title = plan.title || defaultPlanTitle(plan.id, index);
  return (
    <div className="frc-plan">
      <div className="frc-plan-header">
        <span className="frc-plan-index">方案{planIndex(plan.id, title, index)}</span>
        <div className="frc-plan-copy">
          <h5 className="frc-plan-title">{title}</h5>
          {plan.subtitle && <span className="frc-plan-subtitle">{plan.subtitle}</span>}
        </div>
      </div>
      <div className="frc-plan-flights">
        {flights.map((seg, idx) => (
          <FlightRow
            key={seg.flightId ?? `${plan.id}-${idx}`}
            segment={seg}
            expanded={expanded}
            onPick={() => onPick(seg)}
            disabled={disabled}
          />
        ))}
      </div>
    </div>
  );
}

function FlightRow({
  segment,
  expanded,
  onPick,
  disabled,
}: {
  segment: FlightSegment;
  expanded: boolean;
  onPick: () => void;
  disabled: boolean;
}) {
  const showTags = (segment.tags ?? []).slice(0, expanded ? 10 : 2);
  const dep = segment.departure ?? {};
  const arr = segment.arrival ?? {};
  const depTime = formatClock(dep.time);
  const arrTime = formatClock(arr.time);
  const routeDate = formatDateLabel(segment.date || dep.time);
  const routeLabel = [dep.city, arr.city].filter(Boolean).join(' → ');
  const depPlace = formatAirport(dep);
  const arrPlace = formatAirport(arr);
  const airline = segment.airline ?? { code: '', name: '' };
  const airlineLabel = segment.shareInfo
    ? `${airline.name || airline.code || '航司未提供'}（${segment.shareInfo}）`
    : airline.name;
  return (
    <article className="frc-ticket">
      <div className="frc-ticket-head">
        <span className="frc-ticket-route">{routeDate} {routeLabel}</span>
        <span className="frc-ticket-badge">{segment.stops === 0 ? '直飞' : `经停${segment.stops}次`}</span>
      </div>

      <div className="frc-ticket-body">
        <div className="frc-flightline">
          <div className="frc-timepoint frc-timepoint-left">
            <span className="frc-time">{depTime}</span>
            <span className="frc-airport">{depPlace}</span>
          </div>

          <div className="frc-path" aria-hidden="true">
            <span className="frc-duration">{formatDuration(segment.duration)}</span>
            <span className="frc-path-line"><i /></span>
          </div>

          <div className="frc-timepoint frc-timepoint-right">
            <span className="frc-time">{arrTime}</span>
            <span className="frc-airport">{arrPlace}</span>
          </div>
        </div>

        <div className="frc-ticket-meta">
          <span className="frc-airline-chip">{airlineLabel || airline.code || '航司未提供'} {segment.flightNo}</span>
          {segment.aircraft && <span className="frc-soft-chip">{segment.aircraft}</span>}
          {segment.cabin && <span className="frc-soft-chip">{segment.cabin}</span>}
          <FlightComplianceInline price={Number(segment.price)} cabinClass={segment.cabinClass} />
        </div>

        {showTags.length > 0 && (
          <div className="frc-ticket-tags">
            {showTags.map((t) => (
              <span key={t} className="frc-tag">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="frc-ticket-pricebox">
        <div className="frc-price-line"><span>¥</span>{Number(segment.price).toFixed(0)}</div>
        <div className="frc-price-suffix">起</div>
        <button
          type="button"
          className="frc-pick"
          onClick={onPick}
          disabled={disabled}
        >
          选这班
        </button>
      </div>
    </article>
  );
}

function normalizePlans(value: unknown): FlightPlan[] {
  if (!Array.isArray(value)) return [];
  return value.map((raw, idx) => normalizePlan(raw as Record<string, unknown>, idx));
}

function normalizePlan(raw: Record<string, unknown>, idx: number): FlightPlan {
  const id = stringValue(raw.id ?? raw.plan_id) ?? `plan-${idx + 1}`;
  const flights = Array.isArray(raw.flights)
    ? (raw.flights as Array<Record<string, unknown>>).map((flight, flightIdx) =>
        normalizeFlightSegment(flight, id, flightIdx),
      )
    : [normalizeFlightSegment(raw, id, 0)];

  return {
    ...raw,
    id,
    title: stringValue(raw.title) ?? defaultPlanTitle(id, idx),
    subtitle: stringValue(raw.subtitle ?? raw.criteria),
    flights,
  } as FlightPlan;
}

function normalizeFlightSegment(
  raw: Record<string, unknown>,
  planId: string,
  idx: number,
): FlightSegment {
  const flightNo = stringValue(raw.flightNo ?? raw.flight_no) ?? '';
  const depTime = stringValue(raw.departure_time ?? raw.departureTime) ?? '';
  const arrTime = stringValue(raw.arrival_time ?? raw.arrivalTime) ?? '';
  const departureText = stringValue(raw.departure ?? raw.departureAirport) ?? '';
  const arrivalText = stringValue(raw.arrival ?? raw.arrivalAirport) ?? '';
  const airline = normalizeAirline(raw.airline);
  const stops = typeof raw.stops === 'number' ? raw.stops : 0;
  const seats = raw.seats == null ? '' : `余票${String(raw.seats)}`;
  const tags = Array.isArray(raw.tags) ? (raw.tags as string[]) : [seats].filter(Boolean);

  return {
    ...raw,
    flightId: stringValue(raw.flightId ?? raw.flight_id ?? raw.plan_id ?? raw.id)
      ?? `${planId}-${flightNo || idx}`,
    flightNo,
    airline,
    date: stringValue(raw.date) ?? depTime,
    departure: normalizeEndpoint(raw.departure, departureText, depTime),
    arrival: normalizeEndpoint(raw.arrival, arrivalText, arrTime),
    duration: stringValue(raw.duration) ?? '',
    stops,
    cabin: stringValue(raw.cabin) ?? '',
    cabinClass: stringValue(raw.cabinClass ?? raw.cabin_class) ?? 'ECONOMY',
    price: Number(raw.price ?? raw.fare ?? 0),
    tags,
  } as FlightSegment;
}

function normalizeAirline(value: unknown): { code: string; name: string } {
  if (value && typeof value === 'object') {
    const airline = value as Record<string, unknown>;
    return {
      code: stringValue(airline.code) ?? '',
      name: stringValue(airline.name) ?? stringValue(airline.label) ?? '',
    };
  }
  return { code: '', name: stringValue(value) ?? '' };
}

function normalizeEndpoint(value: unknown, fallback: string, time: string): FlightSegment['departure'] {
  if (value && typeof value === 'object') {
    const endpoint = value as Record<string, unknown>;
    return {
      city: stringValue(endpoint.city) ?? '',
      airport: stringValue(endpoint.airport) ?? fallback,
      airportCode: stringValue(endpoint.airportCode ?? endpoint.airport_code) ?? '',
      terminal: stringValue(endpoint.terminal),
      time: stringValue(endpoint.time) ?? time,
    };
  }
  return { city: '', airport: fallback, airportCode: '', time };
}

function stringValue(value: unknown): string | undefined {
  if (value == null) return undefined;
  if (typeof value === 'object') return undefined;
  const text = String(value);
  return text ? text : undefined;
}

function planIndex(id: string | undefined, title: string | undefined, fallbackIndex: number): string {
  const safeTitle = title ?? '';
  if (id === 'fastest' || safeTitle.includes('快')) return '1';
  if (id === 'cheapest' || safeTitle.includes('便宜')) return '2';
  if (id === 'comfortable' || safeTitle.includes('舒适') || safeTitle.includes('直飞')) return '3';
  return String(fallbackIndex + 1);
}

function defaultPlanTitle(id: string | undefined, index: number): string {
  if (id === 'fastest') return '最快抵达';
  if (id === 'cheapest') return '最便宜';
  if (id === 'comfortable') return '舒适首选';
  return `推荐方案 ${index + 1}`;
}

function formatClock(value?: string): string {
  if (!value) return '--:--';
  const match = String(value).match(/(\d{1,2}:\d{2})/);
  return match ? match[1] : String(value);
}

function formatDateLabel(value?: string): string {
  if (!value) return '';
  const text = String(value);
  const match = text.match(/(?:\d{4}-)?(\d{1,2})-(\d{1,2})/);
  if (!match) return text;
  return `${match[1].padStart(2, '0')}月${match[2].padStart(2, '0')}日`;
}

function formatAirport(endpoint: { airport?: string; terminal?: string }): string {
  return [endpoint.airport, endpoint.terminal].filter(Boolean).join(' ');
}

function formatDuration(value?: string): string {
  if (!value) return '';
  return String(value).replace('分钟', 'm').replace('小时', 'h');
}

function FlightComplianceInline({
  price,
  cabinClass,
}: {
  price: number;
  cabinClass?: string;
}) {
  const verdict = checkCompliance(price, cabinClass ?? 'economy');
  return (
    <span
      className={`compliance-badge compliance-${verdict.level}`}
      title={verdict.tooltip}
    >
      {verdict.label}
    </span>
  );
}
