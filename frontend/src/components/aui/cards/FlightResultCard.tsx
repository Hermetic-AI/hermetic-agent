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
  const plans = (body.plans ?? []) as FlightPlan[];
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
  expanded,
  onPick,
  disabled,
}: {
  plan: FlightPlan;
  expanded: boolean;
  onPick: (seg: FlightSegment) => void;
  disabled: boolean;
}) {
  return (
    <div className="frc-plan">
      <div className="frc-plan-header">
        <span className="frc-plan-index">方案{planIndex(plan.id, plan.title)}</span>
        <div className="frc-plan-copy">
          <h5 className="frc-plan-title">{plan.title}</h5>
          {plan.subtitle && <span className="frc-plan-subtitle">{plan.subtitle}</span>}
        </div>
      </div>
      <div className="frc-plan-flights">
        {plan.flights.map((seg, idx) => (
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
  const dep = segment.departure;
  const arr = segment.arrival;
  const depTime = formatClock(dep.time);
  const arrTime = formatClock(arr.time);
  const routeDate = formatDateLabel(segment.date || dep.time);
  const routeLabel = [dep.city, arr.city].filter(Boolean).join(' → ');
  const depPlace = formatAirport(dep);
  const arrPlace = formatAirport(arr);
  const airlineLabel = segment.shareInfo
    ? `${segment.airline.name}（${segment.shareInfo}）`
    : segment.airline.name;
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
          <span className="frc-airline-chip">{airlineLabel || segment.airline.code || '航司未提供'} {segment.flightNo}</span>
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

function planIndex(id: string, title: string): string {
  if (id === 'fastest' || title.includes('快')) return '1';
  if (id === 'cheapest' || title.includes('便宜')) return '2';
  if (id === 'comfortable' || title.includes('舒适') || title.includes('直飞')) return '3';
  return '';
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
