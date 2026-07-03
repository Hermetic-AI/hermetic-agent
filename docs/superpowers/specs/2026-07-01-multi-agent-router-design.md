# Multi-Agent Router — 设计 Spec

**Date:** 2026-07-01
**Author:** opencode (hermetic-agent team)
**Status:** Designed — pending review

---

## 0. 背景与目标

### 现状

当前 hermetic-agent **仅支持单个 opencode sandbox 节点**（`opencode-1` + `Settings.opencode_base_url: str`）。虽然代码架构上已内置 claude_code adapter 和 Nacos AI 推送 + 编排层 `SchedulerService`，但：

- 没有调度层能按需把 chat 请求分配到 N 个 opencode 节点
- 没有 service discovery — 多节点必须静态配置 `default_agents_json`，重启才能增减
- session_id 与节点永久绑定（唯一的那个），无法扩展为 sticky-pool 模式
- 没有策略接口 — 以后加新调度算法要散落各处改
- `AgentPoolService` 与 `AgentBridge._providers` 双轨并行，职责不清

### 目标

| 优先级 | 目标 | 成功指标 |
|--------|------|----------|
| P1 | 多 opencode 节点调度（轮询 / 最少连接 / 能力匹配 / 手工指定） | 新增 opencode-N sandbox 后 Nacos 自动注册、Hub 自动路由 |
| P1 | 向后兼容现有 single-node 行为 | 旧 request body (无 agent_name) 走 round_robin 默认选 |
| P1 | Session sticky — 创建时绑节点，生命期不迁移 | 同 session_id 的请求始终落在同一节点 |
| P2 | 新 SDK（hermes / codex / …）接入零摩擦 | 写 1 个 adapter + 1 个 capability yaml，不改既有代码 |

### 非目标

- ~~跨节点 session 迁移~~（sticky 即可，不要 migration）
- ~~节点故障自动 failover~~（报错即可，不拉其他节点）
- ~~SessionManager (core/session.py) 整合~~（遗留代码暂不动）
- ~~AgentPoolService 合并~~（与 router 职责不同，各自独立）
- ~~chat_controller.py 行数瘦身~~（已超 L1 200 行，但与本 PR 无关，按 KNOWN_VIOLATIONS 豁免）

---

## 1. 架构总览

### 1.1 新增 L3 调度层

```
L1  api/controllers/chat_controller.py
     │  POST /agent/chat[/stream]
     │  ScenarioMiddleware (scenario_name)  ← 不动
     │  AgentRouter.resolve_agent()         ← 新插入点
     ▼
L2  scenarios/                              ← 不动（只管 scenario_name 6 优先级）
     ▼
L3  NEW: core/agent_router.py               ← 调度层
     │   ├─ core/strategies/                ← 策略子包（4 个内置实现）
     │   ├─ core/nacos_discovery.py         ← Nacos 双向服务发现
     │   └─ core/                      ← 已有 scheduler.py 作为编排层 sibling
     ▼
L4  providers/agent_bridge.py               ← 不动（只管 SDK 分发）
     │   ├─ providers/opencode/             ← 不动
     │   ├─ providers/claude_code/          ← 不动
     │   └─ providers/hermes/               ← P2 新增
     ▼
L5  store/policy/audit/sandbox              ← 不动
```

### 1.2 职责划分

| 模块 | 职责 | 不变/新增 |
|------|------|-----------|
| `AgentBridge` | Provider 分发：agent_name → adapter → SDK 通信 | 不变 |
| `AgentRouter` | 路由调度：body + scenario_ctx → agent_name | 新增 |
| `RoutingStrategy` | 从候选列表中选一个节点 | 新增 |
| `AgentNodeRegistry` | 节点内存池 + sticky session map | 新增 |
| `NacosDiscoveryService` | 监听 Nacos 服务上下线 → 驱动 register/deregister | 新增 |
| `NacosAISync` | 推 Agent Cards 到 Nacos AI registry | 不变 |

