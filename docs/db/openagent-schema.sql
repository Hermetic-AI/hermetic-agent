-- ============================================================================
-- OpenAgent · MySQL 8 持久化 Schema (v2)
-- ----------------------------------------------------------------------------
-- 数据库 : openagent
-- 字符集 : utf8mb4 / utf8mb4_0900_ai_ci
-- 引擎   : InnoDB
-- 规范要点:
--   * 主键统一 CHAR(36) UUID,由应用层生成(UUIDv4)
--   * 软删除: is_deleted TINYINT(1) + deleted_at DATETIME(6) NULL
--   * 审计字段: created_at / updated_at DATETIME(6) 默认 CURRENT_TIMESTAMP(6)
--   * 业务元数据一律 JSON 列(parts / metadata / config)
--   * 外键显式声明 + ON DELETE CASCADE / SET NULL
--   * 所有表/字段加 COMMENT,运维/生成文档友好
--   * 幂等: DROP IF EXISTS + CREATE,启动期可重置执行
--
-- v2 相对 v1 的改动:
--   * 拆出独立 parts 表(原 messages.parts JSON),加 session_id 冗余避免 JOIN
--   * sessions 加 token/cost 聚合字段,与 chat_turns 口径一致
--   * scenarios 加 parent_id 自引用,支持版本演化链
--   * 复合索引全部加 id 做 tie-breaker,支持稳定分页游标
--   * audit_logs 加 seq 事务序号,默认 NULL,需要时启用
-- ============================================================================

USE openagent;

-- ----------------------------------------------------------------------------
-- 0. 清理(可重复执行):按 FK 反序删除
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS parts;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS chat_turns;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS scenarios;


