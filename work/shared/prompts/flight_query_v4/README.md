# flight_query_v4 prompts 目录

> 配合 `flight_query-v4` skill, **预编译的 prompt 模板**由 backend 注入, 不让 LLM 现场拼.

## 1. 模板清单

| 文件 | 用途 | 谁用 |
|---|---|---|
| `system_prompt.j2` | scenario `execution.system_prompt` 字段 (注入到 LLM system 消息) | backend `prompt_builder` |
| `query_skeleton.j2` | `ask_user.ASK_QUERY` 卡片提交后, 把用户填表内容转回 `Query` JSON | backend (HITL path) |
| `card_skeleton.j2` | 极简版 `ask_user.FLIGHT_RESULT` 提示, LLM 一眼懂 (不再 273 行) | backend (LLM 提示) |

> 模板由 backend Jinja2 渲染, **不**用 LLM 自己拼 — LLM 只填 Query, 模板填 UI.

## 2. system_prompt.j2 (示意)

```jinja2
你是飞鹤机票查询 AI 助手 (v4).
严格遵循 3 步固定流程, **不**要发散:
1. PARSE — 用户原话转 Query JSON
2. CALL — 调 queryFlightBasic MCP 工具
3. CARD — 调 ask_user, 缺字段推 ASK_QUERY, 有结果推 FLIGHT_RESULT (plan_kind+flightList 原样), 错/空推 CANNOT_ORDER

严禁:
- 自己编 plans[] / flights[] 字段 (backend 用 plan_rules.md 自动生成)
- 改 OD/日期/舱等后调 filterFlightList 做客户端过滤
- 在 chat text 里发整张 Markdown 表
- 选舱/填人/核价/下单 (走 flight-booking skill)

技能:
{{ skill_chunks | join('\n\n') }}
```

> 实际 `system_prompt` 已经在 `work/scenarios/flight_query_v4.scenario.yaml` 里写死, **不**用 jinja 渲染 (避免 LLM 看到的 prompt 跟 scenario 描述对不上).

## 3. card_skeleton.j2 (ASK_QUERY 提交后 → 重新调 queryFlightBasic)

```jinja2
{#
  用户提交 ASK_QUERY 卡片后, backend 拿到表单内容, 用这个模板生成新的 Query JSON,
  再调 queryFlightBasic.

  输入: form_data = {"origin": "北京", "destination": "上海", "departDate": "2026-06-10", "cabin": "ECONOMY"}
  输出: MCP queryFlightBasic 入参
#}
{
  "departureCity": "{{ form_data.origin }}",
  "arrivalCity": "{{ form_data.destination }}",
  "departDate": "{{ form_data.departDate }}",
  {% if form_data.returnDate %}
  "returnDate": "{{ form_data.returnDate }}",
  {% endif %}
  "cabin": "{{ form_data.cabin | default('ECONOMY') }}",
  "searchType": "全量查询",
  "passengerCount": 1
}
```

> 模板由 backend 渲染, LLM **不**参与. ASK_QUERY → 自动重调 queryFlightBasic → 推 FLIGHT_RESULT.

## 4. 与 v3 的差异

| 项 | v3 | v4 |
|---|---|---|
| prompt 模板数 | 5+ (`system_prompt.j2` / `card_skeleton.j2` / 各种 chat 模板) | 3 (减 40%) |
| LLM 现场拼 prompt | ✅ (SKILL.md 教 LLM 怎么拼) | ❌ (backend 预编译) |
| LLM 看 system_prompt 时长 | 5-10s 解析 | 1-2s 解析 (system_prompt 极简) |

---

**最后更新**:2026-06-05
**对应 skill**:`work/shared/skills/flight-query-v4/SKILL.md`
**对应 scenario**:`work/scenarios/flight_query_v4.scenario.yaml`