### 1.3 数据流

```
body {scenario, agent_name?, model?, messages, session_id?}
  │
  ├─ ScenarioMiddleware → ctx.scenario               ← 现状
  │
  ├─ 1. body.agent_name 非空 && strategy=manual
  │     → 用它（bypass scheduling）
  │
  ├─ 2. body.session_id 存在
  │     → router.registry.resolve_session()          ← sticky
  │     → 返回原 agent_name
  │
  ├─ 3. body.strategy / scenario.routing.strategy / settings.default_strategy
  │     → 临时或持久性 strategy hint
  │
  ├─ 4. registry.get_capable(required_caps)          ← 按 scenario tags 过滤
  │     → candidates
  │
  ├─ 5. strategy.select(candidates, ctx)             ← round_robin / least_loaded / capability_match
  │     → agent_name
  │
  └─ 6. bridge.create_session(agent_name=...)        ← 签名不变
        → registry.bind_session(session_id, agent_name)  ← sticky 绑定

chat 返回后:
  router.on_chat_complete(session_id, success, duration)
    → strategy.feedback(node, success, duration)
```

---

## 2. AgentRouter API & 数据模型

### 2.1 新增 `core/agent_router.py`（≤250 行）

```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from hermetic_agent.providers.base import AgentConfig, SDKType


class NodeStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DRAINING = "draining"
    OFFLINE = "offline"


@dataclass
class AgentNode:
    """运行时节点 = 静态 AgentConfig + 动态状态。"""
    config: AgentConfig
    capabilities: frozenset[str] = frozenset()
    status: NodeStatus = NodeStatus.HEALTHY
    active_sessions: int = 0
    last_heartbeat: float = 0.0


@dataclass
class RoutingContext:
    """单次 chat 请求的路由上下文。"""
    scenario_name: str
    body: dict
    session_id: str | None
    required_caps: frozenset[str] = frozenset()
```

### 2.2 节点注册表

```python
class AgentNodeRegistry:
    """进程内节点池——单一数据源（替代现有 AgentPoolService 的 chat 角色）。"""

    def __init__(self) -> None:
        self._nodes: dict[str, AgentNode] = {}
        self._session_map: dict[str, str] = {}   # session_id → agent_name (sticky)

    def register(self, node: AgentNode) -> None:
        """幂等注册；已存在同 name 时更新 config + capabilities。"""
        ...

    def deregister(self, agent_name: str) -> None:
        """标记 DRAINING；清理 session_map 中已过期条目。"""
        ...

    def bind_session(self, session_id: str, agent_name: str) -> None:
        """sticky 绑定。"""
        ...

    def resolve_session(self, session_id: str) -> str | None:
        """查 sticky。"""
        ...

    def get_healthy(self, sdk_type: SDKType | None = None) -> list[AgentNode]:
        """列出 HEALTHY 节点，可按 sdk_type 过滤。"""
        ...

    def get_capable(self, required_caps: frozenset[str]) -> list[AgentNode]:
        """列出满足 capability 需求的 HEALTHY 节点。"""
        ...

    def get_stats(self) -> dict:
        """供 pool_controller 展示。"""
        ...
```

### 2.3 主入口

```python
class AgentRouter:
    """L3 调度器——外部唯一入口。"""

    def __init__(
        self,
        registry: AgentNodeRegistry,
        default_strategy: RoutingStrategy,
        bridge: 'AgentBridge',          # 引用，不拥有
    ) -> None:
        self._registry = registry
        self._default_strategy = default_strategy
        self._bridge = bridge

    async def resolve_agent(self, ctx: RoutingContext) -> str:
        """解析应使用的 agent_name；内部处理 sticky / strategy / caps。"""
        # 1. manual 策略 → body.agent_name
        # 2. session_id → sticky 查询
        # 3. candidates = registry.get_capable(ctx.required_caps)
        # 4. strategy_hint = resolve from body / scenario / settings
        # 5. strategy.select(candidates, ctx) → agent_name
        ...

    async def on_chat_complete(
        self, session_id: str, success: bool, duration: float,
    ) -> None:
        """chat 结束回调，驱动 strategy.feedback。"""
        ...

    def register(self, node: AgentNode) -> None:
        """委托 registry。"""
        ...

    def deregister(self, agent_name: str) -> None:
        """委托 registry。"""
        ...

    @property
    def registry(self) -> AgentNodeRegistry:
        return self._registry
```

