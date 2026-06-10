// Scenario 中文名表 — 把后端返的 snake_case 名字翻成人话,用在 UI 显示.
// 真实场景下后端 YAML 里有中文 description,这里做客户端兜底,确保
// 即便后端 description 缺失也能显示得体.

const FRIENDLY: Record<string, { name: string; description: string }> = {
  flight_query: { name: '机票查询', description: '查实时航班 · 多维筛选' },
  flight_query_v3: { name: '机票查询 (v3)', description: 'opencode 原生 MCP 工具 · 实验' },
  flight_booking: { name: '机票预订', description: '差标合规 · 全程引导下单' },
  customer_service: { name: '客服助手', description: '订单咨询 · 退改签' },
  expense_audit: { name: '报销审核', description: '票据识别 · 差标核对' },
  code_review: { name: '代码审查', description: '静态分析 · 安全扫描' },
};

const DEFAULT = { name: '智能助手', description: '差旅 AI 调度中心' };

export function friendlyScenarioName(raw?: string | null): string {
  if (!raw) return DEFAULT.name;
  return FRIENDLY[raw]?.name ?? raw;
}

export function friendlyScenarioDescription(raw?: string | null): string {
  if (!raw) return DEFAULT.description;
  return FRIENDLY[raw]?.description ?? raw;
}

export function listUserPickableScenarios(): string[] {
  return Object.keys(FRIENDLY).filter((n) => !n.startsWith('_'));
}
