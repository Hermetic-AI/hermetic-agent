# 周报

**周期**：2026-06-08 ~ 2026-06-12
**项目**：OpenAgent · 差旅 Agent（基于 OpenCode）

---

## 本周完成工作

### 1. 国内机票查询 Skill 升级与上下文治理

- **升级 `fh_domestic-flight-booking` Skill**：SKILL.md 主体规则修订约 36 行，归一化脚本、`progressive-search` 工作流、`booking-plan` schema、scenario yaml 同步调整；同步新增 MCP / OpenCode 调用映射的引用文档，强化三要素齐全时直接查询的策略。
- **新增「上下文记忆治理」约束**：在 Skill 目录 `references/` 下新增 `context-memory-governance.md`，约 137 行，对模型在多轮会话中的上下文累积、状态保持、跨阶段信息传递给出明确规则，避免上下文膨胀导致航班业务偏离。
- **构建 / 鉴权 / 测试补全**：新增 `Dockerfile.frontend` + `docker-compose.frontend` + `nginx.frontend.conf` + `.dockerignore`，补齐鉴权控制器、`AuthContext`、登录页与登录样式；新增 5 套测试（鉴权、MCP Token、场景航班卡等），构建链路首次端到端可演示。

### 2. 交互流程与 AGUI 卡片协议完善

- **航班结果卡片重排版**：重做 `FlightResultCard.tsx` 票面布局，新增「最便宜 / 最快 / 舒适首选」分组展示，修复大量字段展示问题。
- **AGUI 协议兜底与拦截增强**：
  - 修复后端无法连接 MCP 的问题、工具调用不返回信息的问题；
  - 新增 `_ask_user_to_card` 拦截路径下「状态补充卡片」能力：用户在对话中询问当前状态时，Hub 可主动补发 `OD_INPUT` / 状态提示类结构化卡片；
  - 修复多轮对话中卡片渲染卡住、白屏、样式错位等问题（`CannotOrderCard` / `ChatFallbackCard` / `FormCard` / `OrderConfirmCard` / `OrderSuccessCard` / `PolicyDecisionCard` / `PriceVerifyCard` / `SelectionListCard` 全部同步更新）；
  - 前后端 `card_type` / `card_id` 字段补齐，前端按协议渲染稳定。
- **场景与路由层调整**：scenario yaml 调整约 94 行，scenario_loader / scenario 集成测试同步跟进，路由层从「场景名 → 业务场景」映射更稳定。

### 3. 部署与打包流程优化

- **配置中心化**：将 Hub 侧 Python 全部硬编码常量下沉到 `src/openagent/config/settings.py`（14 段 / 约 80 字段），各模块保留 `*_FALLBACK` 兜底常量 + lazy getter 模式，import 期不再触发 `.env` 解析。
- **覆盖范围**：Agent Pool 健康检查 / Provider Launcher / OpenCode Chat / Sandbox Runtime / Sanic 超时 / Skill fragment budget / Auth / Scenario lifecycle 等全面接入 settings；`.env.example` 14 段重排。
- **日志体系升级**：引入 `structlog` + `Rich` 终端彩色渲染，新增 `tests/test_logging_console.py`，docker 容器配置 `FORCE_COLOR=1` + `TERM=xterm-256color` 让 Rich 配色在 `docker logs` 中正常显示。
- **P0 修复**：SSE 断流根因修复（多层 async generator 的 `GeneratorExit` 路径、OpenCode `chat_task` 异常传播）；opencode 容器内插件安装 / `models.dev` 索引在只读根 FS 上 EROFS 的问题通过 tmpfs 解决。
- **构建文档**：补全 `docs/BUILD.md`，覆盖本地 / 镜像 / 前端三种打包路径。

### 4. 周四演示与下一步方案

- **周四完成差旅 Agent 端到端演示**：覆盖自然语言查询 → MCP 工具调用 → AGUI 航班卡片 → 选舱 → 乘机人 / 出差单 / 成本中心 → 订单预览主流程。
- **敲定下一步计划**：
  - 目标 **3 周左右** 再次碰头做一次阶段性演示；
  - 下一阶段由本人主导做 **国际机票查询业务** Skill，与刘渊那边并行开发——后续他那边做国内机票（升级版），最终通过 **主路由 Agent** 路由到各查询业务场景；
  - 主路由 Agent 需要重点设计：场景识别、并发 / 串行调度、跨场景上下文共享与回退。
- **同步输出演示材料**：完成 `docs/travel-agent-technical-demo.md`（2056 行技术演示文档）+ `docs/travel-agent-ppt.html`（11 页技术 PPT）+ `docs/travel-agent-demo-question-bank.md`（演示问答库）。

### 5. 代码重构与 AI 生成代码规范治理

- **大规模架构重构落地**（4 大块、109 个文件、净瘦身约 4800 行）：
  - **代码可读性 / 死代码清理**：删 `routes.py` 1095 行死代码、SSE 拦截器抽到 `api/streaming/` 独立模块（`chat_controller.py` 由 836 → 654 行）、`auip/_duration.py` 与 `_flight_mapping.py` 共享辅助（`flight_card.py` 由 296 → 214 行，遵守 L3 ≤ 250 行约束）；
  - **模块分层合并**：`skill_runtime/*` 物理合并到 `skills/runtime/*`（领域 vs 框架分层）；`streaming.py` 迁到 `providers/`；`api/` 拆 4 个子包（`app/` / `http/` / `lifecycle/` / `shared/`）；`providers/` 拆 `opencode/` + `claude_code/` 子包；
  - **P0 修复**：token 落日志、5xx 总是带 traceback、同步 Popen 阻塞 event loop、Agent 全局 set 跨 adapter 池污染、404 误报等共 16 项；
  - **兼容层**：3 重 shim 链保留外部 caller 100% 兼容，后续 Phase 删除。
