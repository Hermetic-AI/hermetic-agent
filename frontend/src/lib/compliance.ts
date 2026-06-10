// 差旅政策 (差标) 合规判定 — 业务规则集中地,所有航班/订单显示共享.
//
// 政策来源: RulesPage.tsx 里硬编码的差标规则. 这里再编码一次,供
// FlightCard / FlightResultCard / OrderCard 等所有需要"是否合规"标
// 记的组件使用.
//
// 真实接入后会从后端拉 (L5 policy 引擎),届时把本文件直接换掉即可.

export type ComplianceLevel = 'ok' | 'warn' | 'over' | 'unknown';

export interface ComplianceVerdict {
  level: ComplianceLevel;
  /** 给用户看的一句话,例如 "超差 ¥240" / "近差标上限" / "差标内". */
  label: string;
  /** 鼠标悬停时更详细的解释. */
  tooltip: string;
}

/**
 * 经济舱机票价格上限为全价票的 75 折 (1 等舱 2 倍商务舱 3 倍).
 * 这里用简化的全价基准 (跟舱等强绑定),适用于演示数据.
 *
 * 真实生产应该:
 *   1. 接收 flight.fullPrice 字段 (Y 舱全价)
 *   2. 接收 employee.travelClass (员工差旅等级)
 *   3. 调 L5 policy 引擎
 */
const CAPS: Record<'economy' | 'business' | 'first', number> = {
  economy: 1500, // 全价 ~2000 的 75 折
  business: 4500,
  first: 9000,
};

/**
 * 判定一个航班是否在差标内.
 *
 * @param price       该舱位实际价 (含税前)
 * @param cabinClass  舱等
 * @param fullPrice   可选:Y 舱全价 (有就按比例算,没有就用 CAPS 兜底)
 */
export function checkCompliance(
  price: number,
  cabinClass: 'economy' | 'business' | 'first' | string,
  fullPrice?: number,
): ComplianceVerdict {
  if (price == null || isNaN(price)) {
    return {
      level: 'unknown',
      label: '差标未知',
      tooltip: '未能判定是否在差标内',
    };
  }

  let cap: number;
  let rule: string;
  if (fullPrice && fullPrice > 0) {
    const ratio: Record<string, number> = {
      economy: 0.75,
      business: 3,
      first: 5,
    };
    const r = ratio[cabinClass] ?? 0.75;
    cap = Math.round(fullPrice * r);
    rule = `全价 ¥${fullPrice} × ${r} = ¥${cap} (${labelOf(cabinClass)})`;
  } else {
    cap = CAPS[cabinClass as 'economy' | 'business' | 'first'] ?? 1500;
    rule = `${labelOf(cabinClass)} 差标上限 ¥${cap}`;
  }

  if (price <= cap * 0.9) {
    return {
      level: 'ok',
      label: '差标内',
      tooltip: `¥${price} ≤ ${rule}`,
    };
  }
  if (price <= cap) {
    return {
      level: 'warn',
      label: '近差标',
      tooltip: `¥${price} 接近 ${rule} (剩余 ¥${cap - price})`,
    };
  }
  const overage = price - cap;
  return {
    level: 'over',
    label: `超差 ¥${overage}`,
    tooltip: `¥${price} > ${rule} (超额 ¥${overage}, 需个人承担或审批)`,
  };
}

function labelOf(cabin: string): string {
  if (cabin === 'economy') return '经济舱';
  if (cabin === 'business') return '商务舱';
  if (cabin === 'first') return '头等舱';
  return cabin;
}

/**
 * 计算"差标命中率" — 给一个价格列表,统计差标内的占比.
 * 用来在 Welcome / 概览页显示 "近 30 天差标命中率 87%".
 */
export function complianceHitRate(
  items: Array<{ price: number; cabinClass: string; fullPrice?: number }>,
): { rate: number; total: number; ok: number; warn: number; over: number } {
  let ok = 0;
  let warn = 0;
  let over = 0;
  for (const it of items) {
    const v = checkCompliance(it.price, it.cabinClass, it.fullPrice);
    if (v.level === 'ok') ok++;
    else if (v.level === 'warn') warn++;
    else if (v.level === 'over') over++;
  }
  const total = items.length;
  const rate = total === 0 ? 1 : (ok + warn * 0.5) / total;
  return { rate, total, ok, warn, over };
}