### 2.4 `pool_controller` 变更

现有 `POST /agent/pool/register` / `GET /agent/pool/stats` 不变；新增 `DELETE /agent/pool/{name}`：

```python
@pool_bp.delete("/<name>")
async def deregister_agent(request, name):
    router.deregister(name)
    return json({"code": "OK"})
```

---

## 3. 策略接口 + 4 个内置实现

### 3.1 目录结构

```
core/strategies/
  __init__.py          # resolve_strategy() 工厂
  base.py              # RoutingStrategy ABC
  round_robin.py       # ~40 行
  least_loaded.py      # ~50 行
  capability_match.py  # ~70 行
  manual.py            # ~30 行
```

### 3.2 Strategy ABC

```python
class RoutingStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def select(self, candidates: list[AgentNode], ctx: RoutingContext) -> AgentNode:
        """从 candidates 中选一个节点。"""
        ...

    @abstractmethod
    def feedback(self, node: AgentNode, success: bool, duration: float) -> None:
        """chat 结束后回调；least_loaded / capability_match 借此调权重。"""
        ...

    def health_check(self, node: AgentNode) -> bool:
        """可选覆写；默认取 node.status == HEALTHY。"""
        return node.status == NodeStatus.HEALTHY
```

### 3.3 策略工厂

```python
_STRATEGY_REGISTRY: dict[str, type[RoutingStrategy]] = {
    "round_robin": RoundRobinStrategy,
    "least_loaded": LeastLoadedStrategy,
    "capability_match": CapabilityMatchStrategy,
    "manual": ManualStrategy,
}

def resolve_strategy(name: str) -> RoutingStrategy:
    cls = _STRATEGY_REGISTRY.get(name)
    if cls is None:
        raise InvalidRoutingStrategyError(name)
    return cls()
```

### 3.4 策略行为

| 策略 | 算法 | 状态 | 失败回退 |
|------|------|------|----------|
| `round_robin` | atomic counter % len(candidates) | 无状态（单 atomic int） | 跳过 OFFLINE/DRAINING |
| `least_loaded` | min(candidates, key=active_sessions) | `AgentNode.active_sessions` | 全 busy → 降级 round_robin |
| `capability_match` | score = cap_overlap * 100 + feedback_weight | capabilities + feedback | 0 overlap → 降级 round_robin |
| `manual` | 直接读 `ctx.body["agent_name"]` | 无 | 无 agent_name → 400 错误码 |

### 3.5 优先级链

```
body.strategy             → 临时覆盖（单次请求）
scenario.routing.strategy → 场景级（config 热加载）
settings.default_strategy → 进程级 (default=round_robin)
```

---

## 4. Nacos 双向服务发现

### 4.1 新增 `core/nacos_discovery.py`（≤150 行）

