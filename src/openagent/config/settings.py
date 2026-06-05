"""Settings - 配置管理

使用 pydantic-settings 进行环境变量管理。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from openagent.config.env_sources import (
    PathAwareDotEnvSource,
    PathAwareEnvSource,
)


class Settings(BaseSettings):
    """应用配置

    可通过环境变量或 .env 文件配置。

    环境变量前缀: AGENT_SCHEDULER_
    """

    model_config = SettingsConfigDict(
        env_prefix="AGENT_SCHEDULER_",
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

    # OpenCode 连接配置
    opencode_base_url: str = Field(
        default="http://localhost:4096",
        description="OpenCode serve 地址",
    )
    opencode_username: Optional[str] = Field(
        default=None,
        description="OpenCode Basic Auth 用户名",
    )
    opencode_password: Optional[str] = Field(
        default=None,
        description="OpenCode Basic Auth 密码",
    )

    # 服务器配置
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8000, description="服务监听端口")
    workers: int = Field(default=1, description="工作进程数")
    debug: bool = Field(default=False, description="Sanic 调试模式（开启后 500 响应会暴露真实错误）")

    # 调度配置
    default_timeout: float = Field(
        default=120.0,
        description="默认任务超时时间（秒）",
    )
    health_check_interval: float = Field(
        default=30.0,
        description="健康检查间隔（秒）",
    )
    max_retries: int = Field(
        default=3,
        description="最大重试次数",
    )

    # 日志配置
    log_level: str = Field(
        default="INFO",
        description="日志级别",
    )
    log_format: str = Field(
        default="json",
        description="日志格式: json 或 text",
    )
    log_llm_payload: bool = Field(
        default=True,
        description=(
            "是否把每次发往下层 LLM SDK 的完整请求体 (session/model/parts/system/tools) "
            "以 llm_request 事件写入日志。关闭时 hot path 不会构造任何字符串。"
        ),
    )

    # CORS 配置
    cors_origins: list[str] = Field(
        default=["*"],
        description="允许的 CORS 源",
    )

    # 存储配置
    storage_backend: str = Field(
        default="postgres",
        description="存储后端: postgres",
    )
    postgres_dsn: str = Field(
        default="postgresql://localhost:5432/openagent",
        description="PostgreSQL DSN 连接字符串",
    )
    postgres_pool_min_size: int = Field(
        default=5,
        description="PostgreSQL 连接池最小尺寸",
    )
    postgres_pool_max_size: int = Field(
        default=20,
        description="PostgreSQL 连接池最大尺寸",
    )

    # Skill 配置
    skill_paths: list[str] = Field(
        default=[],
        description="Skill 路径列表",
    )

    # MCP Tools 配置
    mcp_tools_config: list[dict] = Field(
        default=[],
        description=(
            "MCP Tools 配置列表; 值可以是 inline JSON (例如 [{\"name\":...}]) "
            "或指向 JSON 文件的路径 (例如 /app/work/mcp/mcp.json)"
        ),
    )

    # Agent 默认注册（启动时自动注册一组默认 Agent，省去手动调 /agent/pool/register）
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

    # Scenario 路由 (P6)
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


@lru_cache
def get_settings() -> Settings:
    """获取缓存的 Settings 实例"""
    return Settings()
