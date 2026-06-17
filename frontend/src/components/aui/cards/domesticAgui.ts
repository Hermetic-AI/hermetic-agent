import type { CardDescriptor } from '../../../types';

export interface AguiDataItem {
  basicType: string;
  dataStr: string;
  dataJson: Record<string, unknown> | null;
  linkUrl: string;
}

export interface AguiTurn {
  sceneId?: string;
  reason?: string;
  contentJson: {
    schemaVersion?: string;
    dataList?: AguiDataItem[];
    thinkingSteps?: string[];
  };
}

export function hasDomesticAgui(card: CardDescriptor): boolean {
  return Boolean(extractAguiTurn(card));
}

export function extractAguiTurn(card: CardDescriptor): AguiTurn | null {
  const body = (card.body ?? {}) as Record<string, unknown>;
  const candidates = [body.agui, body.contentJson, body, card.agui, card.contentJson, card];
  for (const candidate of candidates) {
    const turn = normalizeAguiCandidate(candidate);
    if (turn) return turn;
  }
  // 兜底: 老 AUIP body = {summary, plans:[{flights:[…]}]} 在前端现场合成 AGUI v2.
  // 后端 ask_user 拦截层会优先尝试这个翻译, 但容器里如果还是老代码, 这里兜一次.
  const synthesized = synthesizeFromLegacyAuipBody(body);
  if (synthesized) {
    return {
      contentJson: {
        schemaVersion: '2',
        dataList: synthesized,
        thinkingSteps: [],
      },
    };
  }
  return null;
}

function synthesizeFromLegacyAuipBody(body: Record<string, unknown>): AguiDataItem[] | null {
  const plans = body.plans;
  if (!Array.isArray(plans) || plans.length === 0) return null;
  const flights: Array<Record<string, unknown>> = [];
  for (const plan of plans) {
    if (!plan || typeof plan !== 'object') continue;
    const planFlights = (plan as Record<string, unknown>).flights;
    if (!Array.isArray(planFlights)) continue;
    for (const flight of planFlights) {
      if (flight && typeof flight === 'object') {
        flights.push(flight as Record<string, unknown>);
      }
    }
  }
  if (flights.length === 0) return null;
  const summary = (body.summary as Record<string, unknown> | undefined) ?? {};
  const total = Number(summary.totalCount ?? flights.length) || flights.length;
  const filtered = Number(summary.filteredCount ?? flights.length) || flights.length;
  const dataStr = `共查询到${total}个航班，最后筛选出${filtered}个`;
  return [
    {
      basicType: 'AIR_DOMESTIC_FLIGHT_LIST',
      dataStr,
      dataJson: {
        serialNumber: '',
        totalCount: total,
        filteredCount: filtered,
        flightList: flights.map(auipFlightToAgui),
      },
      linkUrl: '',
    },
  ];
}

function auipFlightToAgui(flight: Record<string, unknown>): Record<string, unknown> {
  const airline = (flight.airline as Record<string, unknown> | undefined) ?? {};
  const departure = (flight.departure as Record<string, unknown> | undefined) ?? {};
  const arrival = (flight.arrival as Record<string, unknown> | undefined) ?? {};
  const departureTime = String(departure.time ?? '');
  const arrivalTime = String(arrival.time ?? '');
  const departureDate = String(flight.date ?? extractDate(departureTime));
  const arrivalDate = extractDate(arrivalTime) || departureDate;
  const departureAirport = String(departure.airport ?? '');
  const arrivalAirport = String(arrival.airport ?? '');
  return {
    depCityName: '',
    arrCityName: '',
    depDate: departureDate,
    lowestPrice: Number(flight.price ?? flight.fullPrice ?? 0) || 0,
    lowestCabinName: 'ECONOMY',
    totalPrice: Number(flight.fullPrice ?? flight.price ?? 0) || 0,
    totalDuration: Number(flight.duration ?? 0) || 0,
    durationMin: Number(flight.duration ?? 0) || 0,
    stopCount: Number(flight.stops ?? 0) || 0,
    transferCount: 0,
    transferCities: [],
    airlineName: String(airline.name ?? ''),
    flightNo: String(flight.flightNo ?? ''),
    airId: String(airline.code ?? '').toUpperCase(),
    tripType: 'OW',
    serialNo: Number(flight.serialNo ?? 0) || 0,
    flightId: String(flight.flightId ?? flight.flightNo ?? ''),
    legs: [],
    depTime: extractTime(departureTime),
    depAirportName: departureAirport,
    depTerminal: String(departure.terminal ?? ''),
    shareFlight: Boolean(flight.shareFlight),
    shareId: String(flight.shareInfo ?? ''),
    arrDate: arrivalDate,
    arrTime: extractTime(arrivalTime),
    arrAirportName: arrivalAirport,
    arrTerminal: String(arrival.terminal ?? ''),
    arrDayOffset: 0,
  };
}

function extractDate(value: string): string {
  const match = value.match(/(\d{4}-\d{2}-\d{2})/);
  return match ? match[1] : '';
}

function extractTime(value: string): string {
  const match = value.match(/(\d{1,2}:\d{2})/);
  return match ? match[1] : '';
}

function normalizeAguiCandidate(value: unknown): AguiTurn | null {
  const record = asRecord(value);
  if (!record) return null;
  const envelopeData = asRecord(record.data);
  if (envelopeData) return normalizeAguiCandidate(envelopeData);
  const contentJson = asRecord(record.contentJson) ?? (Array.isArray(record.dataList) ? record : null);
  if (!contentJson || contentJson.schemaVersion !== '2' || !Array.isArray(contentJson.dataList)) return null;
  return {
    sceneId: stringOrUndefined(record.sceneId),
    reason: stringOrUndefined(record.reason),
    contentJson: contentJson as AguiTurn['contentJson'],
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function stringOrUndefined(value: unknown): string | undefined {
  if (value == null) return undefined;
  const text = String(value);
  return text ? text : undefined;
}
