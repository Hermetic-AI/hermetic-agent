import { useState } from 'react';
import type { CardDescriptor } from '../../../types';
import { CardShell } from '../CardShell';
import { extractAguiTurn, type AguiDataItem } from './domesticAgui';
import './DomesticAguiCard.css';

interface DomesticAguiCardProps {
  card: CardDescriptor;
  suspended?: boolean;
  submitted?: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}

export function DomesticAguiCard({ card, suspended, submitted, onSubmit }: DomesticAguiCardProps) {
  const turn = extractAguiTurn(card);
  const [expanded, setExpanded] = useState(false);
  if (!turn) return null;

  const dataList = Array.isArray(turn.contentJson.dataList) ? turn.contentJson.dataList : [];
  return (
    <CardShell card={card} suspended={suspended} submitted={submitted}>
      <div className="dagui-shell" data-scene-id={turn.sceneId ?? ''}>
        {turn.reason && <p className="dagui-reason">{turn.reason}</p>}
        {dataList.map((item, index) => (
          <AguiBlock
            key={`${item.basicType}-${index}`}
            item={item}
            index={index}
            expanded={expanded}
            setExpanded={setExpanded}
            submitted={Boolean(submitted)}
            onSubmit={onSubmit}
          />
        ))}
      </div>
    </CardShell>
  );
}

function AguiBlock({
  item,
  index,
  expanded,
  setExpanded,
  submitted,
  onSubmit,
}: {
  item: AguiDataItem;
  index: number;
  expanded: boolean;
  setExpanded: (value: boolean) => void;
  submitted: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}) {
  switch (item.basicType) {
    case 'PLAIN_TEXT':
      return <p className="dagui-text">{item.dataStr}</p>;
    case 'AIR_DOMESTIC_FLIGHT_LIST':
      return (
        <FlightListBlock
          item={item}
          expanded={expanded}
          setExpanded={setExpanded}
          submitted={submitted}
          onSubmit={onSubmit}
        />
      );
    case 'AIR_DOMESTIC_FLIGHT_SUGGEST':
      return (
        <FlightScheme
          index={index}
          title={item.dataStr || `推荐方案 ${index + 1}`}
          flight={item.dataJson ?? {}}
          submitted={submitted}
          onPick={(flight) => onSubmit(buildFlightInput(flight, index), 'select_flight')}
        />
      );
    case 'AIR_DOMESTIC_CABIN_LIST':
      return <CabinListBlock item={item} submitted={submitted} onSubmit={onSubmit} />;
    case 'AIR_DOMESTIC_ORDER_SUMMARY':
      return <OrderSummaryBlock item={item} onSubmit={onSubmit} />;
    case 'BUTTON':
      return (
        <button
          type="button"
          className="dagui-primary-btn"
          disabled={submitted}
          onClick={() => onSubmit({ action: item.linkUrl, label: item.dataStr }, item.linkUrl || 'click')}
        >
          {item.dataStr || '继续'}
        </button>
      );
    default:
      return null;
  }
}

function FlightListBlock({
  item,
  expanded,
  setExpanded,
  submitted,
  onSubmit,
}: {
  item: AguiDataItem;
  expanded: boolean;
  setExpanded: (value: boolean) => void;
  submitted: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}) {
  const flights = arrayOfRecords(item.dataJson?.flightList);
  const visibleFlights = expanded ? flights : flights.slice(0, 3);
  return (
    <section className="dagui-section">
      <div className="flight-list-card__summary-row">
        <span className="flight-list-card__summary-text">
          {item.dataStr || formatFlightListSummary(item.dataJson)}
        </span>
        {flights.length > 3 && (
          <button
            type="button"
            className="flight-list-card__more-btn dagui-link-btn"
            data-testid="flight-list-more-btn"
            onClick={() => setExpanded(!expanded)}
          >
            <span>{expanded ? '收起' : '更多'}</span>
            <span className="flight-list-card__more-chevron" aria-hidden="true">
              {expanded ? '▲' : '▼'}
            </span>
          </button>
        )}
      </div>
      <div className="dagui-list">
        {visibleFlights.map((flight, index) => (
          <FlightRow
            key={String(flight.flightId ?? flight.flightNo ?? index)}
            flight={flight}
            title={`机票  ${index + 1}`}
            submitted={submitted}
            onPick={(picked) => onSubmit(buildFlightInput(picked, index), 'select_flight')}
          />
        ))}
      </div>
    </section>
  );
}

