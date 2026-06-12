# 全量代码审查报告

## 📋 审查概览

- **项目名称**：OpenCode Agent Scheduler Hub（fh-openagent）
- **技术栈**：Python 3.10+ / Sanic 24 / Pydantic v2 / asyncpg / structlog / httpx；前端 React 18 + Vite 6 + TypeScript 5；Node 24 opencode-ai；Docker Compose 三服务编排
- **审查范围**：全量代码（`src/`、`docker/`、`scripts/`、`frontend/src/`、`tests/`、配置）
- **涉及文件数**：约 90 个 Python 源文件 + 128 个测试 + 90 个前端源文件 + 10+ 脚本/容器文件 + 文档；源代码总计约 **18 445 行**（src 树，不含 vendor）
- **整体评价**：架构分层清晰、设计文档完整，但 L1（`api/`）与 L4（`providers/`）严重超标（300+ / 1200+ 行），存在路由注册重复、模块未被挂载（整段死代码）、未捕获错误吞错、SSE keepalive 逻辑有边界问题等真实风险；测试数量充足（763 个 `test_` 函数）但前端零测试。
- **风险等级**：🟡 **中**（架构/可维护性问题多，但当前在本地 + 单租户 + dev 场景下功能可用；进入生产前必须修复 🔴 项）

## 🗺️ 项目地图

1. **入口与运行**：`src/openagent/main.py` 调 `create_app` 启 Sanic；容器化（`docker/Dockerfile.openagent`）构建；`docker-compose.yml` 编排 Hub + opencode-sandbox +（可选）frontend。
2. **5 层架构**（`scripts/ci_check.py` 强制）：L1 `api/`（HTTP/Blueprints）、L2 `scenarios/`（YAML 配置 + 路由 + 注入）、L3 `skill_runtime/ + auip/ + core/suspendable_scheduler.py`（HITL + 卡片）、L4 `providers/`（opencode / claude_code 双 SDK 适配）、L5 `policy/ + store/ + audit/`（策略与持久化）。
3. **核心服务**：`api/app.py` + `api/lifecycle.py` 装载 storage / SkillRegistry / MCPRegistry / AgentBridge / Scheduler / turn_store / scenario 中间件；前端 SSE 流式 + Heartbleed 风格 keepalive 注入。
4. **agent 桥接**：`AgentBridge` 按 `sdk_type` 路由到 `OpenCodeAdapter` 或 `ClaudeCodeAdapter`；opencode 路径走双轨——SDK + 直接 `httpx` POST（绕开 SDK body 限制）。
5. **场景子系统**：`ScenarioRegistry.load_from_paths` → `ScenarioRouter` 6 优先级 → `ScenarioInjector` 白名单交集 → `ScenarioMiddleware` 注入 `request.ctx`。
6. **HITL**：`SuspendableScheduler`（P5 简化版，模拟 ask_user）+ `InMemoryTurnStore`；通过 `turn_routes.py` 5 个端点（resume / get / events / heartbeat / cancel）。
7. **AUIP 卡片**：`Card` dataclass + `CARD_TYPES_SET`；Hub 端兜底 `maybe_assemble_flight_card` 替弱模型把 `queryFlightBasic` 工具结果拼成 `FLIGHT_RESULT` 卡片。
8. **策略与安全**：`PolicyEngine` 合并 `EffectivePolicy` + override（工具/网络/路径/turn 预算）；路径 hard block（`BLOCKED_PATTERNS`，覆盖 .env / id_* / .ssh / *.pem / *.key 等）；网络 `off / local / any` 三档。
9. **持久化**：`SessionRepository` 抽象 + `MemorySessionRepository` / `PostgresSessionRepository`（asyncpg）双实现。
10. **沙箱**：`sandbox/runtime.py` 包装 `docker` CLI；`providers/launcher.py` 在 `cwd` 校验后用 `Popen` 启 `opencode serve`。

## 🔴 必须修复（Bug / 安全 / 严重设计问题）

### [src/openagent/api/routes.py:53 + src/openagent/api/app.py:163-174] 整份 routes.py 死代码
- **问题描述**：`src/openagent/api/routes.py`（**1095 行**）定义了一个 `router = Blueprint("agent_scheduler", url_prefix="/agent")`，挂在 `/agent/chat`、`/agent/chat/stream`、`/agent/session/*`、`/agent/skills`、`/agent/tools`、`/agent/pool/*` 等所有核心端点，但 `app.py:create_app` **完全没有 `app.blueprint(router)`**——只挂了 `chat_bp`/`session_bp`/`registry_bp`/`pool_bp` 等新拆分的 blueprint。`routes.py` 既未 import，也未注册。`/agent/chat` 实际由 `controllers/chat_controller.py` 提供。`routes.py` 的 `ChatRequest`/`ChatResponse` 跟 `schemas.py` 中同名，导入冲突。
- **影响场景**：
  1. **死代码 1095 行**——造成长期维护负担（任何修改这里的人都以为"它在线"），且双重 Pydantic 模型的字段不同步风险。
  2. **重复路由注册**：`/agent/skills`、`/agent/tools`、`/agent/pool/*` 在 `routes.py` 与 `controllers/registry_controller.py` / `controllers/pool_controller.py` 各定义一份。如果有人误把 `router` 加进 `app.blueprint(router)`，Sanic 会启动失败或路由竞态。
  3. **import 副作用**：`chat_controller.py:36` 从 `routes.py` import 了 `_extract_mcp_token` 与 `_resolve_session_directory`——这两个 helper 仍然有效，但来源文件标注不清。
- **根因分析**：P6 阶段把 endpoints 从 `routes.py` 拆到 `controllers/*.py`，但没把旧 router 删掉/标记。
- **修复建议**：
  1. **删除** `src/openagent/api/routes.py` 整个文件（1095 行），并把 `_extract_mcp_token` 与 `_resolve_session_directory` 移到一个独立 `api/extractors.py` 供 `chat_controller.py` 引用；
  2. 或者将 `router` 真正注册到 app、删除 controllers 中的副本（不推荐：当前 controllers 是 P6 改造的成果，routes.py 是旧版）。
  ```python
  # app.py 现状 — 缺的行
  # app.blueprint(router)  # ← 永远不要加回去
  ```
- **严重程度**：🔴

