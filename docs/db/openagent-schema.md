# hermetic_agent · MySQL 8 持久化 Schema 设计说明

> 版本: **v2**  ·  数据库: `hermetic_agent`  ·  引擎: InnoDB  ·  字符集: utf8mb4 / utf8mb4_0900_ai_ci
> 适用对象: hermetic_agent Agent Scheduler Hub
> 配套脚本:
> - 完整 schema: [`hermetic_agent-schema.sql`](./hermetic_agent-schema.sql)
> - v1→v2 数据迁移: [`migrate-v1-to-v2.sql`](./migrate-v1-to-v2.sql)
>
> 参考: 对照 `relate_project/opencode/` 设计,采纳其 3 表拆 session/message/part、复合排序索引、token/cost 聚合反规范化等模式

---

## 1. 设计原则

| # | 原则 | 落地方式 |
|---|------|---------|
| 1 | **统一主键风格** | 所有表主键统一 `CHAR(36)` UUID, 由应用层生成 UUIDv4 |
| 2 | **软删除为默认** | 业务表一律 `is_deleted TINYINT(1) NOT NULL DEFAULT 0` + `deleted_at DATETIME(6) NULL` |
| 3 | **审计字段必备** | `created_at / updated_at DATETIME(6)`, 后者 `ON UPDATE CURRENT_TIMESTAMP(6)` |
| 4 | **元数据走 JSON** | 业务扩展字段一律 JSON 列(MySQL 8 原生) |
| 5 | **外键显式声明** | 跨表关系都建外键约束, 级联策略明确 |
| 6 | **DDL 幂等** | `DROP IF EXISTS + CREATE`,启动期可重置 |
| 7 | **命名规范** | 表名小写下划线复数 (`sessions`); 主键名统一 `id`; 外键列 `<resource>_id` |
| 8 | **冗余反规范化** | `parts.session_id` 冗余 / `sessions.tokens_*` 聚合 — 来自 opencode 启发 |
| 9 | **复合索引带 id tie-breaker** | `(..., created_at, id)` 支持稳定分页游标 |
| 10 | **注释完备** | 表/字段全加 `COMMENT` |

---

## 2. 表清单 (v2)

| # | 表名 | 角色 | 关键变化 (vs v1) |
|---|------|------|-----------------|
| 1 | `scenarios` | 场景定义/快照 | ➕ `parent_id` 自引用版本链 |
| 2 | `sessions` | 对话主表 | ➕ `message_count` + 5 个 token/cost 聚合字段 |
| 3 | `chat_turns` | 单轮执行单元 | ➕ 5 个本 turn token 字段 + 索引加 id tie-breaker |
| 4 | `messages` | 消息 | ➖ `parts` JSON 列已拆出 + 索引加 id tie-breaker |
| 5 | **`parts`** | 消息分段 (v2 新增) | ✨ 从 messages.parts 拆出 + `session_id` 冗余 |
| 6 | `audit_logs` | 审计日志 | ➕ `seq` 事务序号 + 索引重构 |

> `users` / `agents` 仍未建表 — 现有 `user_id` 仍是外部传入字符串; `AgentPool` 仍是纯内存运行时。

---

## 3. ER 关系

```
                                    ┌──────────────┐
                                    │  scenarios   │ 业务短码+版本号 唯一
                                    │  id (PK)     │
                                    │  code        │
                                    │  version     │
                                    │  parent_id ──┼──┐ (自引用, 版本链)
                                    │  config JSON │  │
                                    └──────┬───────┘  │
                                           │ 1        │
                                           │          │
                                           │ N        ▼
                                    ┌──────▼───────┐
                                    │  sessions    │ + message_count
                                    │  id (PK)     │ + cost / tokens_*
                                    │  user_id     │ (聚合, 不强一致)
                                    │  scenario_id │
                                    │  status      │
                                    └──────┬───────┘
                                           │ 1
                              ┌────────────┼────────────┐
                              │ N                      │ N
                       ┌──────▼───────┐         ┌──────▼───────┐
                       │  messages    │  N   1  │  chat_turns  │
                       │  id (PK)     │◀────────│  id (PK)     │
                       │  turn_id     │         │  cost        │
                       │  role        │         │  tokens_*    │
                       └──────┬───────┘         └──────────────┘
                              │ 1
                              │
                              │ N
                       ┌──────▼───────┐         ┌──────────────┐
                       │  parts  ✨   │ 1    N  │  audit_logs  │
                       │  id (PK)     │────────▶│  resource_id │
                       │  message_id  │         │  seq         │
                       │  session_id ─┼─(冗余)  │  (append)    │
                       │  part_type   │         └──────────────┘
                       │  position    │
                       └──────────────┘
```