function FlightScheme({
  index,
  title,
  flight,
  submitted,
  onPick,
}: {
  index: number;
  title: string;
  flight: Record<string, unknown>;
  submitted: boolean;
  onPick: (flight: Record<string, unknown>) => void;
}) {
  return (
    <section className="dagui-scheme">
      <h4 className="dagui-scheme__title">
        方案{index + 1}：{title}
      </h4>
      <FlightRow
        flight={flight}
        title={title}
        submitted={submitted}
        onPick={onPick}
      />
    </section>
  );
}

function FlightRow({
  flight,
  title,
  submitted,
  onPick,
}: {
  flight: Record<string, unknown>;
  title: string;
  submitted: boolean;
  onPick: (flight: Record<string, unknown>) => void;
}) {
  const legs = arrayOfRecords(flight.legs);
  const firstLeg = legs[0] ?? flight;
  const airId = String(flight.airId ?? firstLeg.airId ?? '').toUpperCase();
  const aircraftName = String(firstLeg.aircraftName ?? flight.aircraftName ?? '').trim();
  const meal = firstLeg.meal;
  const stops = Number(flight.stopCount ?? 0);
  const transferCount = Number(flight.transferCount ?? 0);
  const routeTag = stops > 0 ? `经停${stops}次` : transferCount > 0 ? `中转${transferCount}次` : '直飞';
  return (
    <article className="dagui-flight-item flight-item flight-card">
      <button
        type="button"
        className="dagui-flight-click"
        disabled={submitted}
        onClick={() => onPick(flight)}
      >
        <div className="flight-card__doc-title">{titleLine(flight, firstLeg, title)}</div>
        <div className="flight-journey-row">
          <div className="flight-journey-row__dep">
            <span className="flight-journey-row__time">{clock(firstLeg.depTime)}</span>
            <span className="flight-journey-row__ap">{airport(firstLeg, 'dep')}</span>
          </div>
          <div className="flight-journey-row__mid">
            <span className="flight-journey-row__dur">
              {duration(flight.totalDuration ?? flight.durationMin ?? firstLeg.duration)}
            </span>
            <span className="flight-journey-row__mid-line" aria-hidden="true" />
          </div>
          <div className="flight-journey-row__arr">
            <span className="flight-journey-row__time">{clock(firstLeg.arrTime)}</span>
            <span className="flight-journey-row__ap">{airport(firstLeg, 'arr')}</span>
          </div>
          <div className="flight-journey-row__price">
            <span className="flight-journey-row__price-num">¥{money(flight.lowestPrice ?? flight.totalPrice)}</span>
            <span className="flight-journey-row__price-suffix">起</span>
          </div>
        </div>
        <div className="flight-card__airline-row">
          {airlineLogo(airId) ? (
            <img
              className="flight-card__airline-logo-img"
              src={airlineLogo(airId) ?? ''}
              alt={String(flight.airlineName ?? firstLeg.airlineName ?? '')}
              loading="lazy"
              onError={(event) => {
                const target = event.currentTarget;
                target.style.display = 'none';
                const fallback = target.nextElementSibling;
                if (fallback) (fallback as HTMLElement).style.display = 'inline-flex';
              }}
            />
          ) : null}
          <span
            className="flight-card__airline-logo"
            style={airlineLogo(airId) ? { display: 'none' } : undefined}
          >
            {airlineInitial(flight.airlineName ?? firstLeg.airlineName)}
          </span>
          <span className="flight-card__airline-text">
            {String(flight.airlineName ?? firstLeg.airlineName ?? '航司未提供')}{' '}
            {String(flight.flightNo ?? firstLeg.flightNo ?? '')}
            {flight.shareFlight === true && <span className="flight-share-tag">共享</span>}
          </span>
          {aircraftName && (
            <span className="flight-card__meta-pipe">| {aircraftName}</span>
          )}
          {meal === true && (
            <span
              className="flight-card__meta-pipe flight-card__meal-pipe"
              title="含餐"
            >
              | <MealGlyph />
            </span>
          )}
          {meal === false && (
            <span
              className="flight-card__meta-pipe flight-card__meal-pipe"
              title="无餐"
            >
              | <MealGlyph muted />
            </span>
          )}
          <span className="flight-card__meta-pipe">| {routeTag}</span>
        </div>
      </button>
    </article>
  );
}