```python
class NacosDiscoveryService:
    """订阅 Nacos 服务上下线事件 → 驱动 router register/deregister。"""

    def __init__(self, nacos_client, router: AgentRouter, bridge: 'AgentBridge', settings) -> None:
        self._client = nacos_client
        self._router = router
        self._bridge = bridge
        self._settings = settings
        self._instance_to_agent: dict[str, str] = {}   # instance_id → agent_name

    async def start(self) -> None:
        # 1. 全量 list_services(): hermetic-opencode
        # 2. 对每个 instance → _on_add(instance)
        # 3. subscribe(service, self._on_change)
        ...

    async def _on_change(self, event) -> None:
        if event.action == "ADD":
            meta = event.metadata
            agent_name = f"{event.service_name}-{event.instance_id[:8]}"
            node = AgentNode(
                config=AgentConfig(
                    name=agent_name,
                    base_url=f"http://{event.ip}:{meta['port']}",
                    sdk_type="opencode",
                    default_model=meta.get("default_model"),
                    capabilities=meta.get("capabilities", []),
                ),
                capabilities=frozenset(meta.get("capabilities", [])),
            )
            await self._router.register(node)
            await self._bridge.register(node.config)   # 同步进 bridge
            self._instance_to_agent[event.instance_id] = agent_name
        elif event.action == "REMOVE":
            agent_name = self._instance_to_agent.pop(event.instance_id, None)
            if agent_name:
                await self._router.deregister(agent_name)

    async def stop(self) -> None:
        ...
```

### 4.2 启动/关闭

```python
# lifecycle.py (startup)
if settings.nacos_enabled:
    discovery = NacosDiscoveryService(nacos_client, router, bridge, settings)
    await discovery.start()
    app.ctx.discovery = discovery

# lifecycle.py (shutdown)
if hasattr(app.ctx, 'discovery'):
    await app.ctx.discovery.stop()
```

### 4.3 Nacos 离线降级

Hub 进程内 router 已有内存中的节点池，Nacos 断联**不影响**已注册节点的新请求；仅新 sandbox 上线时不会被自动感知（需 Nacos 恢复后重新 list_services 补偿）。

兜底路径：Nacos 不可达时，从 `default_agents_json` 加载静态节点（现状行为）。

### 4.4 sandbox 端注册

sandbox 容器 entrypoint 启动时，自注册到 Nacos service `hermetic-opencode`，metadata 带 `port` / `default_model` / `capabilities`；优雅退出时 deregister。Nacos 健康检查超时也会自动摘除。

---

## 5. Chat 请求路由流程改动

### 5.1 `chat_controller.py` 改动

仅 3 处插入，不改既有签名：

```
现有 _resolve_or_create_session():
  ├─ body.agent_name 有值 → 直接用
  ├─ body.session_id 有值 → bridge.get_agent_for_session()
  └─ 否则 → next(iter(bridge.list_agents()))

改为:
  ├─ RoutingContext 构建（scenario_name + required_caps）
  ├─ agent_name = await router.resolve_agent(ctx)       ← 新
  └─ bridge.create_session(agent_name=...)              ← 签名不变

新增聊后回调:
  router.on_chat_complete(session_id, success, duration)
```

### 5.2 `scenario → caps` 映射

```python
def _caps_from_scenario(scenario) -> frozenset[str]:
    """从 ScenarioConfig.tags 提取所需能力。"""
    caps = frozenset(scenario.tags or [])
    ws = getattr(scenario, "workspace", None)
    if ws and ws.launcher and ws.launcher.prefer_engine:
        eng = ws.launcher.prefer_engine
        if eng and eng != "auto":
            caps = caps | frozenset([f"engine:{eng}"])
    return caps
```

### 5.3 Request body 向后兼容

| body 字段 | 旧行为 | 新行为 |
|-----------|--------|--------|
| `agent_name` | 手动指定 | strategy=manual 强制用它 |
| `session_id` | 复用 session | sticky → 查 router 返回原 agent_name |
| `model` | 传给 provider | 不变 |
| 无 agent_name/session_id | 取第一个 | 走 router 默认策略选最优 |
| **新增** `strategy` | — | 单次请求临时覆写 |
| **新增** `cap_hint` | — | 显式能力需求，传给 capability_match |

### 5.4 HITL 分支

HITL 使用 `SuspendableScheduler` 走独立事件流循环，**不经过 router 调度**；但当 HITL fallback 到普通 chat 路径时，同样走 router 选节点。

---

## 6. 新 SDK 接入模式（P2）

### 6.1 开闭原则

新 SDK 接入遵循**对扩展开放，对已有代码零修改**。

### 6.2 Step-by-step 接入 hermes SDK