-- ----------------------------------------------------------------------------
-- 1. scenarios  场景定义(支持版本链)
-- ----------------------------------------------------------------------------
CREATE TABLE scenarios (
    id            CHAR(36)        NOT NULL                                COMMENT '主键 UUID',
    code          VARCHAR(128)    NOT NULL                                COMMENT '业务短码, 全局唯一',
    name          VARCHAR(255)    NOT NULL                                COMMENT '场景名',
    version       INT UNSIGNED    NOT NULL DEFAULT 1                      COMMENT '语义版本号, 同 code 自增',
    parent_id     CHAR(36)        NULL                                    COMMENT '上一版本场景 ID(版本演化链)',
    description   TEXT            NULL                                    COMMENT '场景描述',
    config        JSON            NOT NULL                                COMMENT 'ScenarioConfig Pydantic 序列化结果',
    source        VARCHAR(32)     NOT NULL DEFAULT 'db'                   COMMENT '来源: db / yaml / builtin',
    status        VARCHAR(32)     NOT NULL DEFAULT 'enabled'              COMMENT '状态: enabled / disabled / draft',
    is_deleted    TINYINT(1)      NOT NULL DEFAULT 0                      COMMENT '软删除标记',
    deleted_at    DATETIME(6)     NULL                                    COMMENT '软删除时间',
    created_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6)    COMMENT '创建时间',
    updated_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_scenarios_code_version (code, version),
    KEY idx_scenarios_status (status, is_deleted, updated_at, id),
    KEY idx_scenarios_parent (parent_id),
    KEY idx_scenarios_updated (updated_at),
    CONSTRAINT fk_scenarios_parent FOREIGN KEY (parent_id) REFERENCES scenarios(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='场景定义/快照(支持版本链)';


-- ----------------------------------------------------------------------------
-- 2. sessions  对话(原 Session dataclass, 加 token/cost 聚合)
-- ----------------------------------------------------------------------------
CREATE TABLE sessions (
    id                  CHAR(36)        NOT NULL                          COMMENT '主键 UUID',
    user_id             VARCHAR(64)     NOT NULL DEFAULT ''               COMMENT '所属用户标识(外部系统传入)',
    title               VARCHAR(255)    NOT NULL DEFAULT 'New Session'    COMMENT '会话标题',
    model               VARCHAR(128)    NULL                              COMMENT 'LLM 模型标识',
    agent_name          VARCHAR(128)    NOT NULL DEFAULT ''               COMMENT '使用的 Agent 名',
    scenario_id         CHAR(36)        NULL                              COMMENT '关联场景 ID',
    status              VARCHAR(32)     NOT NULL DEFAULT 'active'         COMMENT '状态: active / closed / archived',

    -- 聚合字段(从 chat_turns 反向汇总,与 opencode 风格一致)
    message_count       INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '消息条数缓存',
    cost                DECIMAL(12,6)   NOT NULL DEFAULT 0                COMMENT '累计花费 USD',
    tokens_input        INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 input tokens',
    tokens_output       INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 output tokens',
    tokens_reasoning    INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 reasoning tokens',
    tokens_cache_read   INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 cache read tokens',
    tokens_cache_write  INT UNSIGNED    NOT NULL DEFAULT 0                COMMENT '累计 cache write tokens',

    metadata            JSON            NULL                              COMMENT '扩展元数据',
    is_deleted          TINYINT(1)      NOT NULL DEFAULT 0                COMMENT '软删除标记',
    deleted_at          DATETIME(6)     NULL                              COMMENT '软删除时间',
    created_at          DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    updated_at          DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_sessions_user (user_id, is_deleted, updated_at, id),
    KEY idx_sessions_agent (agent_name, is_deleted, updated_at, id),
    KEY idx_sessions_scenario (scenario_id),
    KEY idx_sessions_updated (updated_at),
    CONSTRAINT fk_sessions_scenario FOREIGN KEY (scenario_id) REFERENCES scenarios(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='会话主表(含 token/cost 聚合)';


-- ----------------------------------------------------------------------------
-- 3. chat_turns  单轮执行单元(在 messages 之前建,因 messages.turn_id 引用)
-- ----------------------------------------------------------------------------
CREATE TABLE chat_turns (
    id                    CHAR(36)       NOT NULL                         COMMENT '主键 UUID',
    session_id            CHAR(36)       NOT NULL                         COMMENT '所属 session',
    user_message_id       CHAR(36)       NULL                             COMMENT '触发本 turn 的 user 消息(回填)',
    assistant_message_id  CHAR(36)       NULL                             COMMENT '本 turn 产出的 assistant 消息(回填)',
    agent_name            VARCHAR(128)   NULL                             COMMENT '执行 agent 名(快照)',
    model                 VARCHAR(128)   NULL                             COMMENT '调用模型(快照)',
    status                VARCHAR(32)    NOT NULL DEFAULT 'pending'       COMMENT 'pending / running / success / failed / cancelled',
    started_at            DATETIME(6)    NULL                             COMMENT '执行开始',
    finished_at           DATETIME(6)    NULL                             COMMENT '执行结束',
    duration_ms           INT UNSIGNED   NULL                             COMMENT '耗时(毫秒)',

    -- 本 turn 内的 token 用量(写到 turn,定期汇总到 session)
    cost                  DECIMAL(12,6)  NOT NULL DEFAULT 0               COMMENT '本 turn 花费 USD',
    tokens_input          INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn input tokens',
    tokens_output         INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn output tokens',
    tokens_reasoning      INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn reasoning tokens',
    tokens_cache_read     INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn cache read tokens',
    tokens_cache_write    INT UNSIGNED   NOT NULL DEFAULT 0               COMMENT '本 turn cache write tokens',

    error_code            VARCHAR(64)    NULL                             COMMENT '错误码',
    error_message         TEXT           NULL                             COMMENT '错误信息',
    metadata              JSON           NULL                             COMMENT '扩展元数据',
    is_deleted            TINYINT(1)     NOT NULL DEFAULT 0               COMMENT '软删除标记',
    deleted_at            DATETIME(6)    NULL                             COMMENT '软删除时间',
    created_at            DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间',
    updated_at            DATETIME(6)    NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_turns_session (session_id, is_deleted, created_at, id),
    KEY idx_turns_status (status, is_deleted, created_at, id),
    KEY idx_turns_started (started_at),
    CONSTRAINT fk_turns_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='单轮执行单元(含本 turn token 用量)';


-- ----------------------------------------------------------------------------
-- 4. messages  消息(原 Message dataclass, parts 已拆出)
--    必须在 parts 之前建: parts.message_id FK → messages.id
-- ----------------------------------------------------------------------------
CREATE TABLE messages (
    id            CHAR(36)        NOT NULL                                COMMENT '主键 UUID',
    session_id    CHAR(36)        NOT NULL                                COMMENT '所属 session',
    turn_id       CHAR(36)        NULL                                    COMMENT '所属 chat_turn(可空, 系统消息/老数据)',
    role          VARCHAR(32)     NOT NULL                                COMMENT 'user / assistant / system / tool',
    content       MEDIUMTEXT      NOT NULL                                COMMENT '消息文本主体',
    metadata      JSON            NULL                                    COMMENT '扩展元数据(工具名/trace_id 等)',
    is_deleted    TINYINT(1)      NOT NULL DEFAULT 0                      COMMENT '软删除标记',
    deleted_at    DATETIME(6)     NULL                                    COMMENT '软删除时间',
    created_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6)    COMMENT '创建时间',
    updated_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_messages_session (session_id, is_deleted, created_at, id),
    KEY idx_messages_turn (turn_id),
    KEY idx_messages_role (role, is_deleted),
    CONSTRAINT fk_messages_session FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
    CONSTRAINT fk_messages_turn    FOREIGN KEY (turn_id)    REFERENCES chat_turns(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='消息表(parts 已拆出)';


-- ----------------------------------------------------------------------------
-- 5. parts  消息分段(原 messages.parts JSON 拆出,加 session_id 冗余)
--    在 messages 之后建, FK → messages
-- ----------------------------------------------------------------------------
CREATE TABLE parts (
    id            CHAR(36)        NOT NULL                                COMMENT '主键 UUID',
    message_id    CHAR(36)        NOT NULL                                COMMENT '所属 message',
    session_id    CHAR(36)        NOT NULL                                COMMENT '冗余: 所属 session(避免 JOIN message)',
    part_type     VARCHAR(32)     NOT NULL                                COMMENT 'text / image / tool_call / tool_result / file / ...',
    content       MEDIUMTEXT      NULL                                    COMMENT '段内容(文本/序列化结果)',
    position      INT UNSIGNED    NOT NULL DEFAULT 0                      COMMENT '段在 message 内的顺序',
    metadata      JSON            NULL                                    COMMENT '扩展元数据(工具名/参数等)',
    is_deleted    TINYINT(1)      NOT NULL DEFAULT 0                      COMMENT '软删除标记',
    deleted_at    DATETIME(6)     NULL                                    COMMENT '软删除时间',
    created_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6)    COMMENT '创建时间',
    updated_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_parts_message (message_id, is_deleted, position, id),
    KEY idx_parts_session (session_id, is_deleted, created_at, id),
    KEY idx_parts_type (part_type, is_deleted, created_at, id),
    CONSTRAINT fk_parts_message FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='消息分段(原 messages.parts JSON 拆出)';


-- ----------------------------------------------------------------------------
-- 6. audit_logs  审计日志(append-only, 不软删; 加 seq 事务序号)
-- ----------------------------------------------------------------------------
CREATE TABLE audit_logs (
    id            CHAR(36)        NOT NULL                                COMMENT '主键 UUID',
    seq           BIGINT UNSIGNED NULL                                    COMMENT '同资源下的事务序号(可选, 默认 NULL)',
    actor_type    VARCHAR(32)     NOT NULL                                COMMENT 'user / system / admin / anonymous',
    actor_id      VARCHAR(128)    NULL                                    COMMENT '操作者 ID',
    action        VARCHAR(64)     NOT NULL                                COMMENT 'create / update / delete / login / state_change ...',
    resource_type VARCHAR(64)     NOT NULL                                COMMENT 'session / message / scenario / turn / config ...',
    resource_id   CHAR(36)        NULL                                    COMMENT '资源 ID(软引用, 不建 FK)',
    before_data   JSON            NULL                                    COMMENT '变更前快照',
    after_data    JSON            NULL                                    COMMENT '变更后快照',
    ip            VARCHAR(64)     NULL                                    COMMENT '客户端 IP',
    user_agent    VARCHAR(512)    NULL                                    COMMENT 'UA',
    request_id    VARCHAR(64)     NULL                                    COMMENT '链路 trace ID',
    metadata      JSON            NULL                                    COMMENT '扩展',
    created_at    DATETIME(6)     NOT NULL DEFAULT CURRENT_TIMESTAMP(6)    COMMENT '写入时间',
    PRIMARY KEY (id),
    KEY idx_audit_resource_seq (resource_type, resource_id, seq, created_at),
    KEY idx_audit_actor (actor_type, actor_id, created_at, id),
    KEY idx_audit_action (action, created_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='审计日志(append-only)';