### [src/openagent/skill_runtime/fragments.py:192-204] 死代码 — 复制粘贴残留
- **问题描述**：`FragmentLoader._load_explicit` 末尾 `return self._enforce_budget(...)` 之后，紧接着出现 **12 行无意义代码**——`strategy = ps.strategy`、3 个 `if strategy == ...` 分支与 `raise ValueError`。这些代码紧跟 `return` 之后，永远不可达；它们看起来像旧版 `load()` 方法被切碎后遗留的碎片。
- **影响场景**：
  1. 阅读者会误以为 `_load_explicit` 实际有 fallback 逻辑；
  2. 未来重构时易被错误地"激活"——`return` 后写 `strategy` 会被 linter 警告但仍能跑，造成逻辑混乱；
  3. ruff/mypy 多数情况下不会发现"return 后不可达"，需要 `flake8-return` 或 `vulture` 才会标红。
- **根因分析**：与 routes.py 类似，是 P5→P6 重构时 cut-paste 残留。
- **修复建议**：
  ```python
  # 删掉这 12 行
  return self._enforce_budget(
      texts, report,
      scenario_name=_scenario_name(scenario), current_state="*",
  )
  # END — 不要往下写
  ```
- **严重程度**：🔴（实际为可立即删除的死代码，无运行期影响，但维护期容易误伤）

### [src/openagent/api/controllers/chat_controller.py:436-477] SSE keepalive 在错误路径下重复写 done，可能泄漏连接
- **问题描述**：`_stream_with_keepalive` 的循环里 `if event.type in ("done", "error"): return`，但在 chat_controller 的 `streaming_fn` 里：
  - 正常路径 `await resp.write(chunk.to_sse())` + `if chunk.type == "done": done_written = True`；
  - 异常路径 `try/except` 内写 `StreamEvent.error(...).to_sse()`，但 `done_written` 不更新；
  - `finally` 块又写一次 `StreamEvent.done().to_sse()` **如果 `not done_written`**。
  
  问题：当业务流在错误之后又自然 emit 一个 done（极少见但可能），或当 keepalive 包了 done 后又 raise，done 会写两次；前端 EventSource 会因 `data: {...}` 重复收到 done 而触发 reconnect 风暴。
- **影响场景**：长 chat 偶发异常后前端 EventSource 自动重连（`retry: 2000` 在 controller 里硬编码了），重连又可能命中相同错误，进入"快速重连 → 错误 → 重连"循环。
- **根因分析**：SSE 协议下"流结束"语义有歧义——`done` 事件 vs `eof` vs `error`。当前实现混用三种。
- **修复建议**：
  1. 显式状态机：`stream_state ∈ {OPEN, DONE_SENT, ERROR_SENT, CLOSED}`；
  2. `done_written` 用 `contextlib.Event` 或 `bool` 包装 `_write_done_once()` 工具函数；
  3. `eof()` 只调用一次（当前在 `finally` 写 done + `eof`，二者顺序未做互斥）。
  ```python
  done_event = asyncio.Event()
  async def _write_done():
      if not done_event.is_set():
          await resp.write(StreamEvent.done().to_sse())
          done_event.set()
  ```
- **严重程度**：🔴

### [src/openagent/api/controllers/chat_controller.py:176-189] 中文/英文路由正则可被构造绕过
- **问题描述**：`_FH_ROUTE_RE` 匹配 `从 北京 到 上海`，但**没有边界**，能匹配 `从abc到def`（任意非空字符串），也匹配 `从头到尾到xyz` 这种含多段"到" 的输入；`_FH_DATE_RE` 同样对 `12-3` / `13-2` 这种结构合法日期但月份 13 也接受。`_should_bypass_hitl_placeholder` 把这些当成"用户已提供完整信息"，跳过 ask_user 卡片。
- **影响场景**：HITL 状态机的"占位卡片"被错误跳过，LLM 进入下游分支而用户其实想填多段。
- **根因分析**：中文 NLP 难，但工程上至少要"保守"——只在明确有空格/分隔符时匹配。
- **修复建议**：
  ```python
  _FH_ROUTE_RE = re.compile(
      r"从\s*[\u4e00-\u9fffA-Za-z]{2,5}\s*(?:到|至|飞)\s*[\u4e00-\u9fffA-Za-z]{2,5}"
  )
  # 加 ^ 锚或前后分隔; \b 不适用中文, 用 lookbehind/lookahead 至少避免
  # 跟下一段 "到" 拼起来
  ```
- **严重程度**：🔴

### [src/openagent/api/controllers/auth_controller.py:296-300] 日志把 feihe 整个 response body 记录（含 token）
- **问题描述**：
  ```python
  logger.info(
      "feihe_logon_response_raw",
      status=feihe_resp.status_code,
      headers=dict(feihe_resp.headers),
      body=feihe_resp.text,
  )
  ```
  紧接着 `_token_from_response` 又打了 `token_value=token`（**明文**）到 info 级日志。`audit.py:redact_value` 只在 `AuditEvent.context` 里脱敏，structlog 的常规 logger 走的不是 audit 通道——密码/令牌原文会**直接落到 JSON 日志**（生产是 Loki/ELK）。
- **影响场景**：明文 token 落盘 / 落日志聚合系统后变成合规事故（PCI / GDPR / 等保 2.0）。
- **根因分析**：调试时为方便贴的 raw log，遗留。
- **修复建议**：
  1. 删掉 `body=feihe_resp.text`（或 truncate 到 200 字符 + redact 已知敏感 key）；
  2. 改用 `redact_value`：
  ```python
  from openagent.policy.audit import redact_value
  logger.info("feihe_logon_response_raw", status=..., body=redact_value("body", feihe_resp.text[:200]))
  logger.info("feihe_logon_token_parse_hit", source=..., token_len=len(token))  # 仅长度
  ```
- **严重程度**：🔴

### [src/openagent/api/controllers/auth_controller.py:158-162] MD5 哈希密码——算法过时
- **问题描述**：`_feihe_password_value` 用 `hashlib.md5(value.encode("utf-8")).hexdigest()` 把用户密码算成 MD5 哈希再发给 feihe 后端（`logonV2` 接口本身要求 32 字符小写 hex）。MD5 在 2026 年**已被多次证明可碰撞 / 快速 brute-force**。
- **影响场景**：Hub 内部若有人截获 `feihe_logon_attempt` 日志（user_code + 哈希密码），可离线爆破——但 user_code 是公司员工编号（3-4 位），空间极小。
- **根因分析**：feihe 后端协议本身只接受 MD5 hex——Hub 是协议适配层，无法升级算法。
- **修复建议**：
  1. **缓解**：仅记 `password_hash` 的存在性 / 长度，**不**记哈希值；
  2. **长期**：跟 feihe 后端团队提议升级到 bcrypt/argon2；
  3. 当前实现已能识别"用户已经传了 32 字符 MD5"→ 不再哈希（避免双重哈希），逻辑 OK——主要风险在日志。