### 外键清单

| 子表 | 外键 | 父表 | 级联 |
|------|------|------|------|
| `scenarios` | `parent_id` | `scenarios.id` | `SET NULL` (自引用版本链) |
| `sessions` | `scenario_id` | `scenarios.id` | `SET NULL` |
| `chat_turns` | `session_id` | `sessions.id` | `CASCADE` |
| `messages` | `session_id` | `sessions.id` | `CASCADE` |
| `messages` | `turn_id` | `chat_turns.id` | `SET NULL` |
| `parts` | `message_id` | `messages.id` | `CASCADE` |

> `audit_logs.resource_id` **不建外键**: 审计日志 append-only, 业务上不希望删除受日志约束。

---

## 4. 索引设计

| 表 | 索引 | 列 | 用途 |
|----|------|----|------|
| `scenarios` | `PRIMARY` | `id` | 主键 |
| | `uk_scenarios_code_version` UNIQUE | `(code, version)` | 同 code 业务唯一 |
| | `idx_scenarios_status` | `(status, is_deleted, updated_at, id)` | 查启用中场景, id tie-breaker |
| | `idx_scenarios_parent` | `parent_id` | 查版本链 |
| | `idx_scenarios_updated` | `updated_at` | 全局时间线 |
| `sessions` | `PRIMARY` | `id` | 主键 |
| | `idx_sessions_user` | `(user_id, is_deleted, updated_at, id)` | 用户会话列表(最常见) |
| | `idx_sessions_agent` | `(agent_name, is_deleted, updated_at, id)` | Agent 维度 |
| | `idx_sessions_scenario` | `scenario_id` | 场景维度 |
| | `idx_sessions_updated` | `updated_at` | 全局时间线 |
| `chat_turns` | `PRIMARY` | `id` | 主键 |
| | `idx_turns_session` | `(session_id, is_deleted, created_at, id)` | 拉某 session 全部 turn |
| | `idx_turns_status` | `(status, is_deleted, created_at, id)` | 监控 pending/running/failed |
| | `idx_turns_started` | `started_at` | 监控/报表 |
| `messages` | `PRIMARY` | `id` | 主键 |
| | `idx_messages_session` | `(session_id, is_deleted, created_at, id)` | 拉历史 + 稳定分页 |
| | `idx_messages_turn` | `turn_id` | 查某 turn 关联消息 |
| | `idx_messages_role` | `(role, is_deleted)` | 按角色筛选 |
| `parts` | `PRIMARY` | `id` | 主键 |
| | `idx_parts_message` | `(message_id, is_deleted, position, id)` | 拉某 message 全部 part |
| | `idx_parts_session` | `(session_id, is_deleted, created_at, id)` | 拉某 session 全部 part, **省去 JOIN message** |
| | `idx_parts_type` | `(part_type, is_deleted, created_at, id)` | 按 part_type 统计(如所有 tool_call) |
| `audit_logs` | `PRIMARY` | `id` | 主键 |
| | `idx_audit_resource_seq` | `(resource_type, resource_id, seq, created_at)` | 资源事件流 |
| | `idx_audit_actor` | `(actor_type, actor_id, created_at, id)` | 用户行为追溯 |
| | `idx_audit_action` | `(action, created_at, id)` | 行为类型统计 |

