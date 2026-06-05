# plan_rules.md — backend 用, LLM **不要**读

> **目的**:v3 让 LLM 自己设计"3 方案"分组 (耗时 1-2s), v4 把这步固化为 backend 函数,
> LLM 只传 `plan_kind` 枚举, backend 1ms 生成完整 `plans[]`。
>
> **LLM 看到的是 `plan_kind: "default"`**; **backend 调用** `_build_plans(flightList, plan_kind)`
> 拿回 `[{id, title, subtitle, criteria, flights}, ...]`。

## 1. plan_kind 枚举

| plan_kind | 生成方案数 | 排序维度 | 适用场景 |
|---|---|---|---|
| `default` | 3 | fastest + cheapest + comfortable | 用户没表态时**永远默认这个** |
| `cheapest` | 1 | `lowestPrice` 升序, 取 top 3 | 用户说"最便宜/划算/便宜" |
| `fastest` | 1 | `totalDuration` 升序 (HH:MM parse), 取 top 3 | 用户说"最快/赶时间" |
| `comfortable` | 1 | `stopCount=0` 优先 + 大机型优先 (aircraftName 包含 "747"/"777"/"787"/"A350"/"A380") | 用户说"要大飞机/舒适/直飞" |
| `user_explicit` | 1 | 取 `flightList[0]` (LLM 已经替用户选过) | 用户已说"挑第一个/这个" |

## 2. 方案结构 (1 个 plan)

```json
{
  "id": "fastest",
  "title": "最快抵达",
  "subtitle": "用时最短",
  "criteria": "duration",
  "flights": [FlightSegment, FlightSegment, FlightSegment]
}
```

- `id`: 枚举 `fastest` / `cheapest` / `comfortable` / `recommended`
- `title`: 中文标题, 与 plan_kind 对应
- `subtitle`: 副标题
- `criteria`: 排序维度 key, 给前端做二次排序用
- `flights`: top-3 个 FlightSegment (FlightSegment 结构见 §3)

## 3. FlightSegment 字段映射 (MCP flightList[i] → AUIP flights[i])

> **这是 backend 的翻译表, LLM 永远不直接填 flights[].** 后端 `_flight_to_auip(raw, idx)` 函数负责 1:1 转换。

| AUIP 字段 | 来源 (MCP `flightList[i]`) | 必填 | 备注 |
|---|---|---|---|
| `flightId` | `flightId` (顶层) | ✅ | 主键 |
| `flightNo` | `flightNo` | ✅ | 显示 |
| `shareFlight` | `shareFlight` (顶层) | ✅ | bool |
| `shareInfo` | `"共享" + legs[0].airlineName` (当 shareFlight=true) | ❌ | null when 直飞 |
| `airline.code` | `airId` (顶层) | ✅ | "CA"/"MU" |
| `airline.name` | `legs[0].airlineName` | ✅ | "中国国际航空" |
| `aircraft` | `legs[0].aircraftName` 去 "(大)/(中)/(小)" 后缀 | ✅ | "波音 737" |
| `date` | `depDate` (顶层) | ✅ | yyyy-MM-dd |
| `departure.city` | 查表 (depAirportCode → 城市名) | ✅ | "北京" |
| `departure.airport` | `legs[0].depAirportName` | ✅ | "首都国际机场" |
| `departure.airportCode` | `depAirportCode` (顶层) | ✅ | "PEK" |
| `departure.terminal` | `legs[0].depTerminal` | ❌ | "T3"/null |
| `departure.time` | `legs[0].depTime` | ✅ | HH:MM |
| `arrival.*` | 同上, 用 `arrAirportCode`/`legs[0].arr*` | ✅ | 对称 |
| `duration` | `totalDuration` | ✅ | "2h20m" |
| `stops` | `stopCount` | ✅ | 0 = 直飞 |
| `cabin` | `lowestCabinName` | ✅ | "经济舱" |
| `cabinClass` | `lowestCabinName` → 枚举 (经济/经济+→公务→头等) | ❌ | ECONOMY/BUSINESS/FIRST |
| `meal` | `legs[0].meal` (bool) → "是"/"否" | ❌ | 也可保留中文 |
| `price` | `lowestPrice` | ✅ | 数字(元) |
| `fullPrice` | `fullPrice` (顶层) | ❌ | 全价票面价 |
| `tags` | 派生 | ❌ | 例 ["最便宜", "1h55m ⚡"] |