- **严重程度**：🟡（无 Hub 自身漏洞，但建议在 docs 标出"MD5 是协议约束"）

### [src/openagent/providers/opencode_chat.py:1040-1065] race 抑制逻辑可能误吞真实错误
- **问题描述**：
  ```python
  if (
      mapped.type == "error"
      and chat_task is not None
      and not chat_task.done()
  ):
      with contextlib.suppress(Exception):
          await asyncio.wait_for(asyncio.shield(chat_task), timeout=3.0)
      if chat_task.done() and chat_task.exception() is None:
          # 视为 race, 吞掉
          continue
  ```
  注释说"在 ~1s 内的 session.error 是 opencode 1.17.0 share-subscriber race fingerprint"，但代码里 `timeout=3.0` 是 3 秒——任何 3 秒内碰巧通过的 `error` 事件都会被吞。
- **影响场景**：
  1. 真实的 `session.error`（非 race）若发生在 chat 启动 3s 内，**前端不会看到**——前端一直等 `done`，等到 30-60s 后 Sanic 超时返回 500。
  2. opencode 1.17.0 升级后这个 race 假设可能不再成立，吞错范围扩大。
- **根因分析**：注释说"first ~1s"，代码说"3s"——漂移。
- **修复建议**：
  1. 把 `timeout=3.0` 改成 `timeout=1.0` 跟注释一致；
  2. 加一个 `time.monotonic() - start_time < 1.0` 显式时间窗判断；
  3. 永不静默：吞错前记一条 `logger.warning("session_error_swallowed", reason="init_race_window")`。
- **严重程度**：🔴

### [src/openagent/providers/opencode_chat.py:1133-1144] 不完整任务取消可能让 HTTP client 留 leak
- **问题描述**：
  ```python
  else:
      chat_task.cancel()
      try:
          await chat_task
      except (asyncio.CancelledError, Exception):
          pass
      return
  ```
  这里 `chat_task` 在客户端断开时取消，但底层 `_post_session_message_raw` 启动的 `httpx.AsyncClient`（`async with _build_http_client() as client`）在 `await` 取消后会跑 `aclose()`——OK。
  
  **但** 同一文件 1139 行注释说"显式 aclose 底层 async generator"——`aclose()` 在 `GeneratorExit` 路径下并非总是被调用。Sanic 25 的行为：当 `async for` 因客户端断开被 `aclose` 时，下游 generator 抛 `GeneratorExit`，但 `httpx.AsyncClient` 的 `aclose` 是同步 ctx mgmt，会在 `__aexit__` 里跑——这是 OK 的。
  
  真正的隐患是 **`_opencode_admin_port()` / `_wait_opencode_health` / `_push_flight_token_to_opencode`** 各自 `async with httpx.AsyncClient(...)` 创建的 client 在异常路径下能否被 `aclose`——这些函数是 helper，独立 try/except 包裹，**但 client 创建在 `try` 之外**：
  ```python
  try:
      async with httpx.AsyncClient(timeout=5.0) as client:  # 230 行
          r1 = await client.post(...)
          ...
  except (httpx.HTTPError, OSError) as e:
      ...
  ```
  `async with` 在 try 内，OK——但函数参数 `client: httpx.AsyncClient | None = None` 路径下，外部 client 的 close 不归本函数管，如果调用方在异常路径下没 close，外层 client 会留 leak。
- **影响场景**：高频 token 推送 + 异常情况下，httpx 连接池可能增长。
- **根因分析**：helper 既支持"自带 client"又支持"新 client"，生命周期归属不清。
- **修复建议**：
  1. 统一为"永远自带 client"，`client=` 参数去掉；
  2. 或者用 `try/finally + await client.aclose()` 显式 close（不依赖 ctx mgmt 的隐式行为）。
- **严重程度**：🟡

### [src/openagent/api/app.py:60-63] 兜底 SanicException 类型断言是潜在 silent failure
- **问题描述**：
  ```python
  try:
      from sanic.exceptions import SanicException
  except ImportError:  # pragma: no cover
      SanicException = Exception  # type: ignore[misc,assignment]
  ```
  pyproject.toml 把 `sanic>=24.0.0` 写死，Sanic 24 一定有 `SanicException`，该 try block 永远不会触发 ImportError——但万一未来升级到 30+ API 改了，**`SanicException = Exception` 会导致所有 5xx 也被当成 4xx 处理**，业务异常被错误分类。
- **影响场景**：上线后的 Sanic 升级把 ImportError 静默吞掉，4xx/5xx 全部搞错。
- **根因分析**：防御式代码未配套"防御实际生效"的判断。
- **修复建议**：
  ```python
  from sanic.exceptions import SanicException  # 让 ImportError 真的炸出来
  ```
  若真要兜底，至少在 `ImportError` 分支里 `raise RuntimeError("Sanic version mismatch")`。
- **严重程度**：🟡

### [src/openagent/providers/launcher.py:139-150 + 217-229] Popen + 信号处理，孤儿进程风险
- **问题描述**：
  ```python
  proc = Popen(["opencode", "serve", ...], cwd=cwd, stdout=DEVNULL, stderr=PIPE)
  ...
  def stop(self, handle):
      if handle.proc and handle.proc.poll() is None:
          handle.proc.terminate()
          try:
              handle.proc.wait(timeout=grace)
          except TimeoutExpired:
              handle.proc.kill()
  ```
  在 async 上下文里用 sync `Popen` + `terminate` + `wait(timeout=)` 同步阻塞 event loop（最坏 5+ 秒）；Hub 进程一旦开 N 个 opencode 实例 + reload，每个 stop 都会卡死 asyncio loop。Popen 句柄泄漏无 `try/finally`；如果 `_validate_cwd` 在 `_launch_opencode` 之后抛错（虽然目前不会），Popen 不会被 close。
