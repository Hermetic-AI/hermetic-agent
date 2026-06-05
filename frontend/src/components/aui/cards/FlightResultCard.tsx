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
      <div className="frc-summary">
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
            disabled={Boolean(suspended || submitted)}
          />
        ))}
      </div>

      {!suspended && !submitted && plans.length > 0 && (
        <div className="frc-footer-hint">
          点击「选这班」可直接进入预订流程; 或继续对话调整筛选条件。
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
        <h5 className="frc-plan-title">{plan.title}</h5>
        {plan.subtitle && <span className="frc-plan-subtitle">（{plan.subtitle}）</span>}
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
  const airlineLabel = segment.shareInfo
    ? `${segment.airline.name}（${segment.shareInfo}）`
    : segment.airline.name;
  return (
    <div className="frc-row">
      <div className="frc-row-date">
        <span className="frc-row-date-label">航班</span>
        <span className="frc-row-date-value">{segment.date}</span>
        <span className="frc-row-route">
          {dep.city} - {arr.city}
        </span>
      </div>

      <div className="frc-row-main">
        <div className="frc-row-time">
          <div className="frc-row-time-end">
            <span className="frc-row-time-hhmm">{dep.time}</span>
            <span className="frc-row-time-airport">
              {dep.airport}
              {dep.terminal ? ` ${dep.terminal}` : ''}
            </span>
          </div>
          <div className="frc-row-time-arrow">
            <span className="frc-row-time-duration">{segment.duration}</span>
            <span className="frc-row-time-line">———▶</span>
            <span className="frc-row-time-stops">
              {segment.stops === 0 ? '直飞' : `经停 ${segment.stops} 次`}
            </span>
          </div>
          <div className="frc-row-time-end">
            <span className="frc-row-time-hhmm">{arr.time}</span>
            <span className="frc-row-time-airport">
              {arr.airport}
              {arr.terminal ? ` ${arr.terminal}` : ''}
            </span>
          </div>
        </div>

        <div className="frc-row-meta">
          <span className="frc-row-airline">
            {airlineLabel} · {segment.aircraft ?? '机型未提供'}
          </span>
          <span className="frc-row-cabin">{segment.cabin}</span>
          <FlightComplianceInline price={Number(segment.price)} cabinClass={segment.cabinClass} />
        </div>

        {showTags.length > 0 && (
          <div className="frc-row-tags">
            {showTags.map((t) => (
              <span key={t} className="frc-tag">
                {t}
              </span>
            ))}
          </div>
        )}
      </div>

      <div className="frc-row-aside">
        <div className="frc-row-price-label">起</div>
        <div className="frc-row-price">¥{Number(segment.price).toFixed(0)}</div>
        <button
          type="button"
          className="frc-row-pick"
          onClick={onPick}
          disabled={disabled}
        >
          选这班
        </button>
      </div>
    </div>
  );
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
