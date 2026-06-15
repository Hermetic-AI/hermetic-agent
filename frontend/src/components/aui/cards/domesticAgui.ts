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
  const candidates = [card.body?.agui, card.body?.contentJson, card.body, card.agui, card.contentJson, card];
  for (const candidate of candidates) {
    const turn = normalizeAguiCandidate(candidate);
    if (turn) return turn;
  }
  return null;
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