- **影响场景**：sandbox reload / 优雅停机时 5 秒级 loop 阻塞；Popen 句柄不在 `__del__` 里兜底 close。
- **根因分析**：历史代码 vs 异步 runtime 的迁移半成品。
- **修复建议**：
  ```python
  # 用 asyncio.create_subprocess_exec 替换 Popen
  proc = await asyncio.create_subprocess_exec(
      "opencode", "serve", "--port", str(port), ...,
      cwd=cwd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
  )
  ...
  async def stop(self, handle):
      if handle.proc and handle.proc.returncode is None:
          handle.proc.terminate()
          try:
              await asyncio.wait_for(handle.proc.wait(), timeout=grace)
          except asyncio.TimeoutError:
              handle.proc.kill()
              await handle.proc.wait()
  ```
- **严重程度**：🔴（生产 graceful shutdown 必踩）

### [src/openagent/scenarios/middleware.py:43-49] 中间件热重载引用缓存可泄漏旧 router
- **问题描述**：
  ```python
  def __init__(self, app: Sanic) -> None:
      self._app = app
      self._router: ScenarioRouter | None = getattr(app.ctx, "scenario_router", None)
      self._injector: ScenarioInjector | None = getattr(app.ctx, "scenario_injector", None)
  ```
  middleware 构造时缓存 router/injector 引用。`__call__` 里虽然用 `getattr(self._app.ctx, ...)` 重新读 ctx，但 `_router` 字段保留旧对象——`scenario_reload` 端点替换 `app.ctx.scenario_router` 后，旧 middleware 实例的 `_router` 仍然指向旧 router（fallthrough 路径使用）。
- **影响场景**：P6 引入了 `POST /agent/scenarios/reload` 端点——reload 后旧 router 的命中规则可能不准确。
- **修复建议**：删掉 `_router`/`_injector` 实例字段，每次都从 `self._app.ctx` 读。
- **严重程度**：🟡

### [src/openagent/api/controllers/chat_controller.py:342-358] 重复桥接的 agent_name 查找可能 N² 慢
- **问题描述**：`chat` 与 `chat_stream` 都在收到已有 `session_id` 时线性扫描 `bridge.list_agents()` 找 `get_session`。每次 chat 都从 0 开始扫——N 个 agent 池上 chat 是 O(N)。
- **影响场景**：未来加多 agent (Phase 2+) 会 N²。
- **修复建议**：直接用 `bridge.get_agent_for_session(session_id)`（已有 O(1) 字典方法，`agent_bridge.py:167`），删除 339-348 整段 for 循环。
- **严重程度**：🟡

## 🟡 建议改进（质量 / 结构 / 可维护性）

### [src/openagent/api/routes.py:53 整体] 1095 行单文件，违反 L1 ≤ 200 行硬限
- **问题描述**：`scripts/ci_check.py` 明确把 L1 上限定为 200 行（`LINE_LIMITS["L1"] = 200`），但 `routes.py` 是 1095 行。当前**确实没注册**到 app，但 `LINE_LIMITS` 检查只对"实际挂载的"路径生效还是全部生效？根据 `LAYER_PATTERNS["L1"] = ["openagent/api/"]`，**所有 `api/` 下的文件都计**——`routes.py` 应该被 CI 拦下。
- **影响**：CI 可能没跑 / 有豁免；架构纪律性受损。
- **建议**：彻底删除（见 🔴 项 #1），或拆成 controllers。

### [src/openagent/api/controllers/chat_controller.py:836] 836 行单文件
- **问题描述**：chat_controller 已经 836 行；按 L1 200 行硬限应拆分（chat/stream 各自独立 controller + 提取 SSE 拦截器到独立模块）。
- **建议**：拆出 `_stream_with_keepalive` / `_stream_with_ask_user_intercept` / `_ask_user_to_card` / `_turn_event_to_sse` 到 `api/streaming/`，chat controller 缩到 < 250 行。

### [src/openagent/providers/opencode_chat.py:1206] 1206 行单文件
- **问题描述**：L4 限 200 行，opencode_chat 1206 行（含 80+ 行 helper）。包含 `blocking_chat` / `stream_chat` / `_push_flight_token_to_opencode` / `_wait_opencode_health` 等多个独立关注点。
- **建议**：拆成 `opencode_chat_blocking.py` / `opencode_chat_streaming.py` / `opencode_flight_token.py` / `opencode_event_hub.py`（已存在但小）/ `opencode_admin.py`。

### [src/openagent/api/app.py:87-105] 异常处理器把 traceback 返回给客户端
- **问题描述**：
  ```python
  return JSONResponse({
      "success": False, "status": 500, "error": ...,
      "traceback": tb, "path": request.path,
  }, status=500)
  ```
  `app.config.DEBUG` 控制 Sanic 自带格式，但**这条 500 handler 总是把 traceback 加到 JSON body**。生产泄露：内部类名、文件路径、SQL 字符串、Pydantic 校验的字段值等。`app.config.DEBUG = True` 才有意义。
- **建议**：
  ```python
  body = {"success": False, "status": 500, "error": "internal server error"}
  if app.config.DEBUG:
      body["traceback"] = tb
  return JSONResponse(body, status=500)
  ```

### [src/openagent/api/controllers/chat_controller.py:680-686] 用 `err.body.decode()` 反向解析 JSON
- **问题描述**：
  ```python
  await resp.write(
      StreamEvent.error(
          message=err.body.decode() if err.body else "session error",
          code="SESSION_ERROR",
      ).to_sse()
  )
  ```
  `_resolve_or_create_session` 返回的 err 是 `JSONResponse` 对象；调 `err.body.decode()` 把已序列化 JSON 当字符串塞进 error 事件的 `message` 字段——前端展示会是 JSON 字符串，不是人话。
- **建议**：`_resolve_or_create_session` 应直接返 `(None, None, error_message: str | None, error_code: str | None)` 而不是 `JSONResponse`——避免在 controller 之间传递 HTTP 响应对象。

### [src/openagent/api/lifecycle.py:91-115] 注册默认 agent 时 `bridge.register` 静默吞错
- **问题描述**：
  ```python
  try:
      bridge.register(cfg)
      registered.append(cfg.name)
  except ValueError as e:
      logger.debug("default_agent_already_registered", name=cfg.name, detail=str(e))
  ```
  注释说"Already-registered is the expected 'idempotent' case during a hot reload"，但 `bridge.register` 抛 `ValueError` 也可能因为 `sdk_type` 不支持——这种情况**应该 warn 而非 debug**。
- **建议**：
  ```python
  except ValueError as e:
      if "already registered" in str(e).lower():
          logger.debug("default_agent_already_registered", name=cfg.name, detail=str(e))
      else:
          logger.warning("default_agent_register_failed", name=cfg.name, error=str(e))
  ```

