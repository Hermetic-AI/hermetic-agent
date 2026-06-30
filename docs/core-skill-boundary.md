# hermetic-agent — Core vs Skill Boundary Contract

> 项目的核心约束。`hermetic-agent` 本身只做"调度 / 通信 / 状态 / 通用技术基座"，所有业务能力（机票、订单、报表、CRM 等）一律下沉到 SKILL 层。
>
> 任何对 `src/hermetic_agent/` 的修改必须遵守本文定义。CI 层 `scripts/ci_check.py` 后续扩展可机器校验本文中的"禁词清单"。

---

## 1. 5 层架构中的"基座 vs 业务"边界

```
L1 api/              ← 基座：HTTP 协议 + SSE 流化 + 错误码
L2 scenarios/        ← 基座：路由 + YAML 加载 + 通用 placeholder 解析
                       业务：scenario YAML 本身在 work/ 下，不入 src/
L3 skill_runtime/    ← 基座：SkillRegistry / FragmentLoader / Manifest / PromptBuilder
   auip/             ← 基座：Card / TurnEvent / CardRenderer 接口协议（无业务实现）
                       业务：每个具体 card_type 的渲染逻辑下沉至 SKILL
   core/             ← 基座：Scheduler / SuspendableScheduler / TurnStore
L4 providers/        ← 基座：opencode SDK 适配 + Provider 抽象
                       业务：MCP tool 名 / token push 等运行时由 SKILL manifest 声明
L5 policy/ store/    ← 基座：安全策略 + 持久化
   audit/
   config/           ← 基座：通用技术配置（无业务字段）
   sandbox/
```

---

## 2. 基座（`src/hermetic_agent/`）允许的关键词白名单

基座代码允许出现的关键词（通用概念，不构成业务绑定）：

| 类别 | 白名单关键词 | 备注 |
|------|-------------|------|
| 协议 | `card`、`tool`、`mcp`、`session`、`turn`、`agent`、`skill` | 通用协议名词 |
| 类型 | `text`、`reasoning`、`tool_use`、`tool_result`、`state` | TurnEvent 枚举值 |
| 字段 | `card_id`、`card_type`、`body`、`fields`、`options`、`actions` | 通用 Card schema |
| 系统 | `opencode`、`claude_code`、`sanic`、`httpx`、`mcp` | 技术栈相关 |
| 业务实现 | `_default`、`example` | 用于 example/兜底场景，不入具体业务名 |

---

## 3. 基座禁止出现的关键词黑名单

基座代码（`src/hermetic_agent/**/*.py`）严禁出现以下词汇（不区分大小写、词形变化）：

```python
# 业务-业务（具体产品/行业）
FLIGHT_KEYWORDS = {
    "flight", "airline", "aircraft", "airport", "cabin", "passenger",
    "booking", "ticket", "itinerary", "fare", "departure", "arrival",
    "baggage", "refund", "reroute", "iata", "icao", "tsa",
}

# 业务-租户（特定企业/项目代号）
TENANT_KEYWORDS = {
    "feihe", "feiheair", "fh_", "_feihe",  # 飞鹤
    "crmdev", "traveldev",
    "fh-domestic", "fh-international",
}

# 业务-API（特定业务系统）
BUSINESS_API_KEYWORDS = {
    "queryFlightBasic", "intShopping", "findPassenger", "saveOrder",
    "chooseFlight", "chooseCabin", "listTripApplications", "buildOrderPreview",
    "getFlightPolicyInfo", "recordPolicyUserDecision", "fillPassenger",
    "validateBookingInfo", "listCostCenters", "bindCostCenter",
    "getDefaultContact", "getOrderDetail", "resetBookingSession",
    "logonV2", "getGraphicsCaptcha",
}
```

**注**：
- `src/hermetic_agent/.skills/`（如有）允许包含业务 SKILL demo，但 CI 应默认排除此目录
- `tests/` 与 `work/` 不在 `src/hermetic_agent/` 范围内，外部清理在本阶段单独处理
- 例外条款（`KNOWN_VIOLATIONS` 豁免）：仅在 Phase 1 收尾时一次性消化，**新增代码不允许再列豁免**

---