**设计原则**:
- 软删除字段 `is_deleted` 总是组合索引的等值过滤位
- 时间字段 `created_at` / `updated_at` 放在范围/排序位
- **`id` 永远在索引最后** — 作为 tie-breaker,保证 `(session_id, created_at)` 同时间的多行有稳定顺序,分页游标可重现
- 唯一索引 `uk_scenarios_code_version` 不带 `is_deleted`(MySQL 8 不支持条件唯一索引), 业务层保证软删后允许 `code+version` 复活

---

## 5. 字段类型约定

| 类别 | 选型 | 原因 |
|------|------|------|
| 主键 | `CHAR(36)` | UUID 字符串, 易读; 36 字节, B+Tree 节点填充率较低但运维方便 |
| 短字符串 (≤ 64) | `VARCHAR(N)` | 节省空间 |
| 标题/名称 (≤ 255) | `VARCHAR(255)` | utf8mb4 下完整中文可达 85 字 |
| 长文本 | `TEXT` / `MEDIUMTEXT` | `parts.content` 选 MEDIUMTEXT (16MB) |
| 数值状态 | `VARCHAR(32)` + 注释 | 业务枚举变更零成本 |
| 货币 | `DECIMAL(12,6)` | `cost`, 避免浮点精度问题 |
| 数值计数 | `INT UNSIGNED` | `tokens_*` 不会为负 |
| 时间戳 | `DATETIME(6)` | 微秒精度, 业务时区不依赖 session 变量 |
| 事务序号 | `BIGINT UNSIGNED` | `audit_logs.seq`, 单库理论上限足够 |
| 元数据 | `JSON` | MySQL 8 原生, 支持 `JSON_EXTRACT` |
| 布尔 | `TINYINT(1) NOT NULL DEFAULT 0` | MySQL 没有 BOOLEAN, 标准做法 |

---

## 6. 软删除约定

- **应用层过滤**: 所有读路径 SQL 必须带 `is_deleted = 0`(`audit_logs` 例外, 它本身就是 append-only)
- **删除语义**: 不物理删除, `UPDATE ... SET is_deleted=1, deleted_at=NOW(6) WHERE id=?`
- **后台清理**: 保留 `deleted_at` 字段用于"30 天归档 / 90 天物理删除"等后台任务
- **唯一索引与软删**: `uk_scenarios_code_version (code, version)` 不带 `is_deleted`, 因为 MySQL 8 InnoDB 不支持条件唯一索引。应用层 SELECT FOR UPDATE 兜底

---

## 7. v1 → v2 升级变更

| 变更 | 风险 | 迁移策略 |
|------|------|---------|
| **拆 `parts` 表** (从 `messages.parts` JSON) | 中: 大表 `JSON_TABLE` 解析耗时长 | `INSERT ... SELECT FROM JSON_TABLE(...)`, 见 [`migrate-v1-to-v2.sql`](./migrate-v1-to-v2.sql) 阶段 2 |
| **`sessions` 加 7 个聚合字段** | 低: `DEFAULT 0` 立即回填 | 一条 `ALTER TABLE ... ADD COLUMN` + 阶段 3 反向汇总 UPDATE |
| **`scenarios` 加 `parent_id`** | 低: NULL 即可 | `ADD COLUMN + ADD CONSTRAINT` |
| **复合索引重建** | 中: DROP + ADD 期间无索引 | 业务低峰执行 |
| **`audit_logs` 加 `seq`** | 低: 默认 NULL 不破坏旧数据 | `ADD COLUMN` |

**执行建议**:
1. 停服
2. `mysqldump` 全量备份
3. 跑 `migrate-v1-to-v2.sql`(先 stage 0 备份, 再 stage 1-4)
4. 跑烟囱测试 SQL 验证
5. 启服

详细回滚策略见 `migrate-v1-to-v2.sql` 文件头注释。

---

## 8. 与 opencode 的对照 (借鉴 vs 不照搬)

