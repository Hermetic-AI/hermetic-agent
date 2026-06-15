-- ============================================================================
-- OpenAgent · v1 → v2 数据迁移脚本(保数据)
-- ----------------------------------------------------------------------------
-- 适用场景: v1 schema 已落库且有数据时,需要无损升级到 v2
-- 风险:   ALTER TABLE 大表耗时长,需要停机维护窗口
-- 反向:   v2 → v1 没有自动回滚脚本,务必先备份
--
-- v2 主要变更:
--   1. messages.parts JSON → 独立 parts 表
--   2. sessions 加 token/cost 聚合字段
--   3. scenarios 加 parent_id 版本链
--   4. messages/chat_turns/parts 索引加 id tie-breaker
--   5. audit_logs 加 seq 字段
-- ============================================================================

USE openagent;

-- ----------------------------------------------------------------------------
-- 阶段 0: 备份(强烈建议手动 mysqldump 一次)
-- ----------------------------------------------------------------------------
-- 停服后,在 mysql 外执行:
--   mysqldump -uroot -p1014 openagent > openagent_v1_backup_$(date +%Y%m%d_%H%M%S).sql


-- ----------------------------------------------------------------------------
-- 阶段 1: ALTER 现有表(加字段、加索引、加约束)
-- ----------------------------------------------------------------------------

-- 1.1 sessions 加聚合字段
ALTER TABLE sessions
    ADD COLUMN message_count       INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '消息条数缓存' AFTER status,
    ADD COLUMN cost                DECIMAL(12,6)   NOT NULL DEFAULT 0                COMMENT '累计花费 USD'     AFTER message_count,
    ADD COLUMN tokens_input        INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 input tokens'  AFTER cost,
    ADD COLUMN tokens_output       INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 output tokens' AFTER tokens_input,
    ADD COLUMN tokens_reasoning    INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 reasoning tokens' AFTER tokens_output,
    ADD COLUMN tokens_cache_read   INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 cache read tokens'  AFTER tokens_reasoning,
    ADD COLUMN tokens_cache_write  INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 cache write tokens' AFTER tokens_cache_read;

-- 1.2 scenarios 加 parent_id
ALTER TABLE scenarios
    ADD COLUMN parent_id CHAR(36) NULL COMMENT '上一版本场景 ID' AFTER version,
    ADD KEY idx_scenarios_parent (parent_id),
    ADD CONSTRAINT fk_scenarios_parent FOREIGN KEY (parent_id) REFERENCES scenarios(id) ON DELETE SET NULL;

-- 1.3 chat_turns 加本 turn token 字段
ALTER TABLE chat_turns
    ADD COLUMN cost                  DECIMAL(12,6)  NOT NULL DEFAULT 0               COMMENT '本 turn 花费 USD'    AFTER duration_ms,
    ADD COLUMN tokens_input          INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn input tokens'  AFTER cost,
    ADD COLUMN tokens_output         INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn output tokens' AFTER tokens_input,
    ADD COLUMN tokens_reasoning      INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn reasoning tokens' AFTER tokens_output,
    ADD COLUMN tokens_cache_read     INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn cache read tokens'  AFTER tokens_reasoning,
    ADD COLUMN tokens_cache_write    INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn cache write tokens' AFTER tokens_cache_read;

-- 1.4 重建复合索引(原索引名带不带 id,统一重建)
ALTER TABLE sessions
    DROP INDEX idx_sessions_user,
    DROP INDEX idx_sessions_agent,
    DROP INDEX idx_scenarios_status,                 -- 不存在,会报错,见下方条件 DROP
    ADD KEY idx_sessions_user (user_id, is_deleted, updated_at, id),
    ADD KEY idx_sessions_agent (agent_name, is_deleted, updated_at, id);

ALTER TABLE scenarios
    DROP INDEX idx_scenarios_status,
    ADD KEY idx_scenarios_status (status, is_deleted, updated_at, id);

ALTER TABLE chat_turns
    DROP INDEX idx_turns_session,
    DROP INDEX idx_turns_status,
    ADD KEY idx_turns_session (session_id, is_deleted, created_at, id),
    ADD KEY idx_turns_status (status, is_deleted, created_at, id);

ALTER TABLE messages
    DROP INDEX idx_messages_session,
    ADD KEY idx_messages_session (session_id, is_deleted, created_at, id);

-- 1.5 audit_logs 加 seq
ALTER TABLE audit_logs
    ADD COLUMN seq BIGINT UNSIGNED NULL COMMENT '同资源下的事务序号' AFTER id,
    DROP INDEX idx_audit_resource,
    DROP INDEX idx_audit_actor,
    DROP INDEX idx_audit_action,
    ADD KEY idx_audit_resource_seq (resource_type, resource_id, seq, created_at),
    ADD KEY idx_audit_actor (actor_type, actor_id, created_at, id),
    ADD KEY idx_audit_action (action, created_at, id);


