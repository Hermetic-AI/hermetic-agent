---
name: flight-query-v3.iata_icao_codes
description: IATA 3 字码 / ICAO 4 字码 / 机场名 → 中文城市名翻译对照表。MCP `queryFlightBasic` 工具的 `departureCity` / `arrivalCity` 入参接受**中文原话**(不接受 IATA/ICAO 码;opencode 加载 MCP server 时会把 `inputSchema` 注入 LLM context,LLM 自查)。本子 skill 作为"用户说 IATA/ICAO/机场名 → LLM 翻成中文原话"的翻译辅助。父 skill `flight-query-v3` 调用本子 skill 做翻译。
version: 3.0.0
allowed-tools: []
---

# IATA / ICAO 代码速查 (On-Demand) — 翻译辅助

> **加载时机**:父 skill `flight-query-v3` 提示"详见 `flight-query-v3:iata_icao_codes`"时;
> 或 LLM 遇到未识别城市 / 用户说 IATA/ICAO 码要翻译成中文时。
>
> **v3.0.0**:从 v2 子 skill `flight-query.iata_icao_codes` 照搬,只改 frontmatter 名称 + 删掉"详见 skill 内 `tools/flight-mcp.json`"的 v2 引用(本 skill 不再有内嵌工具 schema)。内容**完全等价**。

---

## 1. IATA vs ICAO 一句话区别

| | IATA | ICAO |
|---|---|---|
| 字数 | **3 字母** | **4 字母** |
| 制定方 | 国际航空运输协会(International Air Transport Association) | 国际民用航空组织(International Civil Aviation Organization) |
| 用途 | **客运系统标准**:机票/登机牌/航司显示 | **航空运行标准**:飞行计划/ATC 雷达/航管通信 |
| 例子(北京首都) | `PEK` | `ZBAA` |
| **MCP 工具 `queryFlightBasic` 接受** | ❌ **不**接受(要中文) | ❌ **不**接受(要中文) |

> **铁律**:**MCP 工具入参要"用户原话"中文**(如 `北京` `上海`),IATA/ICAO/机场名都需要先翻译成中文。
>
> **常见场景**:
> - 用户说"北京" → 直接 `北京`
> - 用户说"BJS" → 翻译成 `北京`(LLM 不区分 PEK/PKX — 城市码含全部机场)
> - 用户说"PEK"/"首都" → 翻译成 `北京`(同上)
> - 用户说"PVG"/"浦东" → 翻译成 `上海`
> - 用户说"虹桥" → 翻译成 `上海`(默认 SHA 城市码;如要 PVG 显式说"浦东")

---

## 2. 中国大陆机场(IATA 优先)

> 城市码 = IATA 协会给整座城市的代码(覆盖该城市所有机场);机场码 = 单一机场。

### 2.1 一线城市 + 直辖市

| 城市 | 城市码 | 机场码 | 机场名 | ICAO |
|---|---|---|---|---|
| 北京 | `BJS` | `PEK` / `PKX` | 首都 / 大兴 | `ZBAA` / `ZBAD` |
| 上海 | `SHA` | `SHA` / `PVG` | 虹桥 / 浦东 | `ZSSS` / `ZSPD` |
| 广州 | `CAN` | `CAN` | 白云 | `ZGGG` |
| 深圳 | `SZX` | `SZX` | 宝安 | `ZGSZ` |

### 2.2 省会 + 主要城市

| 城市 | IATA | 城市 | IATA | 城市 | IATA |
|---|---|---|---|---|---|
| 成都 | `CTU` | `ZUUU` ICAO | 杭州 | `HGH` | `ZSHC` |
| 重庆 | `CKG` | `ZUCK` | 西安 | `XIY` | `ZLXY` |
| 昆明 | `KMG` | `ZPPP` | 南京 | `NKG` | `ZSNJ` |
| 厦门 | `XMN` | `ZSAM` | 青岛 | `TAO` | `ZSQD` |
| 大连 | `DLC` | `ZYTL` | 沈阳 | `SHE` | `ZYTX` |
| 哈尔滨 | `HRB` | `ZYHB` | 长春 | `CGQ` | `ZYCC` |
| 武汉 | `WUH` | `ZHHH` | 长沙 | `CSX` | `ZGHA` |
| 郑州 | `CGO` | `ZHCC` | 济南 | `TNA` | `ZSJN` |
| 合肥 | `HFE` | `ZSOF` | 福州 | `FOC` | `ZSFZ` |
| 太原 | `TYN` | `ZBYN` | 兰州 | `LHW` | `ZLAN` |
| 贵阳 | `KWE` | `ZUGY` | 南宁 | `NNG` | `ZGNN` |
| 海口 | `HAK` | `ZJHK` | 三亚 | `SYX` | `ZJSY` |
| 乌鲁木齐 | `URC` | `ZWWW` | 拉萨 | `LXA` | `ZULS` |
| 呼和浩特 | `HET` | `ZBHH` | 银川 | `INC` | `ZLIC` |
| 西宁 | `XNN` | `ZLXN` | 澳门 | `MFM` | `VMMC` |
| 香港 | `HKG` | `VHHH` | 台北桃园 | `TPE` | `RCSS` |
| 台北松山 | `TSA` | `RCSS` | 高雄 | `KHH` | `RCKH` |

### 2.3 命名趣闻(扩展知识,非 MCP 必需)

- `CAN`(广州)来自旧英文 "Canton";`PEK`(北京)来自 "Peking"
- `HKG`(香港)、`HND`(东京羽田)、`LHR`(伦敦希思罗)是按城市/机场名缩写
- `ORD`(芝加哥奥黑尔)前身叫 "Orchard Field",代码保留,机场名改了纪念飞行员
- 加拿大 Y 开头(`YYZ` 多伦多、`YVR` 温哥华)源自早期气象站代码

---

## 3. 加载本子 skill 的触发条件(LLM 行为)

满足**任一**即加载本 skill:

1. 用户原话含 IATA 3 字母码(全大写且非中文城市名)
2. 用户原话含 ICAO 4 字母码
3. 用户说"XX 机场"但工具入参要"城市名"(`queryFlightBasic.departureCity`)
4. LLM 解析 OD 时不确定该用哪个中文名

**不**触发:

- 用户已用中文城市名(直接用,无需翻译)
- 用户说"附近机场"/"主城区"等模糊语 — 主动追问
- 已加载过本子 skill(用工作记忆即可,避免重复加载)

---

## 4. 翻译后行为

翻译完成后:

- LLM **直接**用中文城市名作 `queryFlightBasic.departureCity` / `.arrivalCity` 入参
- **不**保留 IATA 码(工具不接受)
- 翻译结果在后续轮次中保持(LLM 工作记忆,无需再加载本 skill)

---

## 5. 与 v2 子 skill 的差异

| 项 | v2 (`flight-query.iata_icao_codes`) | v3 (`flight-query-v3.iata_icao_codes`) |
|---|---|---|
| 内容(IATA/ICAO 对照表) | ✅ | ✅(照搬) |
| 父 skill 名引用 | `flight-query` | `flight-query-v3` |
| 指向 `tools/flight-mcp.json` | ✅(v2 skill 自带 tools/) | ❌(v3 不内嵌,改用 MCP 工具 `inputSchema`) |
| 其他 | — | 一致 |

> **本子 skill 的所有内容跟 v2 完全等价**,v3 复用同一张表,只改了 frontmatter + 引用说明。

---

**最后更新**:2026-06-05(从 v2 复制)
**父 skill**:`work/shared/skills/flight-query-v3/SKILL.md`