## 4. SKILL 侧的完整职责清单

每个业务 SKILL（位于 `work/shared/skills/<skill-name>/`）可自由实现以下内容：

### 4.1 场景定义（scenario YAML）

```yaml
# work/scenarios/<scenario-name>.scenario.yaml
name: <scenario-name>
version: "1.0.0"
description: "..."

# 业务系统提示词（基座不会解读，仅注入 LLM system_prompt）
system_prompt: |
  你是 <业务领域> 助手...
  ...业务专属指令...

# 业务工具声明（基座在 opencode request 里启用这些 tool）
tools:
  - <tool_name_1>
  - <tool_name_2>

# 业务环境变量（Hub → opencode 容器的 env.runtime）
env:
  BUSINESS_API_KEY: "${BUSINESS_API_KEY}"
  BUSINESS_API_BASE: "${BUSINESS_API_BASE}"

# 引用的 SKILL 列表
skills:
  - <skill-name>

# 资源目录（占位符 ${PROJECT_DIR} / ${WORK_ROOT} 等的解析基准）
resource_dirs:
  - "${WORK_SHARED}/skills/<skill-name>"
```

### 4.2 SKILL 包结构

```
work/shared/skills/<skill-name>/
├── SKILL.md              # 必需：frontmatter + 业务 prompt
├── skill.yaml            # 必需：业务工具/环境变量声明
├── card_renderers/       # 可选：业务 CardRenderer 实现
│   ├── __init__.py       #     RendererRegistry 注册入口
│   └── <card_type>.py
├── message_rewriters/    # 可选：业务 MessageRewriter 实现
│   ├── __init__.py
│   └── <tool_name>.py
├── tests/                # 可选：SKILL 单元测试
│   └── test_<feature>.py
├── agents/               # 可选：opencode 场景级 agent 配置
├── references/           # 可选：业务参考文档
├── schemas/              # 可可选：业务 JSON Schema
├── scripts/              # 可可选：业务辅助脚本
└── workflows/            # 可可选：业务工作流
```

### 4.3 CardRenderer 协议（基座定义，SKILL 实现）

```python
# 基座：src/hermetic_agent/auip/renderer.py
from typing import Protocol
from hermetic_agent.auip.events import TurnEvent
from hermetic_agent.auip.cards import Card

class CardRenderer(Protocol):
    """业务 SKILL 实现的卡片渲染器协议.

    基座在 tool_result 事件发生时, 按 tool_name 路由到对应 Renderer.
    Renderer 决定:
      1. 自己能不能处理这个 tool_result (can_render)
      2. 怎么把 tool_result 数据转换成 Card (render)
    """

    def tool_names(self) -> set[str]:
        """声明本 Renderer 关注的 tool name 集合.
        基座用此做路由: 收到 tool_result 时, 找匹配 tool 的 Renderer."""
        ...

    def can_render(self, event: TurnEvent, context: dict) -> bool:
        """快速判断: 这个事件我能渲染吗? (数据完整性 / 状态等)"""
        ...

    def render(self, event: TurnEvent, context: dict) -> Card | None:
        """从 event 数据 + context 构造一张 Card. 失败返 None."""
        ...
```

```python
# SKILL 侧：work/shared/skills/<skill-name>/card_renderers/domestic_flight.py
from hermetic_agent.auip.cards import Card
from hermetic_agent.auip.renderer import CardRenderer

class DomesticFlightCardRenderer:
    def tool_names(self) -> set[str]:
        return {"<mcp-server>_<tool>", "..."}  # 业务工具名

    def can_render(self, event, context):
        output = event.data.get("output")
        return isinstance(output, (dict, str)) and self._parse(output) is not None

    def render(self, event, context):
        output = self._parse(event.data.get("output"))
        if not output:
            return None
        flight_list = output.get("flightList") or []
        if not flight_list:
            return None
        # ... 业务渲染逻辑 ...
        return Card(card_type=CardType.FLIGHT_RESULT, ...)
```

```python
# SKILL 侧：work/shared/skills/<skill-name>/card_renderers/__init__.py
from .domestic_flight import DomesticFlightCardRenderer
from hermetic_agent.auip.renderer import CardRendererRegistry

# SKILL 启动时注册 (基座扫描 SKILL 包时自动调用)
def register_renderers(registry: CardRendererRegistry) -> None:
    registry.register(DomesticFlightCardRenderer())
```