-- ----------------------------------------------------------------------------
-- 阶段 2: 创建新表 parts,并从 messages.parts 迁移数据
-- ----------------------------------------------------------------------------
CREATE TABLE parts (
    id            CHAR(36)        NOT NULL                                COMMENT '主键 UUID',
    message_id    CHAR(36)        NOT NULL                                COMMENT '所属 message',
    session_id    CHAR(36)        NOT NULL                                COMMENT '冗余: 所属 session',
    part_type     VARCHAR(32)     NOT NULL                                COMMENT 'text / image / tool_call / tool_result / file',
    content       MEDIUMTEXT      NULL                                    COMMENT '段内容',
    position      INT UNSIGNED    NOT NULL DEFAULT 0                      COMMENT '段在 message 内的顺序',
    metadata      JSON            NULL                                    COMMENT '扩展元数据',
    is_deleted    TINYINT(1)      NOT NULL DEFAULT 0                      COMMENT '软删除标记',
    deleted_at    DATETIME(6)     NULL                                    COMMENT '软删除时间',
    created_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    PRIMARY KEY (id),
    KEY idx_parts_message (message_id, is_deleted, position, id),
    KEY idx_parts_session (session_id, is_deleted, created_at, id),
    KEY idx_parts_type (part_type, is_deleted, created_at, id),
    CONSTRAINT fk_parts_message FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='消息分段(v1 messages.parts JSON 拆出)';

-- 2.1 把 messages.parts JSON 数组转成 parts 行
-- MySQL 8 的 JSON_TABLE 支持把 JSON 数组展开成行
INSERT INTO parts (id, message_id, session_id, part_type, content, position, metadata, is_deleted, created_at, updated_at)
SELECT
    COALESCE(JSON_UNQUOTE(JSON_EXTRACT(p.part, '$.id')), UUID())           AS id,
    m.id                                                                   AS message_id,
    m.session_id                                                           AS session_id,
    JSON_UNQUOTE(JSON_EXTRACT(p.part, '$.part_type'))                      AS part_type,
    JSON_UNQUOTE(JSON_EXTRACT(p.part, '$.content'))                        AS content,
    p.idx - 1                                                              AS position,  -- JSON_TABLE 序号从 1 开始,position 从 0
    JSON_EXTRACT(p.part, '$.metadata')                                     AS metadata,
    m.is_deleted                                                           AS is_deleted,
    m.created_at                                                           AS created_at,
    m.created_at                                                           AS updated_at
FROM messages m,
     JSON_TABLE(
         COALESCE(m.parts, JSON_ARRAY()),
         '$[*]' COLUMNS (
             idx     FOR ORDINALITY,
             part    JSON         PATH '$'
         )
     ) AS p
WHERE m.parts IS NOT NULL
  AND JSON_LENGTH(m.parts) > 0;

-- 2.2 给老 parts(没显式 id 字段的)补默认值
-- 上面 SQL 已经用 COALESCE 兜底,这里无需额外处理

-- 2.3 校验数据量
-- SELECT COUNT(*) AS old_parts_sum FROM messages WHERE parts IS NOT NULL;
-- SELECT COUNT(*) AS new_parts_total FROM parts;

-- 2.4 删除 messages.parts 列
ALTER TABLE messages DROP COLUMN parts;


-- ----------------------------------------------------------------------------
-- 阶段 3: 反向汇总 sessions 聚合字段(从 chat_turns + messages)
-- ----------------------------------------------------------------------------
UPDATE sessions s
  LEFT JOIN (
    SELECT session_id, COUNT(*) AS cnt
    FROM messages WHERE is_deleted = 0 GROUP BY session_id
  ) m ON m.session_id = s.id
  LEFT JOIN (
    SELECT session_id,
           SUM(cost) AS cost, SUM(tokens_input) AS ti, SUM(tokens_output) AS to_,
           SUM(tokens_reasoning) AS tr, SUM(tokens_cache_read) AS tcr, SUM(tokens_cache_write) AS tcw
    FROM chat_turns GROUP BY session_id
  ) t ON t.session_id = s.id
SET s.message_count      = COALESCE(m.cnt, 0),
    s.cost               = COALESCE(t.cost, 0),
    s.tokens_input       = COALESCE(t.ti, 0),
    s.tokens_output      = COALESCE(t.to_, 0),
    s.tokens_reasoning   = COALESCE(t.tr, 0),
    s.tokens_cache_read  = COALESCE(t.tcr, 0),
    s.tokens_cache_write = COALESCE(t.tcw, 0);


-- ----------------------------------------------------------------------------
-- 阶段 4: 启动期幂等补丁(此后运行 openagent-schema.sql 全部 IF EXISTS 也无副作用)
-- ----------------------------------------------------------------------------
-- 校验:
--   SELECT COUNT(*) FROM parts;                       -- 应等于原 messages.parts JSON 元素总数
--   SELECT message_count, tokens_input FROM sessions; -- 聚合字段已填
--   SELECT code, version, parent_id FROM scenarios;   -- 新列存在

-- 阶段 1 的 ALTER ... DROP INDEX 失败的话,说明 v1 索引名不一致,
-- 可改用更安全的做法(只 ADD 不 DROP,然后用 RENAME):
--   ALTER TABLE sessions RENAME INDEX old_name TO new_name;
-- 或在 MySQL 8 之前手动查 information_schema.STATISTICS 拿到旧索引名。