```
Step 1. 写 adapter (providers/hermes/)
  ├── providers/hermes/__init__.py          (~10 行)
  ├── providers/hermes/adapter.py           (~150 行，参考 claude_code/adapter.py)
  ├── providers/hermes/chat.py              (~300 行)
  └── providers/hermes/lifecycle.py         (~180 行)

Step 2. 扩展 SDKType + bridge (~10 行)
  providers/base.py:         SDKType += "hermes"
  providers/agent_bridge.py: +1 elif 分支

Step 3. 注册 capabilities
  work/capabilities/hermes.yaml:
    sdk_type: hermes
    capabilities: [code, chinese_nlp, rag]
    default_model: hermes-7b

Step 4. scenario yaml 可引用
  scenario.yaml:
    routing:
      strategy: capability_match
      require_caps: [code, tool_use]
```

### 6.3 能力声明 file

`work/capabilities/{sdk_type}.yaml` 声明各 SDK 支持的能力标签供 `capability_match` 策略引用。

### 6.4 P2 扩展估算

- 写 adapter：~2 人日
- capability yaml + 联调：~0.5 人日
- **合计**：~2.5 人日/SDK

---

## 7. 错误码

新增 5 个路由层错误码，遵循既有 `code` + `detail` 规范。

| # | code | HTTP | 触发 | detail 示例 |
|---|------|------|------|-------------|
| 13 | `AGENT_POOL_EMPTY` | 503 | 节点池全空 | `无可用 opencode 节点。agents=0。请检查 Nacos 服务注册或 default_agents_json。文件: config/settings.py:612` |
| 14 | `AGENT_CAP_NOT_MATCH` | 404 | cap 0 overlap 且 fallback round_robin 也找不到 | `无节点满足 capability 需求 caps=[vision]，可用节点 caps: opencode-core=[code,tool_use]。文件: scenario.yaml:routing.require_caps` |
| 15 | `AGENT_NOT_FOUND` | 404 | manual 策略下 body.agent_name 不存在 | `指定节点 not-found 不存在。可用: opencode-core, opencode-2。文件: body.agent_name` |
| 16 | `ROUTING_STRATEGY_INVALID` | 400 | 策略名不识别 | `路由策略 wrr 不识别。可选: round_robin, least_loaded, capability_match, manual。文件: body.strategy` |
| 17 | `SESSION_STALE` | 409 | sticky session 对应的节点已下线 | `session_id=xxx 原节点 opencode-1 已下线 (DRAINING)。请用新 session_id 重新发起。` |

### 降级行为

```
resolve_agent() 内部异常分支：
  ├─ 所有 unhealthy       → raise PoolEmptyError(code=13)
  ├─ cap 0 overlap        → fallback round_robin → 仍空则 raise PoolEmptyError
  ├─ manual 指名 miss      → raise AgentNotFoundError(code=15)，不 fallback
  ├─ strategy 名字错       → raise InvalidStrategyError(code=16)，不 fallback
  └─ 路由成功但 chat 中节点挂了 → 走既有 bridge 错误码（不新增）
```

---

## 8. 文件大小约束

| 模块 | 层 | 上限 | 预估行数 |
|------|-----|------|----------|
| `core/agent_router.py` | L3 | 250 | ~200 |
| `core/strategies/base.py` | L3 | 250 | ~50 |
| `core/strategies/round_robin.py` | L3 | 250 | ~40 |
| `core/strategies/least_loaded.py` | L3 | 250 | ~50 |
| `core/strategies/capability_match.py` | L3 | 250 | ~70 |
| `core/strategies/manual.py` | L3 | 250 | ~30 |
| `core/strategies/__init__.py` | L3 | 250 | ~30 |
| `core/nacos_discovery.py` | L3 | 250 | ~150 |

---

## 9. 影响面

### 不改动的既有文件