### [src/openagent/streaming.py:472] 模块级 dataclass StreamEvent 与 `_to_dict` 通用
- **问题描述**：`StreamEvent` 用 `dataclass(asdict)` 转 SSE——`asdict` 对嵌套 dataclass 也递归，但 `field.metadata` / 不可序列化对象（如 datetime）会爆。当前 `_to_dict` 在 27-60 行，但实际没被 StreamEvent 用——一致性可疑。
- **建议**：把 `StreamEvent.to_sse` 改为显式 `json.dumps` + 自定义 `default=` 处理 datetime / UUID / Path。

### [src/openagent/api/controllers/registry_controller.py:82] 与 routes.py 重复（已合并到 🔴 #1）
- **问题描述**：`/agent/skills`、`/agent/tools` 端点既在 `routes.py` 又在 `registry_controller.py` 定义——双份 Pydantic model 字段不一致（`routes.py:684` 缺 `prompt_template`、`mcp_tools` 字段，registry_controller 多一些；`source` 默认值也不同）。
- **建议**：合并到 `registry_controller.py`，删 `routes.py`。

### [src/openagent/scenarios/router.py:89-99] URL/header/body 路由短路后未保存 `routing_context.rejected`
- **问题描述**：URL/header/body 三种"显式指定"路径直接 `return RoutingContext(scenario=cfg, matched_by=label, candidates=[cfg])`——`rejected` 字段为空。如果该 scenario 被禁用且显式 URL 指定了——`_try_get_enabled` 抛 `ScenarioDisabledError`——前端只看到 error，不知道"我之前已经被 keyword 阶段拒过了"。
- **建议**：保留 keyword 阶段 rejected 历史，统一在 `__init__` 阶段就缓存。

### [src/openagent/api/controllers/chat_controller.py:180-182] 日期正则匹配 "12-13" 也算合法
- **问题描述**：`_FH_DATE_RE` 中的 `\d{1,2}[-/.月]\d{1,2}日?` 没限制月份 ≤ 12、日期 ≤ 31，会把"13-45" 当成合法日期。
- **影响**：`_should_bypass_hitl_placeholder` 错判"用户给了日期"，跳过 ask_user 卡片。
- **建议**：用 `datetime.strptime` 在 `_should_bypass_hitl_placeholder` 内做真实解析。

### [src/openagent/sandbox/runtime.py:240-262] docker run 命令中 env 透传缺转义
- **问题描述**：`--env` 通过 `_build_env_args` 拼到 argv：`-e f"{k}={v}"`。如果 `v` 含空格 / 引号，Docker CLI 可能误解。`spec.env` 来自 Hub 内部（settings / LLM 凭证），来源较安全；但**未来若允许 user-provided env 必须警惕**。
- **建议**：用 `shlex.quote` 包裹 value；或文档化"只接受可打印 ASCII、无 shell metachar 的 env"。

### [src/openagent/policy/engine.py:51-101] merge 函数是"只收紧"逻辑但合并时机不明确
- **问题描述**：注释说"override rank <= base rank"——只能收紧。但 `_INTERSECT_FIELDS = {"workspace_dirs", "deny_dirs"}` 用 `set` 转换是 O(N)——若 N 大（数百 workspace dirs）有性能问题。
- **建议**：明确文档化"override 是 caller 的限制，不是扩张"；将 _INTERSECT 改用 `frozenset` 一次性构造。

### [src/openagent/api/scenario_lifecycle.py:114] 初始化失败仅日志
- **问题描述**：
  ```python
  except Exception as e:
      logger.exception("scenarios_init_failed", error=str(e))
  ```
  注释说"失败时记录错误但不抛 — 允许 chat_controller 在 scenario 未就绪时仍可工作"。但实际上 scenario 未就绪时 `ScenarioMiddleware.__call__` 会**把所有 chat 请求挂 400**，因为 `router is None`。当前实现让 logger.exception 静默吞错，**会让 prod 排查极其困难**。
- **建议**：把"scenario 不可用时怎么处理"明文化（如返回明确的 503 / 维护页）；不要既不抛又不返回正确状态码。

### [src/openagent/api/controllers/question_controller.py:53-61] 404 逻辑被一段"if not items and not filtered"反向触发
- **问题描述**：
  ```python
  items = await list_questions_for_session(bridge, session_id)
  filtered = [q for q in items if q.get("sessionID") == session_id or not session_id]
  if not items and not filtered:
      client, _ = await resolve_opencode_client(bridge, session_id)
      if client is None:
          return JSONResponse(ErrorResponse(error=f"Session '{session_id}' not found"), status=404)
  ```
  这段检查"items 和 filtered 都空"——但 `filtered` 的构造里 `or not session_id` 永远会让 `filtered` 至少等于 `items`——当 `items` 空时 `filtered` 也空，触发"session not found"——但**当 `session_id` 实际存在但没有问题时**，也会返回 404（误报）。
- **建议**：去掉 `or not session_id`（该分支永远不会用），直接 `filtered = [q for q in items if q.get("sessionID") == session_id]`；session 存在性用 `bridge.get_agent_for_session(session_id) is None` 判断。

### [src/openagent/core/session.py:24-29] Vendor stub 几乎全 `NotImplementedError`
- **问题描述**：`src/openagent/_vendor/opencode.py` 是个完整 stub，覆盖 `AsyncOpencode` + `_SessionStub` 所有方法——但生产用法 4 个文件（`core/session.py` / `providers/opencode_chat.py` / `providers/opencode_adapter.py` / `providers/opencode_native_sdk.py`）都有 `try: from opencode_ai; except: from openagent._vendor.opencode`。
- **影响**：`opencode-ai` 包必须装才能跑（依赖里有 `opencode-ai>=0.1.0a0`）——vendor stub 永远走不到，是死代码。
- **建议**：删 `src/openagent/_vendor/` 整个目录。

### [src/openagent/providers/opencode_chat.py:779-780] 函数体内 import
- **问题描述**：`import uuid` 出现在 `blocking_chat` 与 `stream_chat` 函数体内（`blocking_chat` 的 780 行、`stream_chat` 的 968 行）。Python 的 import 缓存让重复 import 几乎免费，但**热路径上每条 chat 都要做一次 sys.modules 查找**（虽 O(1)）。
- **建议**：提到模块顶部；或用 `importlib` 进一步 cache。