| opencode 特性 | hermetic_agent 采纳 | 备注 |
|---------------|---------------|------|
| `session`/`message`/`part` 3 表拆 | ✅ 采纳 | parts.session_id 冗余一并采纳 |
| `(session_id, time_created, id)` 复合索引 | ✅ 采纳 | 我们用 `DATETIME(6)` 替代 `integer` 毫秒 |
| 业务字段全塞 JSON `text(json)` | ⚠️ 部分采纳 | MySQL 8 用原生 `JSON` 类型, 不需要 `text + mode:json` |
| 软删除 → `time_archived` 状态字段 | ❌ 不采纳 | 合规/审计场景不合适, 保留 `is_deleted + deleted_at` |
| `event` + `event_sequence` Event Sourcing | ❌ 不采纳 | 业务简单, `audit_logs` 足够 |
| `session_message` 第二类消息 | ❌ 不采纳 | 等业务真出现再补 |
| `permission` / `account` / `control_account` | ❌ 不采纳 | 等需求来了再加 |
| `data_migration` 表 + 自管 migration runner | ❌ 不采纳 | 用 DDL 幂等 + 启动期执行, 简单可控 |
| `DatabasePath.absoluteColumn` 平台路径归一 | ❌ 不采纳 | hermetic_agent 是服务端 Linux/Docker, 路径问题少 |
| 表名单数 (`session`, `message`, `part`) | ❌ 保留复数 | 与 Django/Java 风格一致 |

---

## 9. 与现有代码的对接 (后续)

| 现有模块 | 改造点 |
|---------|--------|
| `src/hermetic_agent/store/base.py` | `SessionRepository` ABC 不变, 新增 `ScenarioRepository` / `ChatTurnRepository` / `PartRepository` / `AuditLogRepository` |
| `src/hermetic_agent/store/postgres.py` | 替换驱动为 `asyncmy`, 拆出独立 DDL 字符串, 启动期 `engine.execute(SCHEMA)` |
| `src/hermetic_agent/store/memory.py` | 保留 dev/test, 多加内存实现 |
| `src/hermetic_agent/store/__init__.py` | 工厂模式扩展 |
| `src/hermetic_agent/scenarios/registry.py` | `load_from_db` stub 已有, 接入 `ScenarioRepository.list_active()` |
| `src/hermetic_agent/config/settings.py` | 把 `postgres_dsn` 改为通用 `database_url`, 解析 MySQL DSN |

**驱动选型建议**:
- **`asyncmy`** (推荐): 纯异步, 性能最好, Sanic 全异步栈首选
- `aiomysql`: 老牌, 兼容性稳

---

## 10. 烟囱测试结果 (v2, 已通过)

```
✅ scenarios 版本链: flight-booking v2.parent_id → v1
✅ sessions 聚合: message_count=2, tokens_input=150, tokens_output=80 (反向汇总与 chat_turns 一致)
✅ parts 独立表: 3 条 part 正确分配 (text/tool_call/text), session_id 冗余有效
✅ 拉某 session 完整对话: 1 条 SQL JOIN messages + parts, 不需要反查
✅ audit_logs seq: 两条日志 seq=1, 2 稳定排序
✅ FK 级联: 6 个外键全部 CASCADE / SET NULL 正确
```

---

## 11. 后续 TODO

- [ ] 选 MySQL 驱动 (`asyncmy` 推荐)
- [ ] 改造 `store/base.py` 抽象 + 新增 PartRepository
- [ ] 配置层加 `database_url` (MySQL DSN), 替换 `postgres_dsn`
- [ ] `ScenarioRegistry.load_from_db()` 接入 (新场景走 DB, YAML 仅作 seed)
- [ ] session 聚合字段的反向汇总: 写 turn 时同步 `UPDATE sessions` (事务内) 或后台定时器
- [ ] 监控指标: parts 表行数分布 / session 聚合字段与 turn SUM 一致性
- [ ] 决定是否上 event_sourcing (当前 audit_logs 足够, 但要补 seq 启用的客户端封装)
