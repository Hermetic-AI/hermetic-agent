"""Settings - 全局配置中心 (Hub 侧 Python).

唯一改这里 = 改所有 Hub 行为. 各模块 (api / providers / sandbox / policy
/ skill_runtime / core) 一律从 ``get_settings()`` 读, **不要** 在模块顶层
或函数默认值里再写硬编码常量.

.. code-block:: python

    from hermetic_agent.config.settings import get_settings
    settings = get_settings()
    timeout = settings.opencode_client_timeout_read

环境变量:
    - 前缀: 无 (pydantic-settings 配的)
    - 文件: CWD 下的 ``.env`` (pydantic-settings 自动 load)
    - 复杂字段 (list[dict]): 既支持 inline JSON, 也支持指向 JSON 文件路径,
      见 ``env_sources.PathAwareEnvSource``.

业务配置（如租户 auth base_url、API key 等）通过 SKILL 层的 skill.yaml
``required_envs`` + scenario YAML 的 ``env`` 字段声明, 不进入基座
Settings. 详见 ``docs/core-skill-boundary.md`` §4.5.

按职责分 7 个 section (按文件内顺序):

1.  Server         — host/port/workers/debug/CORS/Sanic 超时
2.  OpenCode       — opencode_serve URL + admin port + reload settle
3.  Logging        — log level/format/llm_payload
4.  Storage        — backend (memory/postgres) + DSN + pool
5.  Skill Runtime  — skill_paths / budget / policy
6.  MCP            — mcp_tools_config (inline or file path)
7.  Agent          — auto_register + default_agents_json
8.  Sandbox        — docker bin / network / 资源 limit / port / health
9.  Policy         — _ALLOWED_LOCAL_PORTS / BLOCKED_PATTERNS / 网络/路径策略
10. Scenario       — scenario_paths / default_scenario / work_root / PROJECT_DIR
11. Launcher       — config_dir / FORBIDDEN_CWDS / opencode serve cmd / port
12. Chat / SSE     — keepalive interval / client timeouts
13. App Metadata   — OpenAPI 文档 (title/version/contact/license)
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from hermetic_agent.config.env_sources import (
    PathAwareDotEnvSource,
    PathAwareEnvSource,
)


class Settings(BaseSettings):
    """应用配置.

    可通过环境变量或 .env 文件配置.
    环境变量: 无前缀, 直接读 .env 或进程 env.
    """

    model_config = SettingsConfigDict(
        env_prefix="",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Plug in env sources that resolve file-path values for complex fields."""
        return (
            init_settings,
            PathAwareEnvSource(settings_cls),
            PathAwareDotEnvSource(settings_cls),
            file_secret_settings,
        )

    # =========================================================================
    # 1. Server — 监听 / 进程 / CORS / Sanic 超时
    # =========================================================================

    # OpenCode 连接配置
    opencode_base_url: str = Field(
        default="http://localhost:4096",
        description="OpenCode serve 地址. Docker 部署时 = http://opencode-1:14096",
    )
    opencode_username: str | None = Field(
        default=None,
        description="OpenCode Basic Auth 用户名 (目前没启)",
    )
    opencode_password: str | None = Field(
        default=None,
        description="OpenCode Basic Auth 密码 (目前没启)",
    )

    # Hub 进程配置
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8000, description="服务监听端口")
    workers: int = Field(default=1, description="Sanic 工作进程数")
    debug: bool = Field(
        default=False,
        description="Sanic 调试模式（开启后 500 响应会暴露真实错误）",
    )

    # CORS
    cors_origins: list[str] = Field(
        default=["*"],
        description="允许的 CORS 源",
    )

    # Sanic 超时 (P8: 长 LLM 调用必须撑住, 默认 10s/5s 必断)
    # 都是**上限**而非**真实等待**; 业务流自然结束会立即释放.
    sanic_request_timeout: int = Field(
        default=600,
        description="Sanic 接受完整请求体上限 (秒). 10min, 容纳长 LLM 调用 + 多步工具",
    )
    sanic_request_max_size: int = Field(
        default=50_000_000,
        description="Sanic 单请求体最大字节数 (默认 50MB, 容纳大 system_prompt)",
    )
    sanic_keep_alive_timeout: int = Field(
        default=120,
        description="Sanic HTTP/1.1 keep-alive 探活超时 (秒)",
    )
    sanic_websocket_ping_timeout: int = Field(
        default=60,
        description="Sanic WebSocket ping 间隔 (秒, 后用)",
    )
    sanic_websocket_pong_timeout: int = Field(
        default=60,
        description="Sanic WebSocket pong 超时 (秒)",
    )

    # 调度配置
    default_timeout: float = Field(
        default=120.0,
        description="默认任务超时时间（秒）",
    )
    health_check_interval: float = Field(
        default=30.0,
        description="健康检查间隔（秒, 跟 agent_pool 同步）",
    )
    max_retries: int = Field(
        default=3,
        description="最大重试次数 (agent_pool 连续失败 N 次后 mark_offline)",
    )

    # =========================================================================
    # 2. OpenCode — opencode_serve 客户端 (HTTP / admin / reload)
    # =========================================================================

    opencode_admin_port: int = Field(
        default=7778,
        description=(
            "OpenCode 容器内 admin server 端口 (跟 docker/opencode/scripts/admin_server.py "
            "/ docker-compose.yml 一致). Hub 通过 :7778 写 env.runtime + 触发 reload."
        ),
    )
    opencode_reload_settle_seconds: float = Field(
        default=1.0,
        description=(
            "Hub 触发 opencode reload 后, 等待 supervisor 拉起新进程的最短秒数. "
            "再调 /global/health 探活. 0 = 不等."
        ),
    )
    opencode_wait_health_timeout: float = Field(
        default=8.0,
        description="opencode serve 启动后 /global/health 探活总超时 (秒)",
    )
    opencode_wait_health_interval: float = Field(
        default=0.25,
        description="opencode serve /global/health 探活间隔 (秒)",
    )

    # =========================================================================
    # 3. Logging
    # =========================================================================

    log_level: str = Field(
        default="INFO",
        description="日志级别: DEBUG/INFO/WARNING/ERROR/CRITICAL",
    )
    log_format: str = Field(
        default="json",
        description="日志格式: json (生产) / console (本地开发, Rich 配色)",
    )
    log_llm_payload: bool = Field(
        default=True,
        description=(
            "是否把每次发往下层 LLM SDK 的完整请求体 (session/model/parts/system/tools) "
            "以 llm_request 事件写入日志. 关闭时 hot path 不会构造任何字符串."
        ),
    )

    # ---- 3a. 外部日志采集平台 (仿照 fh-ai app/commons/log) ----
    # DTO 字段 + 接入指南见 ``docs/design/外部日志采集平台接入指南.md``.
    # 默认全关 (use_redis_log=false), 生产打开走 Redis 列表通道.
    log_use_redis_log: bool = Field(
        default=False,
        description=(
            "是否启用 Redis 列表通道 (模式 A, 推荐). 关闭时走 Python 文件 "
            "(模式 B, Filebeat/Logkit 采集). 详见接入指南 §5."
        ),
    )
    log_queue_name: str = Field(
        default="hermetic_agent",
        description=(
            "Redis List 名 (不含 log: 前缀), 平台订阅 ``log:{queueName}``."
        ),
    )
    log_max_queue_size: int = Field(
        default=100_000,
        description="Redis List 满后丢弃本批 (沿用 fh-ai 行为, 不阻塞主流程).",
    )
    log_file_path: str | None = Field(
        default=None,
        description=(
            "use_redis_log=false 时的文件路径. 留空 = 关闭 (facade 仍写内存队列, "
            "但不落盘). 建议配 /var/log/hermetic_agent/platform.log (容器 ro 模式下 "
            "需要 bind mount / 改 read_only=false)."
        ),
    )
    log_tee_to_stdout: bool = Field(
        default=False,
        description=(
            "把平台日志 (BusiLog/RequestLog) 也打到 stdout (跟 structlog 输出并存), "
            "加 ``[platform-log]`` 前缀方便 grep. 默认关 — 生产打开会双发日志, "
            "只在本地 dev / 调试时开. 跟 ``log_use_redis_log`` / ``log_file_path`` 独立."
        ),
    )
    log_system_type: str = Field(
        default="hermetic_agent",
        description=(
            "拼接 ``type`` 字段后缀, 例 hermetic_agent → ``BUSI_LOG_hermetic_agent``. "
            "生产可改 ``hermetic_agent_prod`` 跟测试分流."
        ),
    )
    log_redis_poll_interval: float = Field(
        default=0.5,
        description="RedisWriteTask 轮询间隔 (秒). 跟 fh-ai 一致 0.5s.",
    )
    log_redis_host: str = Field(
        default="127.0.0.1",
        description="外部日志采集平台 Redis host.",
    )
    log_redis_port: int = Field(
        default=6379,
        description="外部日志采集平台 Redis port.",
    )
    log_redis_password: str | None = Field(
        default=None,
        description="外部日志采集平台 Redis 密码 (None=无密码).",
    )
    log_redis_database: int = Field(
        default=15,
        description="外部日志采集平台 Redis DB index (0-15).",
    )
    log_redis_timeout: float = Field(
        default=5.0,
        description="外部日志采集平台 Redis socket 超时 (秒).",
    )

    # =========================================================================
    # 4. Storage
    # =========================================================================

    storage_backend: str = Field(
        default="mysql",
        description="存储后端: mysql / postgres / memory",
    )
    # ---- MySQL (Phase 2 主存储) ----
    mysql_dsn: str = Field(
        default="mysql://root:1014@127.0.0.1:13306/hermetic_agent",
        description=(
            "MySQL DSN 连接字符串. 格式: mysql://user:pass@host:port/db "
            "(asyncmy 协议). 多套环境切换时改这里即可."
        ),
    )
    mysql_pool_min_size: int = Field(
        default=5,
        description="MySQL 连接池最小尺寸",
    )
    mysql_pool_max_size: int = Field(
        default=20,
        description="MySQL 连接池最大尺寸",
    )
    mysql_echo: bool = Field(
        default=False,
        description="是否打印 MySQL 执行 SQL(调试用, 生产关)",
    )
    # ---- Postgres (兼容老配置, 暂时不接, 留作未来扩展) ----
    postgres_dsn: str = Field(
        default="postgresql://localhost:5432/hermetic_agent",
        description="PostgreSQL DSN 连接字符串 (兼容字段, 当前未使用)",
    )
    postgres_pool_min_size: int = Field(
        default=5,
        description="PostgreSQL 连接池最小尺寸 (兼容字段)",
    )
    postgres_pool_max_size: int = Field(
        default=20,
        description="PostgreSQL 连接池最大尺寸 (兼容字段)",
    )

    # =========================================================================
    # 5. Skill Runtime
    # =========================================================================

    skill_paths: list[str] = Field(
        default=[],
        description="Skill 路径列表 (显式加载, 优先于 fallback 候选目录)",
    )
    skill_path_fallbacks: list[str] = Field(
        default_factory=lambda: [
            "src/hermetic_agent/.skills",
            "work/shared/skills",
            "/app/src/hermetic_agent/.skills",
            "/app/work/shared/skills",
        ],
        description=(
            "Skill 路径 fallback 候选目录 (相对 CWD 或绝对路径). "
            "显式 skill_paths 没配时, 依次探测这些目录里存在的; 跟 docker "
            "mount 路径对齐 (开发态 / 容器态)."
        ),
    )
    fragment_budget_tokens: int = Field(
        default=4000,
        description="FragmentLoader 预算 (token), 控制单次 chat 加载 skill 片段总 token 数",
    )
    fragment_budget_policy: str = Field(
        default="error",
        description="FragmentLoader 超预算策略: error / warn / truncate",
    )

    # =========================================================================
    # 6. MCP
    # =========================================================================

    mcp_tools_config: list[dict] = Field(
        default=[],
        description=(
            "MCP Tools 配置列表; 值可以是 inline JSON (例如 [{\"name\":...}]) "
            "或指向 JSON 文件的路径 (例如 /app/work/mcp/mcp.json). "
            "解析规则见 env_sources.PathAwareEnvSource."
        ),
    )

    # =========================================================================
    # 7. Agent
    # =========================================================================

    auto_register_default_agents: bool = Field(
        default=True,
        description="启动时自动注册一组默认 Agent（默认指向 opencode_base_url）",
    )
    default_agents_json: list[dict] = Field(
        default=[],
        description=(
            "可选：覆盖默认 Agent 列表。每项含 name/base_url/sdk_type(default='opencode')/"
            "default_model。留空则只注册一个 opencode-core 指向 opencode_base_url。"
            "值可以是 inline JSON 或 JSON 文件路径。"
        ),
    )

    # =========================================================================
    # 8. Sandbox — docker / 资源 / 端口 / 健康
    # =========================================================================

    docker_bin: str = Field(
        default="docker",
        description="docker CLI 路径 (PATH 不在 /usr/bin/docker 时覆盖)",
    )
    sandbox_network: str = Field(
        default="hermetic_agent-sandbox-net",
        description="sandbox 跟 hub 共享的 docker bridge network 名 (跟 docker-compose 对齐)",
    )
    sandbox_mem_limit: str = Field(
        default="2g",
        description="sandbox 容器内存上限 (docker run --memory)",
    )
    sandbox_cpu_limit: float = Field(
        default=2.0,
        description="sandbox 容器 CPU 配额 (docker run --cpus)",
    )
    sandbox_pids_limit: int = Field(
        default=128,
        description="sandbox 容器进程数上限 (docker run --pids-limit)",
    )
    sandbox_health_port: int = Field(
        default=7777,
        description="sandbox 容器内 health_server 端口 (跟 docker/opencode/scripts/health_server.py 一致)",
    )
    sandbox_opencode_port: int = Field(
        default=14096,
        description="sandbox 容器内 opencode serve 端口 (跟 docker/opencode/scripts/entrypoint.sh 一致)",
    )
    sandbox_health_check_timeout: float = Field(
        default=2.0,
        description="单次 /healthz HTTP 探活超时 (秒)",
    )
    sandbox_health_check_retries: int = Field(
        default=3,
        description="连续失败 N 次后节点标 unhealthy (跟 docker/opencode/scripts/health_server.py 对齐)",
    )

    # =========================================================================
    # 9. Policy — L5 安全策略 (网络白名单端口 / 路径黑名单)
    # =========================================================================

    network_allowed_local_ports: list[int] = Field(
        default_factory=lambda: [80, 443, 53, 8080, 8443, 3000, 5000, 5432, 6379],
        description=(
            "network=local 模式下也允许的出网端口 (DNS / local services 等常用端口). "
            "跟 sandbox 内 network_check._ALLOWED_LOCAL_PORTS 对齐."
        ),
    )
    path_blocked_patterns: list[str] = Field(
        default_factory=lambda: [
            "**/.env",
            "**/.env.*",
            "**/id_rsa",
            "**/id_ed25519",
            "**/id_*",
            "**/.ssh/**",
            "**/.aws/credentials",
            "**/.config/gcloud/**",
            "**/*.pem",
            "**/*.key",
            "**/*.p12",
            "**/secrets/**",
            "**/credentials/**",
        ],
        description=(
            "永远不允许的路径 glob 模式 (凭据类文件). "
            "跟 path_check.BLOCKED_PATTERNS 对齐."
        ),
    )

    # =========================================================================
    # 10. Scenario
    # =========================================================================

    scenario_paths: list[str] = Field(
        default_factory=lambda: ["work/scenarios"],
        description="Scenario YAML 加载目录列表 (相对 work_root 或绝对路径)",
    )
    default_scenario: str = Field(
        default="_default",
        description="路由 6 优先级都失败时兜底的 scenario 名",
    )
    work_root: str = Field(
        default="work",
        description="工作区根目录 (所有 ${WORK_ROOT}/${WORK_SHARED} 占位符的解析基准)",
    )
    project_dir_fallback: str = Field(
        default="tenants/tenant-A/projects/project-1",
        description=(
            "${PROJECT_DIR} 占位符兜底值. 当 scenario 没在 resource_dirs 里显式 "
            "给 project_dir 时用. Hub 实际场景用不到 (YAML 都会显式给), 仅 dev "
            "示例场景用. 相对路径以 work_root 为基准, 绝对路径直接用."
        ),
    )

    # =========================================================================
    # 11. Launcher — engine 启动 / cwd 校验
    # =========================================================================

    launcher_config_dir: str = Field(
        default="work/cache/opencode-configs",
        description="opencode serve 临时 config.json 写入目录 (按 agent 名分文件)",
    )
    launcher_forbidden_cwds: list[str] = Field(
        default_factory=lambda: ["/", "~", "${HOME}", "$HOME", "/root", "/home", ""],
        description=(
            "EngineLauncher 拒绝的 cwd. cwd 是这些或占位符没解析时会抛 "
            "LauncherRefusedRoot. 跟 scenarios/config._FORBIDDEN_WS 对齐."
        ),
    )
    launcher_default_tool_level: str = Field(
        default="standard",
        description="scenario_security 没传 tool_level 时, opencode config 渲染的默认值",
    )
    launcher_default_network: str = Field(
        default="local",
        description="scenario_security 没传 network 时, opencode config 渲染的默认值",
    )
    launcher_opencode_hostname: str = Field(
        default="127.0.0.1",
        description="opencode serve --hostname 参数 (loopback, 避免对外暴露)",
    )
    launcher_stop_grace_seconds: float = Field(
        default=5.0,
        description="EngineLauncher.stop 等 SIGTERM 生效秒数, 超时强杀",
    )

    # =========================================================================
    # 12. Chat / SSE — 流式响应 + MCP token
    # =========================================================================

    sse_keepalive_interval: float = Field(
        default=15.0,
        description=(
            "SSE 心跳间隔 (秒). 业务事件空闲超这个时长, 注入 ``: keepalive`` "
            "注释行, 防止 Vite proxy / Nginx / 浏览器在 30-60s 后关连接."
        ),
    )
    opencode_client_timeout_connect: float = Field(
        default=10.0,
        description="opencode SDK 底层 httpx client connect 超时 (秒)",
    )
    opencode_client_timeout_read: float = Field(
        default=300.0,
        description="opencode SDK 底层 httpx client read 超时 (秒). 容纳长 LLM 调用",
    )
    opencode_client_timeout_write: float = Field(
        default=10.0,
        description="opencode SDK 底层 httpx client write 超时 (秒)",
    )
    opencode_client_timeout_pool: float = Field(
        default=5.0,
        description="opencode SDK 底层 httpx client pool 超时 (秒)",
    )
    opencode_client_max_connections: int = Field(
        default=100,
        description="opencode SDK 底层 httpx client 最大连接数",
    )
    opencode_client_max_keepalive: int = Field(
        default=100,
        description="opencode SDK 底层 httpx client keepalive 连接数",
    )
    opencode_client_keepalive_expiry: float = Field(
        default=120.0,
        description="opencode SDK 底层 httpx client keepalive 过期时间 (秒)",
    )
    agent_pool_health_check_http_timeout: float = Field(
        default=5.0,
        description="AgentPoolService 单实例 /health 探活 HTTP 超时 (秒)",
    )

    # =========================================================================
    # 13. App Metadata — OpenAPI 文档
    # =========================================================================

    app_title: str = Field(
        default="hermetic-agent",
        description="OpenAPI 文档 title",
    )
    app_version: str = Field(
        default="0.1.0",
        description="OpenAPI 文档 version (跟 pyproject.toml 同步)",
    )
    app_description: str = Field(
        default=(
            "hermetic-agent — General-purpose Agent scheduling framework "
            "built on opencode SDK.\n\n支持会话管理、SSE 流式聊天、Skill 注册、"
            "MCP 工具管理、Agent Pool 注册。"
        ),
        description="OpenAPI 文档 description",
    )
    app_contact_email: str = Field(
        default="dev@hermetic-agent.local",
        description="OpenAPI 文档 contact email",
    )
    app_license_name: str = Field(
        default="Apache-2.0",
        description="OpenAPI 文档 license name",
    )

    # =========================================================================
    # 15. Nacos — 配置中心 + AI 注册表 (MCP/Agent/Skill/Prompt)
    # =========================================================================

    nacos_enabled: bool = Field(
        default=False,
        description="是否启用 Nacos 集成. 关闭后所有 Nacos 功能跳过.",
    )
    nacos_server_addr: str = Field(
        default="127.0.0.1:8848",
        description=(
            "Nacos Server 地址 (host:port). Docker 部署时 = nacos:8848. "
            "集群模式用逗号分隔: nacos-1:8848,nacos-2:8848."
        ),
    )
    nacos_namespace: str = Field(
        default="",
        description=(
            "Nacos 命名空间 ID (留空 = public). 用于环境隔离 "
            "(dev/test/prod) 或多租户隔离."
        ),
    )
    nacos_group: str = Field(
        default="DEFAULT_GROUP",
        description="Nacos 配置分组. 通常按应用名或环境分.",
    )
    nacos_username: str = Field(
        default="nacos",
        description="Nacos 认证用户名.",
    )
    nacos_password: str = Field(
        default="nacos",
        description="Nacos 认证密码.",
    )
    nacos_config_data_id: str = Field(
        default="hermetic_agent",
        description="Nacos 配置中心的 Data ID (主配置文件).",
    )
    nacos_config_group: str = Field(
        default="DEFAULT_GROUP",
        description="Nacos 配置中心的 Group.",
    )
    nacos_config_format: str = Field(
        default="yaml",
        description="Nacos 配置格式: yaml / json / properties.",
    )
    nacos_ai_enabled: bool = Field(
        default=True,
        description="是否启用 Nacos AI 注册表功能 (MCP/Agent/Skill/Prompt 同步).",
    )
    nacos_ai_mcp_sync: bool = Field(
        default=True,
        description="是否将本地 MCPRegistry 同步到 Nacos MCP Server 注册表.",
    )
    nacos_ai_agent_sync: bool = Field(
        default=True,
        description="是否将本地 AgentPool 同步到 Nacos Agent Card 注册表.",
    )
    nacos_ai_skill_sync: bool = Field(
        default=True,
        description="是否将本地 SkillRegistry 同步到 Nacos Skill 注册表.",
    )
    nacos_ai_prompt_sync: bool = Field(
        default=True,
        description="是否从 Nacos Prompt 注册表拉取 prompt 模板.",
    )
    nacos_service_name: str = Field(
        default="hermetic-agent",
        description="Hub 在 Nacos 服务注册表中的服务名.",
    )
    nacos_service_ip: str = Field(
        default="",
        description="Hub 注册到 Nacos 的 IP (留空 = 自动探测).",
    )
    nacos_service_port: int = Field(
        default=8000,
        description="Hub 注册到 Nacos 的端口 (跟 Hub port 一致).",
    )


@lru_cache
def get_settings() -> Settings:
    """获取缓存的 Settings 实例"""
    return Settings()