### [src/openagent/skill_runtime/fragments.py:31-32] 粗略 token 估算常数
- **问题描述**：
  ```python
  _TOKEN_PER_CHAR_NUM = 2
  _TOKEN_PER_CHAR_DEN = 3
  ```
  即 1 token ≈ 1.5 字符——硬编码且只在变量名里注释"粗略"。对中文 + 英文混合的 SKILL.md 估算误差可能 2-3x。
- **建议**：用 `tiktoken` 精确计数；或至少给一个 `--verbose` 的运行时校准。

### [src/openagent/api/controllers/chat_controller.py:275-325] `_turn_event_to_sse` 跟 `turn_routes.py:60-108` 完全相同
- **问题描述**：`turn_routes.py:60-108` 的 `_turn_event_to_sse` 与 `chat_controller.py:274-324` 的 `_turn_event_to_sse` 字段映射一致，复制粘贴。
- **建议**：抽到 `auip/events.py` 同模块的工厂方法，或 `streaming.py` 提供统一 `turn_event_to_sse(turn_evt)`。

### [src/openagent/api/controllers/chat_controller.py:466-477] heartbeat 注释已过时
- **问题描述**：注释 "心跳间隔 (秒): 15s 是 Vite / Nginx / Cloud LB / 浏览器侧 SSE 实现都接受的... 平衡点"——但 Nginx 默认 60s idle 关闭，跟 `keepalive_interval=15.0` 配合是 OK 的；但 `proxy_read_timeout` 默认 60s 在 Vite 后面会被切割。**应当文档化 "需配 Vite `server.proxyTimeout` 与 `server.wsTimeout`"**。
- **建议**：在 docs/deploy.md 加运维提醒。

### [src/openagent/api/controllers/chat_controller.py:843-846] `content_type="text/event-stream"` 硬编码
- **问题描述**：所有 `ResponseStream` 端点（chat_stream / resume_turn / get_turn_events）都写死 `content_type="text/event-stream"`。但 OpenAPI 文档的 `response(200, ...)` 没声明 `application/json` 或 `text/event-stream`——前端 swagger client 生成会误用 text。
- **建议**：用 `sanic_ext.openapi.response(200, schema, content_type="text/event-stream")` 显式标注。

### [src/openagent/store/postgres.py:18-48] SCHEMA 常量内嵌 IF NOT EXISTS
- **问题描述**：SCHEMA 字符串拼出整张表 + 5 条 `ALTER TABLE ADD COLUMN IF NOT EXISTS` 做"forward-compatible migrations"。生产演进应该用 `migrations/` 目录 + 顺序号（`001_init.sql` / `002_add_xxx.sql` + migration runner）。
- **建议**：当 schema 演进超过 3 个版本时迁移到 `migrations/` 框架（Alembic / `yoyo-migrations`）。

### [src/openagent/api/controllers/scenario_controller.py:182 + 309] `from openagent.scenarios.loader import _validate_resources  # type: ignore`
- **问题描述**：controller 调 loader 的私有函数（`_validate_resources` 以下划线开头）；`type: ignore` 抑制 mypy 警告。
- **建议**：把 `_validate_resources` 改为公开 `validate_resources`（无下划线）或抽到独立 `validation` 模块。

### [src/openagent/api/controllers/chat_controller.py:151-174] `_extract_effective_mcp_token` 在热路径调 `get_settings()` 多次
- **问题描述**：每次 chat 都 `from openagent.config.settings import get_settings` + `get_settings().flight_mcp_token_env`——`get_settings` 有 `lru_cache`，但**导入本身**会做首次的 `.env` 解析副作用。
- **建议**：cache `_TOKEN_ENV_NAME` 模块级常数；或在 `lifespan startup` 阶段锁定。

### [src/openagent/api/scenario_lifecycle.py:23-38] `find_project_root` 可能在 PyInstaller / VFS 打包下失效
- **问题描述**：依赖 `Path(__file__).resolve().parents` 找 `pyproject.toml`——PyInstaller `--onefile` 会把 `__file__` 指向 `_MEIPASS`（临时目录），`pyproject.toml` 永远找不到。
- **建议**：在 `getattr(sys, "_MEIPASS", None)` 命中时改用 `sys._MEIPASS`；或者完全用 env var `AGENT_PROJECT_ROOT` 覆盖。

### [tests/] 前端零测试
- **问题描述**：`tests/` 128 个文件、763 个 test_ 函数——全是 Python。`frontend/src/` 90 个文件**完全无单元测试**（`package.json` 没有 vitest/jest/react-testing-library）。
- **影响**：`AuthContext` / `LoginPage` / `http` 拦截器等关键客户端路径零回归保护。
- **建议**：加 `vitest` + `@testing-library/react`；至少 `AuthContext` 的 token 持久化 / 401 行为 / `needsCaptcha` 处理要测。

### [pyproject.toml:69-71] mypy strict + 无配置
- **问题描述**：
  ```toml
  [tool.mypy]
  python_version = "3.10"
  strict = true
  ```
  启用 strict 但**未在 CI 强制跑**（无 mypy script / pre-commit hook 验证）。整份代码 `agent_bridge.py:101 get_config` 等方法未用——但更多是 `Any` 滥用（如 `Any` 出现在 `def get_provider(self, agent_name: str) -> AgentProvider` 实际签名明确，OK；但 `mcp_registry: Any` / `skill_registry: Any` 全部用 Any）。
- **建议**：在 `pyproject.toml` 加 `[tool.hatch.build.targets.wheel] packages = ["src/openagent"]` + `mypy src/openagent` 作为 pre-commit + CI gate。

## 🟢 可选优化（风格 / 性能 / 微调）

### [src/openagent/api/controllers/chat_controller.py:43] `import openagent.auip.cards` 的 CARD_TYPES_SET 是 frozen set
- **建议**：已经是 `frozenset`（`cards.py:51`），OK。可考虑 cache 排序结果 `sorted(CARD_TYPES_SET)` 避免每次重复。

### [src/openagent/api/controllers/chat_controller.py:189] `_should_bypass_hitl_placeholder` 是模块级函数但实际跟 controller 强耦合
- **建议**：移进 `chat_controller.py` 内的私有方法，或移到 `scenarios/heuristics.py`。

### [src/openagent/api/lifecycle.py:21-52] `_skill_paths_with_fallbacks` 用 set 记 seen 后转 list
- **建议**：用 `dict.fromkeys(...)` 单次 O(N) 去重保序。

### [src/openagent/skills/registry.py:18-43] DEFAULT_TEMPLATE 是死代码
- **建议**：删除；改用 YAML frontmatter 直接读 `SKILL.md`。