- `providers/agent_bridge.py` — 仅 +1 elif 分支（P2 时）
- `providers/adapters/*` — 不动
- `scenarios/*` — 不动
- `audit/*` / `policy/*` / `store/*` — 不动
- `tests/conftest.py` — 不动（新 fixture 走 `tests/test_agent_router_conftest.py`）

### 既有 caller 改动量

- `chat_controller.py` — 3 处插入（resolve agent + on_chat_complete）
- `lifecycle.py` — +2 行（discovery.start / stop）
- `pool_controller.py` — +1 route (DELETE)
- `config/settings.py` — +3 settings (default_strategy / routing / ...)

---

## 10. 测试策略

| 用例 | 位置 | 说明 |
|------|------|------|
| `test_agent_router_happy_path` | `tests/test_agent_router_.py` | round_robin sticky |
| `test_agent_router_cap_not_match` | 同上 | code=14 |
| `test_agent_router_pool_empty` | 同上 | code=13 |
| `test_agent_router_session_sticky` | 同上 | 同 session_id 落在同一节点 |
| `test_agent_router_nacos_register` | `tests/test_nacos_discovery_.py` | mock Nacos event |
| `test_agent_router_strategy_fallback` | 同上 | capability_match → round_robin 降级 |
| `test_chat_controller_router_integration` | `tests/test_chat_multi_agent_.py` | e2e → `--run-e2e` flag |

所有单元用例用 mock strategy + mock registry；e2e 用例需要多 sandbox 容器，默认 skip。

---

## 11. 风险 & 缓解

| 风险 | 概率 | 缓解 |
|------|------|------|
| Nacos SDK subscribe API 与现有客户端版本不兼容 | 中 | 写 compatibility shim，fallback 到 list_services 轮询 |
| atomic counter 在 uvicorn 多 worker 下不共享（多进程） | 高 | 文档声明"单 worker 推荐"；多 worker 下 round_robin 退化为 random |
| 新错误码与既有 12 个冲突 | 低 | #13-17 是新的，既有 #1-12 保留 |
| session_map 内存无限增长 | 中 | LRU 容量上限（默认 10k session）+ 定期清理已关闭 session |

---

## 12. 里程碑

### Phase 1 — Multi-opencode（~5 人日）

- [ ] `core/agent_router.py` + `AgentNodeRegistry` + `RoutingStrategy` ABC
- [ ] 4 个策略实现
- [ ] `chat_controller.py` 3 处插入
- [ ] `pool_controller.py` DELETE route
- [ ] 单元用例 + 覆盖 round_robin / least_loaded / capability_match / manual / sticky / cap-mismatch

### Phase 2 — Nacos 双向发现（~3 人日）

- [ ] `core/nacos_discovery.py`
- [ ] sandbox entrypoint 注册脚本
- [ ] `lifecycle.py` start/stop hooks
- [ ] 静态 fallback (Nacos 不可达 → default_agents_json)

### Phase 3 — 能力声明 + P2 模板（~1 人日）

- [ ] `work/capabilities/*.yaml` 典范文件
- [ ]适配器接入模板文档

### Phase 4 — 第一个新 SDK 接入（~2.5 人日）

- [ ] 选一个目标 SDK（hermes 或 codex）
- [ ] 写 adapter + capability yaml
- [ ] 集成测试

---

## 13. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 调度层位置 | 新增 L3 `core/agent_router.py` | 单一职责；AgentBridge 管 I/O、Router 管调度 |
| 调度策略 | Strategy ABC + 4 built-in implementations | 多 opencode 优先 + 能力匹配 + 向后兼容 |
| Session 亲和 | Sticky（创建时绑节点，不迁移） | 跨节点 migration 复杂度太高，不必要 |
| 节点注册 | Nacos 双向服务发现（推+拉+subscribe） | 复用已存在的 Nacos 基础设施 |
| AgentPoolService 处理 | 保留不动 | pool service 管外部 registry 推送，router 管本地调度，职责不同 |
| chat_controller 大文件 | 暂不瘦身 | 属既有 KNOWN_VIOLATIONS，不在此 PR 范围 |
