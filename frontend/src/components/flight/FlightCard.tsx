import type { Flight } from '../../types';
import { Button, Badge } from '../common';
import { checkCompliance } from '../../lib';
import '../../lib/compliance.css';
import './FlightCard.css';

interface FlightCardProps {
  flight: Flight;
  onSelect?: (flight: Flight) => void;
  selected?: boolean;
}

export function FlightCard({ flight, onSelect, selected = false }: FlightCardProps) {
  const compliance = checkCompliance(flight.price, flight.cabinClass);
  return (
    <div className={`flight-card ${selected ? 'flight-card-selected' : ''}`}>
      <div className="flight-card-header">
        <div className="flight-airline">
          <AirlineLogo code={flight.airlineCode} />
          <span className="airline-name">{flight.airline}</span>
          <Badge variant="default">{flight.flightNumber}</Badge>
        </div>
        <div className="flight-header-right">
          <ComplianceBadge compliance={compliance} />
          <div className="flight-price">
            <span className="price-symbol">¥</span>
            <span className="price-value">{flight.price}</span>
          </div>
        </div>
      </div>

      <div className="flight-card-body">
        <div className="flight-time-block">
          <span className="time-main">{flight.departure.time}</span>
          <span className="time-sub">{flight.departure.airportCode}</span>
        </div>

        <div className="flight-duration">
          <div className="duration-line">
            <span className="duration-dot" />
            <span className="duration-line-segment" />
            <AirplaneMiniIcon />
          </div>
          <span className="duration-text">{flight.duration}</span>
          <div className="duration-line">
            <span className="duration-dot" />
            <span className="duration-line-segment" />
          </div>
        </div>

        <div className="flight-time-block">
          <span className="time-main">{flight.arrival.time}</span>
          <span className="time-sub">{flight.arrival.airportCode}</span>
        </div>
      </div>

      <div className="flight-card-footer">
        <div className="flight-info">
          <span className="info-item">舱位: {getCabinLabel(flight.cabinClass)}</span>
          <span className="info-item">余票: {flight.remainingSeats}</span>
        </div>
        {onSelect && (
          <Button size="small" onClick={() => onSelect(flight)}>
            选择
          </Button>
        )}
      </div>
    </div>
  );
}

function ComplianceBadge({ compliance }: { compliance: ReturnType<typeof checkCompliance> }) {
  return (
    <span
      className={`compliance-badge compliance-${compliance.level}`}
      title={compliance.tooltip}
    >
      {compliance.label}
    </span>
  );
}

function getCabinLabel(cabin: Flight['cabinClass']): string {
  const labels = {
    economy: '经济舱',
    business: '商务舱',
    first: '头等舱'
  };
  return labels[cabin];
}

function AirlineLogo({ code }: { code: string }) {
  return (
    <div className="airline-logo">
      <span>{code.slice(0, 2)}</span>
    </div>
  );
}

function AirplaneMiniIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="#4A9BE8" stroke="none">
      <path d="M21 16v-2l-8-5V3.5a1.5 1.5 0 0 0-3 0V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z" />
    </svg>
  );
}