function MealGlyph({ muted }: { muted?: boolean }) {
  const color = muted ? '#c0c4cc' : '#fa8c16';
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 16 16"
      fill="none"
      stroke={color}
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2 11c1.5 1 3 1 4.5 0S9.5 10 11 11" />
      <path d="M2 13.5c1.5 1 3 1 4.5 0s3-1.5 4.5 0 3 1 4.5 0" />
      <path d="M11 3v8" />
      <path d="M11 3c1.5 0 2.5 1 2.5 2.5S12.5 8 11 8" />
    </svg>
  );
}

function CabinListBlock({
  item,
  submitted,
  onSubmit,
}: {
  item: AguiDataItem;
  submitted: boolean;
  onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void;
}) {
  const cabins = arrayOfRecords(item.dataJson?.cabins);
  const selectedFlight = asRecord(item.dataJson?.selectedFlight);
  const [activeTab, setActiveTab] = useState<'default' | 'economy' | 'business'>('default');

  const economyCount = cabins.filter((c) => /经济舱/.test(String(c.cabinName ?? c.cab ?? ''))).length;
  const businessCount = cabins.filter((c) => /公务舱|头等舱|商务舱/.test(String(c.cabinName ?? c.cab ?? ''))).length;

  const visibleCabins = (() => {
    if (activeTab === 'economy') {
      return cabins.filter((c) => /经济舱/.test(String(c.cabinName ?? c.cab ?? '')));
    }
    if (activeTab === 'business') {
      return cabins.filter((c) => /公务舱|头等舱|商务舱/.test(String(c.cabinName ?? c.cab ?? '')));
    }
    return cabins;
  })();

  const tabButton = (
    key: 'default' | 'economy' | 'business',
    label: string,
    count: number,
  ) => (
    <button
      type="button"
      key={key}
      className={`dagui-cabin-tab ${activeTab === key ? 'active' : ''}`}
      onClick={() => setActiveTab(key)}
      disabled={submitted}
    >
      {label}
      {count > 0 && key !== 'default' && <span className="dagui-cabin-tab-count">{count}</span>}
    </button>
  );

  return (
    <section className="dagui-section">
      {selectedFlight && (
        <div className="dagui-cabin-flight">
          {String(selectedFlight.depCityName ?? '')} → {String(selectedFlight.arrCityName ?? '')}
          <strong>{String(selectedFlight.flightNo ?? '')}</strong>
        </div>
      )}
      <div className="dagui-cabin-tabs">
        {tabButton('default', '默认舱位', cabins.length)}
        {tabButton('economy', '经济舱', economyCount)}
        {tabButton('business', '公务/头等舱', businessCount)}
      </div>
      <div className="dagui-list">
        {visibleCabins.length === 0 && (
          <div className="dagui-cabin-empty">该舱位类型暂无可选方案</div>
        )}
        {visibleCabins.map((cabin, index) => (
          <button
            type="button"
            key={String(cabin.cabId ?? index)}
            className="dagui-cabin-row"
            disabled={submitted}
            onClick={() => onSubmit({ cabId: String(cabin.cabId ?? ''), selectedCabin: cabin }, 'select_cabin')}
          >
            <div>
              <strong>¥{money(cabin.totalPrice ?? cabin.price)}</strong>
              <span>{String(cabin.cabinName ?? cabin.cab ?? '舱位')}</span>
              <small>{String(cabin.luggage ?? '')}</small>
            </div>
            <span className="dagui-seat">{seatText(cabin)}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

function OrderSummaryBlock({ item, onSubmit }: { item: AguiDataItem; onSubmit: (userInput: Record<string, unknown>, actionId?: string) => void }) {
  const order = item.dataJson ?? {};
  const summary = asRecord(order.flightSummary);
  const passengers = Array.isArray(order.passengerLines) ? order.passengerLines.map(String) : [];
  return (
    <section className="dagui-order-card">
      <div className="dagui-order-head">
        <span>订票单号：</span>
        <strong>{String(order.orderNo ?? order.orderId ?? '—')}</strong>
      </div>
      {summary && (
        <div className="dagui-order-flight">
          <span className="dagui-trip-tag">{String(order.tripTypeLabel ?? '单').slice(0, 1)}</span>
          <div>
            <strong>{[summary.depDate, summary.depTime, summary.airlineName, summary.flightNo].filter(Boolean).join(' ')}</strong>
            <span>{String(summary.depAirportName ?? summary.depCityName ?? '')} -- {String(summary.arrAirportName ?? summary.arrCityName ?? '')}</span>
          </div>
        </div>
      )}
      {passengers.map((line) => <div key={line} className="dagui-passenger">{line}</div>)}
      <div className="dagui-order-footer">
        <span>应付总额 <strong>¥{money(order.totalPrice)}</strong></span>
        <button type="button" className="dagui-primary-btn" onClick={() => onSubmit({ order, action: 'GO_PAY' }, 'GO_PAY')}>
          去支付
        </button>
      </div>
    </section>
  );
}


function buildFlightInput(flight: Record<string, unknown>, index: number): Record<string, unknown> {
  const legs = arrayOfRecords(flight.legs);
  const firstLeg = legs[0] ?? flight;
  return {
    flightId: String(flight.flightId ?? flight.flightNo ?? ''),
    flightNo: String(flight.flightNo ?? ''),
    serialNo: flight.serialNo ?? index + 1,
    selectedFlight: {
      depCityName: String(flight.depCityName ?? firstLeg.depCityName ?? ''),
      arrCityName: String(flight.arrCityName ?? firstLeg.arrCityName ?? ''),
      depDate: String(flight.depDate ?? firstLeg.depDate ?? ''),
      depTime: String(flight.depTime ?? firstLeg.depTime ?? ''),
      arrTime: String(flight.arrTime ?? firstLeg.arrTime ?? ''),
      airlineName: String(flight.airlineName ?? firstLeg.airlineName ?? ''),
      flightNo: String(flight.flightNo ?? firstLeg.flightNo ?? ''),
      airId: String(flight.airId ?? ''),
      lowestPrice: Number(flight.lowestPrice ?? flight.totalPrice ?? 0),
      lowestCabinName: String(flight.lowestCabinName ?? '经济舱'),
      durationMin: Number(flight.durationMin ?? flight.totalDuration ?? 0),
      stopCount: Number(flight.stopCount ?? 0),
      groupId: String(flight.groupId ?? ''),
      priceId: String(flight.priceId ?? ''),
      priceOptions: Array.isArray(flight.priceOptions) ? flight.priceOptions : [],
    },
  };
}

function formatFlightListSummary(value: Record<string, unknown> | null): string {
  if (!value) return '航班列表';
  return `共查询到${String(value.totalCount ?? 0)}个航班，最后筛选出${String(value.filteredCount ?? 0)}个`;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function arrayOfRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(asRecord(item))) : [];
}

function clock(value: unknown): string {
  const text = String(value ?? '');
  const match = text.match(/(\d{1,2}:\d{2})/);
  return match ? match[1] : '--:--';
}

function airport(row: Record<string, unknown>, side: 'dep' | 'arr'): string {
  const name = side === 'dep' ? row.depAirportName : row.arrAirportName;
  const terminal = side === 'dep' ? row.depTerminal : row.arrTerminal;
  return [name, terminal].filter(Boolean).join('') || '—';
}

function titleLine(flight: Record<string, unknown>, leg: Record<string, unknown>, fallback: string): string {
  const depDate = String(leg.depDate ?? flight.depDate ?? '');
  const date = depDate.replace(/^(\d{4})-(\d{2})-(\d{2}).*$/, '$2月$3日');
  const dep = String(flight.depCityName ?? leg.depCityName ?? '');
  const arr = String(flight.arrCityName ?? leg.arrCityName ?? '');
  return date && dep && arr ? `机票  ${date}  ${dep} - ${arr}` : fallback;
}

function airlineInitial(value: unknown): string {
  const text = String(value ?? '').trim();
  return text ? text[0] : '航';
}

function airlineLogo(airId: string): string | null {
  if (!airId || !/^[A-Z0-9]{2}$/.test(airId)) return null;
  return `https://crmapp.feiheair.com/airPic/${airId}.png`;
}

function duration(value: unknown): string {
  const minutes = Number(value);
  if (!Number.isFinite(minutes) || minutes <= 0) return '';
  const hours = Math.floor(minutes / 60);
  const remain = minutes % 60;
  if (hours > 0) return remain > 0 ? `${hours}h${remain}m` : `${hours}h`;
  return `${remain}m`;
}

function money(value: unknown): string {
  const amount = Number(value ?? 0);
  return Number.isFinite(amount) ? String(Math.round(amount)) : '—';
}

function seatText(cabin: Record<string, unknown>): string {
  const remain = cabin.remainSeats;
  if (typeof remain === 'number' && remain > 0) return `剩${remain}张`;
  return String(cabin.num ?? '') === 'A' ? '余票充足' : '';
}