- **CI 与静态检查**：`ruff` 162 → 13 errors（自动修 149 个），`ci_check` 0 NEW 违例；测试 662 passed / 89 failed（与重构前 baseline 持平，0 漂移，失败用例均为 pre-existing 异步时序问题）。
- **AI 生成代码结构与格式规范**：补全 `scripts/ci_check.py` 检查项（文件行数、依赖方向、命名规范、import 排序），建立 L1~L5 分层依赖约束；抽 `_resolve_or_create_session`、`DoneGate`、`_FLIGHT_CARD_EMITTED` 弱引用等通用模式作为后续 AI 生成的参考样板。
- **Agent / RAG 方案梳理**：完成 `docs/open-source-evolution-plan.md`（445 行）开源化演进方案，明确把当前 `agent-scheduler-hub` 演进为通用 Agent 基座的目标、关键约束、阻碍开源的硬伤清单、5 个 Milestone 的渐进可发布路线，以及飞鹤业务剥离但不下线的原则；同时补充双 SDK（opencode / claude-agent）架构文档、PostgreSQL 持久化方案、Agent Scheduler 评审稿等。

---

## 本周工作总结

- **节奏**：本周属于「一边收尾 demo、一边打底 v1.0」的高密度周，前半周把卡片体验与 Skill 规则推稳，后半周集中做配置中心、部署链路、架构重构三件硬骨头；周四演示顺利收官，演示后迅速把国际机票 / 主路由 Agent 的下一步方向明确。
- **价值沉淀**：通过「重构 + 配置中心 + CI 规则」三件事，把工程基线从「可演示」抬到「可维护、可扩展」；通过 `travel-agent-technical-demo` + PPT + 问答库，把项目叙事从「内部技术细节」沉淀为「对外可讲解的故事」。
- **风险与短板**：
  - **测试 baseline 仍有 89 个失败用例**（集中在 `todo_controller` 异步时序），未在本周收敛，下周需重点跟进；
  - **主路由 Agent** 设计未启动，是下一阶段最大不确定性；
  - **国际机票 Skill** 与刘渊侧国内机票升级版存在并行边界，需尽快明确「主路由 Agent → 业务 Skill」的协议契约，避免两边接口不一致返工。

---

## 下周工作计划

1. **测试基线收敛**：把 `todo_controller` 等 89 个 pre-existing 失败用例逐个归因 + 修复或标注，CI 流转可作为合并门禁。
2. **Skill 升级版 V2 起草**：基于本周 `fh_domestic-flight-booking` 的实战反馈，沉淀「Skill 升级模板」，给国际机票 Skill 提供参考骨架。
3. **主路由 Agent 方案设计**：
   - 输出 `docs/main-router-agent-design.md`：场景识别策略、并发 / 串行调度、跨场景上下文隔离 / 共享、错误回退、与 Skill / MCP 的协议契约；
   - 与刘渊对齐「主路由 → 国内机票 / 国际机票」接口边界；
4. **国际机票 Skill 调研与脚手架**：
   - 梳理国际机票 MCP 工具能力（与 `feihe-travel` 团队对接）、IATA / ICAO 码翻译、币种 / 时区 / 中转处理；
   - 落 `work/shared/skills/fh-international-flight-search/SKILL.md` 初稿与 `scenario.yaml` 初稿；
5. **CI / 静态检查收尾**：`ruff` 剩余 13 个 N818 / I001 全部清零；`ci_check.py` 增补 AI 生成代码专属规则（如「禁止在 controller 内出现 > 250 行」「禁止跨层 import」）。
6. **演示复盘与下周演示准备**：周四演示录像 / 反馈整理；3 周后演示大纲初版。

---

## 需协调与帮助

| 主题 | 现状 | 希望获得的支持 |
|---|---|---|
| **国际机票 MCP 工具** | `feihe-travel` 团队是否提供国际机票查询 MCP？接口范围、字段约定、QPS 限制未明 | 与差旅产品 / `feihe-travel` 后端约一次对齐会，明确可用工具清单与权限模型 |
| **主路由 Agent 协议边界** | 我与刘渊并行做国际 / 国内机票，需要统一「主路由 → 业务场景」协议 | 约定一次 30-60 分钟方案评审，确定 router 协议（输入 / 输出 / 状态 / 错误码） |
| **测试 89 个失败用例** | `todo_controller` 等异步时序问题单点难收敛 | 希望测试同学协助看一次并发用例运行机制，给出统一收敛方案 |
| **演示资源** | 3 周后演示需要可演示的国际机票能力 + 主路由调度能力 | 申请一段集中的「联调窗口」与刘渊侧对齐时间 |
| **AI 代码生成规范** | 已落 `ci_check` 规则，但团队内其他 AI 助手 / 同事生成代码未统一 | 推动团队层面 `AGENTS.md` 落地，把 L1~L5 分层、行数约束、命名规范变成全员默认 |

---

## 备注

- 本周提交记录 18 次 commit（含 1 次大规模重构 + 配置中心双发 + Skill 升级 + 卡片修复 + 演示文档沉淀），分支 `dev/1.0.0-0-code-review` 当前 ahead of `origin` 0 commit，已通过 `ci_check` 与测试 baseline 持平。
- 本周新增 / 修订的对外文档：`docs/travel-agent-technical-demo.md`、`docs/travel-agent-ppt.html`、`docs/travel-agent-demo-question-bank.md`、`docs/BUILD.md`、`docs/open-source-evolution-plan.md`、`docs/配置文件重构总结.md`，可在 Confluence / 飞书文档同步分发。
- 周四演示录像与提问清单已沉淀到 `docs/travel-agent-demo-question-bank.md`，可作为团队内训与对外讲解素材。