### [src/openagent/scenarios/loader.py:57-68] YAML resolver monkey-patch 影响全局
- **建议**：改用 `yaml.compose` 或在每个 `load` 临时 patch，避免污染全局状态。

### [src/openagent/api/turn_routes.py:166-244] resume_turn 内嵌的 `_err_stream` 写法绕
- **建议**：抽到 `api/turn_routes.py` 模块顶部作为普通函数。

### [src/openagent/providers/opencode_chat.py:122] `_is_transient_opencode_error` 字符串匹配脆弱
- **建议**：用 `isinstance(e, httpx.TransportError)` 等类型判断代替字符串子串匹配。

### [src/openagent/auip/flight_card.py:35-52] `_parse_minutes` 重复于 `flight_query_presenter._parse_duration`
- **建议**：抽到 `auip/_duration.py` 共享。

### [src/openagent/auip/flight_query_presenter.py:13-37] 大段 magic string / constant
- **建议**：拆成独立的 `flight_labels.py` + `flight_classifier.py` 让 unit test 容易。

### [src/openagent/api/logging_setup.py:57-90] `_compact_event_renderer` 拼 markup 字符串
- **建议**：当前实现可读但每次都遍历 event_dict；可考虑把 `event` 字段提取出来用 `rich.console.Console().render` 一次渲染。

### [src/openagent/api/scenario_lifecycle.py:71-89] scenarios 加载路径不递归
- **建议**：与 `registry.load_from_paths` 一致用 `rglob` 支持子目录。

### [src/openagent/api/controllers/chat_controller.py:735-737] `if "ask_user" not in scenario_tools` 检查 O(N)
- **建议**：`tools_set = set(scenario_tools)` 再 `add()`。

### [src/openagent/providers/opencode_chat.py:60] `_FLIGHT_CARD_EMITTED: set[str]` 全局可变状态
- **建议**：移进 `OpenCodeAdapter._sessions` 的元数据，避免跨 session 干扰。

### [src/openagent/scenarios/config.py:191-236] `_cross_field` 警告不抛
- **建议**：文档化"警告 vs 错误"的开关；当前"P2-6 on_demand without hitl 警告"与"必要约束"混在一起，未来 grep 时容易误判严重性。

### [docs/ 全部 9 份 .md] 部分文档与代码漂移
- **建议**：CI 加 `lychee` 检查 dead link + `doctest` 或 `pytest-examples` 跑 README 代码块。

## ✨ 亮点

1. **5 层依赖方向强约束**（`scripts/ci_check.py` 强制 + `ALLOWED_DOWNWARD` 白名单）——这是规模化 Python 项目难得的纪律性设计。
2. **settings 中心化**（`openagent/config/settings.py` 526 行 + `env_sources.py` path-aware）——Hub 任何配置改动唯一入口；pydantic-settings 兜底 + `.env` 自动加载。
3. **Sensitive 信息脱敏**（`openagent/policy/audit.py` `redact_value` + `redact_path` + `redact_obj` 三层递归）——路径/字段双维度，路径还按 env-file/pem/ssh-key/generic 分类，**这是 Hub 部署到企业内网时的合规底气**。
4. **Sanic 错误分层**（4xx 透传 + 5xx 兜底 + SanicException 区分）——避免把 `/favicon.ico` 这种预期内探测当成 500 报警。
5. **opencode race 条件处理**（`_is_opencode_session_init_race` + `_post_session_message_raw` 3 次重试）——`ProviderModelNotFoundError` 短路；带有详细注释 + unit test；这是踩过坑的代码。
6. **Event hub 复用长连接**（`opencode_event_hub.py`）——避免每次 chat 50-200ms 握手，对热路径有可量化收益。
7. **Settings-snapshot 测试覆盖**：76% 的 test_ 函数集中在 `policy/` / `auip/` / `scenarios/` / `skill_runtime/`，核心领域模型有充分回归。

## 📊 维度评分

| 维度 | 评分(1-5) | 说明 |
|------|-----------|------|
| 正确性 | 3 | 多数主路径 OK；但 race 抑制、route regex 边界、SSE done 重复、chat 找 agent N² 等都是潜在 bug |
| 代码质量 | 3 | 命名/注释极佳；但 `routes.py` 1095 行死代码、`fragments.py` 末尾 12 行不可达代码、`except Exception:` 23 处吞错 |
| 结构与架构 | 4 | 5 层划分 + dependency enforcement + settings 中心化是非常好的工程实践；L1/L4 单文件过大是例外 |
| 可复用性 | 3 | `_turn_event_to_sse` / `_parse_minutes` / flight card 字段映射等多处复制粘贴；缺少 `auip/streaming/` / `auip/_duration.py` 等共享层 |
| 可读性 | 4 | 命名自解释、注释解释 why 而非 what；Chinese comments 跟代码职责匹配；但 `# pragma: no cover` 大面积铺开易被误读为"已经覆盖" |
| 可测试性 | 3 | 核心模块易单测（纯函数 + DI），但 launcher / sandbox 难 mock；前端 0 测试；`time.time()` / `uuid.uuid4()` 硬编码 |
| 可维护性 | 3 | settings 中心化加分；dead code / 行数超标 / 路由重复大幅减分；新增 scenario 流程闭环清晰 |
| 性能 | 3 | Event hub 长连接是亮点；O(N²) chat→agent 查找、`uuid` 函数内 import、`created_at = datetime.utcnow()` 老 API（NEP-29 已弃）需要修 |
| 安全性 | 3 | 路径黑名单 + 网络白名单 + audit 脱敏是好基底；但 MD5 哈希 + 密码/token 明文落日志 + 500 traceback 暴露是真实风险 |
| 可靠性 | 3 | 重试/超时/重载都做了；SSE 错误路径 + `done_written` 状态机混乱是隐患；Popen 阻塞 event loop 5s+ |
| 可观测性 | 4 | structlog 双模式（JSON / Rich）、scenario_middleware_ok / ready_check / opencode_session_error 等结构化事件齐全；DEBUG 级别的 raw log 反而过载 |
| 文档 | 4 | README / .env.example / 注释 / 设计文档（`docs/design/`）齐全；`.env.example` 是行业典范级别 |
| **综合** | **3.3** | 架构与文档扎实，但代码卫生（dead code / 行数 / 重复 / 错误吞错 / 边界条件）需要一次大扫除；进入生产前必做一轮"清理周" |

## 📈 风险热力图