### 4.4 MessageRewriter 协议（基座定义，SKILL 实现）

```python
# 基座：src/hermetic_agent/auip/rewriter.py
from typing import Protocol
from hermetic_agent.providers.streaming import StreamEvent

class MessageRewriter(Protocol):
    """把 card-submit 类的 user message 改写成自然语言.

    LLM 不知道 AUIP 协议. 业务 SKILL 注册 Rewriter, 在 LLM 看到 user message
    前把表单数据 'card_submission: {flightId: "..."}' 改写成
    '我选择 CA1234 这班航班.'. 这样 LLM 才能用自然语言继续对话.
    """

    def tool_names(self) -> set[str]:
        """声明本 Rewriter 关注的 tool name 集合."""
        ...

    def rewrite(self, event: StreamEvent, context: dict) -> StreamEvent | None:
        """返回改写后的 event, 或 None 表示不处理."""
        ...
```

### 4.5 SKILL manifest 中的环境变量声明

```yaml
# work/shared/skills/<skill-name>/skill.yaml
name: <skill-name>
version: "1.0.0"

# 业务需要 Hub 注入到 opencode 容器的 env
# Hub 在每个 chat 之前会调 :7778/admin/env 写入, 然后 reload
required_envs:
  BUSINESS_API_KEY:
    source: env  # 从 process env 读
    env_name: BUSINESS_API_KEY
  # 或：
  #   source: file  # 从文件读
  #   path: /app/work/secrets/<skill-name>/api_key
  #   format: raw | base64

# 业务用到的 MCP 工具
mcp_tools:
  <mcp-server-name>:
    tools: [tool_a, tool_b, tool_c]
```

---

## 5. 基座不负责的事

以下内容**永远不应**在 `src/hermetic_agent/` 出现：

- 具体业务的 API 调用代码（HTTP client 调用业务后端）
- 具体业务的数据转换（航班数据、订单数据、报表数据等）
- 具体业务的字段映射（cabin class、aircraft size 等业务枚举）
- 具体业务的 UI 卡片组装（即使 CardType 是基座定义的，组装内容由 SKILL 实现）
- 具体业务的环境变量名（如 `FLIGHT_API_KEY` 应改为 `BUSINESS_API_KEY` 或 `MYAPP_TOKEN`）
- 具体业务的配置字段（基座 `config/settings.py` 严禁出现 `feihe_*` / `flight_*` 等）

---

## 6. 业务耦合度检测（CI 集成）

`scripts/ci_check.py` 扩展点（计划在 Phase 1 收尾时实现）：

```python
# 伪代码
def check_business_keywords(file_path: Path) -> list[Violation]:
    """扫描 src/hermetic_agent/ 下的 .py 文件, 检测黑名单关键词.
    仅检查 .py 文件 (不查 yaml / md / json), 避免误报.
    例外: __init__.py 文件, 因为它通常只 re-export.
    """
    ...
```

**触发失败**：任何基座模块引用了黑名单词汇，CI 直接 fail。

**例外**：通过 `KNOWN_VIOLATIONS` 列表豁免（Phase 1 收尾时**一次性消化**已有违规，新增代码不允许再豁免）。

---

## 7. 迁移路线图

| 阶段 | 操作 | 基座关键字黑名单生效范围 |
|------|------|------------------------|
| Phase 1 POC | AUIP 层业务模块移除 + 新 SKILL 包创建 | 部分生效（AUIP 目录） |
| Phase 1 完成 | config + providers + scenario 全部净化 | 全量生效 |
| Phase 2 | opencode SDK 深度集成（业务零侵入） | 全量生效 |
| Phase 3+ | SKILL 体系 + 文档 | 基座无新增业务词 |

---

## 8. 总结

**一句话**：基座只懂"通用协议"，业务 SKILL 负责"业务实现"。两者通过本文定义的 `CardRenderer` / `MessageRewriter` 协议 + SKILL manifest YAML 解耦。

违反本文的任何代码修改，都应被 PR review 拒掉。
