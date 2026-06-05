---
name: flight-query.iata_icao_codes
description: IATA 3 字码 / ICAO 4 字码 / 机场名 → 中文城市名翻译对照表。MCP `queryFlightBasic` 的 `departureCity` / `arrivalCity` 接受**用户原话**(中文优先,详见 skill 内 `tools/flight-mcp.json` 的字段说明)。本 skill 作为「用户说 IATA/ICAO/机场名 → LLM 翻成用户原话」的翻译辅助。父 skill `flight-query` 调用本子 skill 做翻译。
version: 2.0.0
allowed-tools: []
---

# IATA / ICAO 代码速查 (On-Demand) — 翻译辅助

> **加载时机**:父 skill `flight-query` 提示"详见 `flight-query:iata_icao_codes`"时;
> 或 LLM 遇到未识别城市 / 用户说 IATA/ICAO 码要翻译成中文时。
>
> **本文档不重复**:endpoint / 协议 / token 契约(见父 skill `flight-query` §1 §3 §4 §5)。
>
> **v2.0.0**:本表对齐父 skill 2.0.0 — 强调**先看父 skill §3 速查**(常用 11 城)**+ 命中再看本表全量**,避免 LLM 一上来就 load 整个表。

---

## 1. IATA vs ICAO 一句话区别

| | IATA | ICAO |
|---|---|---|
| 字数 | **3 字母** | **4 字母** |
| 制定方 | 国际航空运输协会(International Air Transport Association) | 国际民用航空组织(International Civil Aviation Organization) |
| 用途 | **客运系统标准**:机票/登机牌/航司显示 | **航空运行标准**:飞行计划/ATC 雷达/航管通信 |
| 例子(北京首都) | `PEK` | `ZBAA` |
| **MCP `queryFlightBasic` 接受** | ❌ **不**接受(要中文) | ❌ **不**接受(要中文) |

> **铁律**:**MCP 接口要"用户原话"中文**(如 `北京` `上海`),IATA/ICAO/机场名都需要先翻译成中文。
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
- 短名补 X:`DXB`(迪拜)、`LAX`(洛杉矶)

---

## 3. 国际常见目的地

| 城市 / 机场 | IATA | ICAO | 城市 / 机场 | IATA | ICAO |
|---|---|---|---|---|---|
| 东京羽田 | `HND` | `RJTT` | 东京成田 | `NRT` | `RJAA` |
| 大阪关西 | `KIX` | `RJBB` | 首尔仁川 | `ICN` | `RKSI` |
| 新加坡樟宜 | `SIN` | `WSSS` | 曼谷素万那普 | `BKK` | `VTBS` |
| 台北桃园 | `TPE` | `RCSS` | 香港 | `HKG` | `VHHH` |
| 伦敦希思罗 | `LHR` | `EGLL` | 巴黎戴高乐 | `CDG` | `LFPG` |
| 法兰克福 | `FRA` | `EDDF` | 阿姆斯特丹 | `AMS` | `EHAM` |
| 纽约肯尼迪 | `JFK` | `KJFK` | 洛杉矶 | `LAX` | `KLAX` |
| 旧金山 | `SFO` | `KSFO` | 芝加哥奥黑尔 | `ORD` | `KORD` |
| 多伦多 | `YYZ` | `CYYZ` | 温哥华 | `YVR` | `CYVR` |
| 悉尼 | `SYD` | `YSSY` | 墨尔本 | `MEL` | `YMML` |
| 迪拜 | `DXB` | `OMDB` | 新德里 | `DEL` | `VIDP` |
| 莫斯科谢列梅捷沃 | `SVO` | `UUEE` | 伊斯坦布尔 | `IST` | `LTFM` |

---

## 4. 模糊处理(用户原话解析不出唯一 IATA 码时)

### 4.1 场景表

| 场景 | 处理 |
|---|---|
| "东京"(有 HND/NRT 两个) | 主动问"东京是羽田(HND)还是成田(NRT)?" |
| "伦敦" / "巴黎" | 主动问"哪个机场?(LHR/LGW/CDG/ORY)" |
| "上海"(SHA/PVG) | 默认 SHA(虹桥,国内);用户说"国际 PVG" 改 PVG |
| "北京" 没说哪个机场 | 用 `BJS`(城市码),回复里注明"按 XX 城市搜索,具体机场以航司为准" |
| 用户给了中文全名("上海浦东国际机场") | 自动映射到 `PVG`,**不**追问 |
| 城市重名(中国/日本/美国都有"东京") | 主动澄清 |

### 4.2 完全未识别的城市

如果表里都没有(用户说"XX 机场"):
1. **不**瞎猜 IATA 码
2. 主动问:"请提供该机场的 IATA 三字代码,或城市全名我帮您查"
3. 用户给了城市全名 → 用 web 搜 / 临时表查询 → 找到 IATA 码 → 确认后调工具
4. 用户坚持不提供 → 终止本轮,告知"无法查询,请补充机场信息"

### 4.3 用户给的是 ICAO 码(罕见)

`ZBAA` 这种 4 字码:
1. 尝试用 IATA 对照表(本 skill §2)映射到 IATA
2. 映射成功 → 用 IATA 调工具
3. 映射失败 → 告知"暂不支持 ICAO 码,本接口只接受 IATA 3 字码,请提供对应 IATA 码"

---

## 5. 缓存建议(对调用方)

如果同一个会话内会查多个航班,**缓存**已查到的 IATA/ICAO 映射(写到 session 上下文),避免重复查表或问用户。

---

## 6. 版本与变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.4.0 | 2026-06-03 | 初版 |
| 1.5.0 | 2026-06-04 | 撤回"角色变更"错描述 — 本 skill 一直是翻译辅助 |
| **2.0.0** | 2026-06-04 | 对齐父 skill 2.0.0;§1 新增"常见场景"决策表(中文/IATA/机场名各对应什么);强调"先看父 skill §3 速查,再 load 本表全量" |