- `src/openagent/api/routes.py`: 🔴 **高**（1095 行死代码 + 重复路由 + 双份 Pydantic model）
- `src/openagent/api/controllers/chat_controller.py`: 🔴 **高**（836 行 + SSE 状态机混乱 + chat→agent O(N) + race 抑制边界 + 路由 regex 过宽）
- `src/openagent/providers/opencode_chat.py`: 🔴 **高**（1206 行 + Popen 阻塞 + 资源管理边界 + race 抑制 3s vs 注释 1s）
- `src/openagent/api/controllers/auth_controller.py`: 🔴 **高**（明文 token 落日志 + MD5 协议依赖 + 整段 raw response 落 body）
- `src/openagent/skill_runtime/fragments.py`: 🔴 **高**（死代码 12 行 + token 估算粗略）
- `src/openagent/providers/launcher.py`: 🟡 **中**（Popen 同步阻塞 + 路径校验不查 symlink）
- `src/openagent/scenarios/middleware.py`: 🟡 **中**（router 引用缓存可泄漏旧对象）
- `src/openagent/policy/`: 🟢 **低**（设计扎实，audit 脱敏细致）
- `src/openagent/scenarios/`: 🟢 **低**（配置 Pydantic 校验强，loader 边界清晰）
- `src/openagent/store/`: 🟢 **低**（抽象简洁，Postgres + Memory 双实现，asyncpg 池管理得当）
- `src/openagent/auip/`: 🟢 **低**（卡片协议清晰，presenter 集中业务规则）
- `src/openagent/api/lifecycle.py`: 🟡 **中**（`bridge.register` 静默吞错 + skill 加载路径 fallback 不去重）
- `src/openagent/api/scenario_lifecycle.py`: 🟡 **中**（初始化失败仅日志，行为不明确）
- `src/openagent/api/logging_setup.py`: 🟢 **低**（设计优雅，Rich 主题 + structlog 双模式）
- `src/openagent/core/`: 🟡 **中**（scheduler / turn_store / suspendable_scheduler 三个文件都偏小，in-memory 实现可接受；`session.py` 是 1.x 时代残留）
- `src/openagent/sandbox/runtime.py`: 🟡 **中**（env 拼 argv 缺转义 + `_node_health_port` 端口从 URL 解析不可靠）
- `frontend/src/`: 🟡 **中**（0 测试 + console 可能泄露密码在错误路径 + AuthContext token 写到 localStorage 可选）
- `docker/`: 🟢 **低**（compose / Dockerfile 防御性做得好，env.runtime 持久化设计清晰）
- `scripts/`: 🟢 **低**（ci_check.py 5 层依赖 enforcement 优秀；verify_opencode_config.py 端到端自检）

## 🎯 Top 5 优先行动项

1. **删除 `src/openagent/api/routes.py` 整段死代码**（1095 行 + 重复路由 + 重复 Pydantic model），把 `_extract_mcp_token` / `_resolve_session_directory` 提到独立 `api/extractors.py`。建议紧接着跑一次 `pytest -k routes` + `curl /agent/chat` 端到端验证删除后系统照常。
2. **修复 `auth_controller.py` 日志泄露 + 500 traceback 泄露**（`auth_controller.py:296-300` raw response 落盘 + `app.py:87-105` 5xx 永远带 traceback）。同时把所有 `logger.info(..., token_value=token)` 改成 `token_len=len(token)`。这是合规红线——比"功能性 bug"优先级高。
3. **拆分 `chat_controller.py`（836 行）与 `opencode_chat.py`（1206 行）**到合理粒度（< 300 行/文件），把 SSE 拦截器（`_stream_with_keepalive` / `_stream_with_ask_user_intercept` / `_ask_user_to_card`）抽到 `api/streaming/` 独立模块。同时把 race 抑制的 `timeout=3.0` 改成跟注释一致的 `1.0`。
4. **`launcher.py` 把 `Popen` 改成 `asyncio.create_subprocess_exec`**（`stop()` 同步阻塞 event loop 5s+；优雅停机必踩），并显式管理句柄 close 避免泄漏。
5. **加前端测试基础设施**（`vitest` + `@testing-library/react`），至少覆盖 `AuthContext` 持久化策略 + `http` 拦截器 401 行为 + `LoginPage` `needsCaptcha` 状态切换。这条是补齐交付能力——目前 0 前端测试无法独立迭代前端改动。

## 📝 总体结论

**项目当前可运行**，架构纪律性、文档与基础设施扎实（5 层依赖 enforcement / settings 中心化 / 路径与网络白名单 / audit 脱敏三件套都是企业级水准），核心 streaming + agent 桥接的复杂竞态处理也踩过坑、修过坑。

**但代码卫生存在系统性问题**：
- 一份 1095 行的 `routes.py` 整段未挂载（refactor 留尾）；
- 12 行不可达代码裸放在 `_load_explicit` 末尾（cut-paste 留尾）；
- L1/L4 行数上限在 `ci_check.py` 写明 200/250，实际 836/1206 行；
- 23 处 `except Exception:` + 至少 1 处明文 token 落 `logger.info`；
- SSE done 状态机有 race。

**建议下一步路线图**：

**Phase A（必须，上线前 1 周）**：
- 删 `routes.py` + 修日志泄露 + 改 launcher 为 async subprocess + 修 race 抑制 3s→1s
- 把 `_turn_event_to_sse` / SSE 拦截器抽共享层
- 5xx 响应 traceback 用 `app.config.DEBUG` gate
- 给 frontend 加 vitest 最小集

**Phase B（建议，上线后 1 个月内）**：
- 拆 chat_controller / opencode_chat 到 < 300 行
- 前端 AuthContext 加 `httpOnly` cookie 模式 + 不再写 localStorage
- 加 `e2e` Playwright 跑 chat/stream/resume 三条主路径
- 加 `mypy` / `ruff` 严格 pre-commit gate

**Phase C（生产化）**：
- 引入 Alembic 替换 `SCHEMA` 内嵌 ALTER
- 引入 OpenTelemetry 替换裸 structlog（同一事件总线）
- 引入 `httpx` 连接池上限 / circuit breaker
- 多 agent pool 切换到 round-robin / least-loaded 调度（`acquire_idle_instance` 当前简单 O(N)）
- Postgres migration 加 `pgbouncer` / 连接池上限
- audit 通道改为 `kafka` / `pulsar` 而非 stdout print

整体风险等级 🟡 中；进入生产前完成 Phase A 的 6 项即可。