## 4. 字段映射实现策略 (backend `_flight_to_auip`)

```python
def _flight_to_auip(raw: dict, idx: int) -> dict:
    """MCP flightList[idx] → AUIP FlightSegment. LLM 不可见."""
    leg = (raw.get("legs") or [{}])[0]
    cabin = raw.get("lowestCabinName", "")
    cabin_class = "ECONOMY"
    if "公务" in cabin or "商务" in cabin:
        cabin_class = "BUSINESS"
    elif "头等" in cabin or "一等" in cabin:
        cabin_class = "FIRST"
    elif "超经" in cabin or "高级" in cabin:
        cabin_class = "PREMIUM_ECONOMY"
    aircraft = (leg.get("aircraftName") or "").replace("(大)", "").replace("(中)", "").replace("(小)", "").strip()
    meal = leg.get("meal")
    meal_str = "是" if meal is True else ("否" if meal is False else None)
    return {
        "flightId": raw.get("flightId", f"idx-{idx}"),
        "flightNo": raw.get("flightNo", ""),
        "shareFlight": raw.get("shareFlight", False),
        "shareInfo": f"共享{leg.get('airlineName', '')}" if raw.get("shareFlight") else None,
        "airline": {"code": raw.get("airId", ""), "name": leg.get("airlineName", "")},
        "aircraft": aircraft,
        "date": raw.get("depDate", ""),
        "departure": {
            "city": _airport_to_city(raw.get("depAirportCode", "")),
            "airport": leg.get("depAirportName", ""),
            "airportCode": raw.get("depAirportCode", ""),
            "terminal": leg.get("depTerminal"),
            "time": leg.get("depTime", ""),
        },
        "arrival": {
            "city": _airport_to_city(raw.get("arrAirportCode", "")),
            "airport": leg.get("arrAirportName", ""),
            "airportCode": raw.get("arrAirportCode", ""),
            "terminal": leg.get("arrTerminal"),
            "time": leg.get("arrTime", ""),
        },
        "duration": raw.get("totalDuration", ""),
        "stops": raw.get("stopCount", 0),
        "cabin": cabin,
        "cabinClass": cabin_class,
        "meal": meal_str,
        "price": raw.get("lowestPrice", 0),
        "fullPrice": raw.get("fullPrice"),
        "tags": _derive_tags(raw),
    }
```

## 5. tags 派生规则 (后端生成, LLM 不可见)

| 触发条件 | tag |
|---|---|
| 当前方案中 `lowestPrice` 最小 | "最便宜" |
| 当前方案中 `totalDuration` 最短 | "最快" |
| `stopCount=0` + `aircraftName` 含 "747"/"777"/"787"/"A350"/"A380" | "大飞机直飞" |
| `lowestPrice < fullPrice * 0.7` | "省 30%+" |
| `legs[0].meal=true` | "含餐" |
| `depTime` 在 06:00-12:00 | "早班" |
| `depTime` 在 18:00-24:00 | "晚班" |

每个 flight 最多 3 个 tag, 优先 `最便宜` / `最快` / `大飞机直飞`, 其它按出现顺序补到 3 个。

## 6. 边界

- `flightList=[]` → 推 `CANNOT_ORDER`, **不**生成 plans
- `flightList.length < 3` → 1 个方案 `id="recommended"`, 全部塞进 `flights[]`
- 任何 sort/filter 错误 (空 cabinName 等) → fallback 到 `default` 方案, 不报错
