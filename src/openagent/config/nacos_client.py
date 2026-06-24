"""Nacos Client Wrapper - 配置中心 + 服务注册 + AI 注册表客户端.

封装 nacos-sdk-python v3 的连接、配置拉取/发布、服务注册/注销、
AI 注册表 (MCP/Agent/Prompt) 操作.

底层使用 nacos-sdk-python v3 (import v2.nacos).
"""

from __future__ import annotations

import socket
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _detect_local_ip() -> str:
    """探测本机局域网 IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip: str = str(s.getsockname()[0])
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class NacosClient:
    """Nacos v3 SDK 客户端封装."""

    def __init__(self, settings: Any) -> None:
        """初始化 Nacos 客户端."""
        self._settings = settings
        self._enabled: bool = getattr(settings, "nacos_enabled", False)
        self._server_addr: str = getattr(settings, "nacos_server_addr", "127.0.0.1:8848")
        self._namespace: str = getattr(settings, "nacos_namespace", "")
        self._group: str = getattr(settings, "nacos_group", "DEFAULT_GROUP")
        self._username: str = getattr(settings, "nacos_username", "")
        self._password: str = getattr(settings, "nacos_password", "")
        self._naming_service: Any = None
        self._config_service: Any = None
        self._ai_service: Any = None
        self._client_config: Any = None
        logger.info(
            "nacos_client_init",
            enabled=self._enabled,
            server_addr=self._server_addr,
            namespace=self._namespace,
        )

    @property
    def enabled(self) -> bool:
        """是否启用."""
        return self._enabled

    @property
    def connected(self) -> bool:
        """是否已连接."""
        return self._naming_service is not None

    @property
    def ai_service(self) -> Any:
        """获取 AI 服务实例."""
        return self._ai_service

    @property
    def config_service(self) -> Any:
        """获取 Config 服务实例."""
        return self._config_service

    @property
    def naming_service(self) -> Any:
        """获取 Naming 服务实例."""
        return self._naming_service

    async def start(self) -> bool:
        """启动 Nacos 客户端, 建立 Naming + Config + AI 服务连接."""
        if not self._enabled:
            logger.info("nacos_start_skipped", reason="disabled")
            return False

        try:
            from v2.nacos import (
                ClientConfigBuilder,
                NacosConfigService,
                NacosNamingService,
            )
            from v2.nacos.ai.nacos_ai_service import NacosAIService

            builder = ClientConfigBuilder()
            builder.server_address(self._server_addr)
            if self._namespace:
                builder.namespace_id(self._namespace)
            if self._username and self._password:
                builder.username(self._username)
                builder.password(self._password)
            builder.log_level("WARN")
            self._client_config = builder.build()

            self._naming_service = await NacosNamingService.create_naming_service(
                self._client_config
            )
            self._config_service = await NacosConfigService.create_config_service(
                self._client_config
            )
            self._ai_service = await NacosAIService.create_ai_service(
                self._client_config
            )
            logger.info(
                "nacos_connected",
                server_addr=self._server_addr,
                namespace=self._namespace,
            )
            return True
        except ImportError:
            logger.warning("nacos_sdk_not_installed", hint="pip install nacos-sdk-python")
            self._enabled = False
            return False
        except Exception as e:
            logger.error("nacos_connect_failed", error=str(e))
            return False

    async def stop(self) -> None:
        """关闭 Nacos 客户端, 释放资源."""
        try:
            if self._ai_service is not None:
                await self._ai_service.shutdown()
                self._ai_service = None
            if self._naming_service is not None:
                await self._naming_service.shutdown()
                self._naming_service = None
            if self._config_service is not None:
                await self._config_service.shutdown()
                self._config_service = None
            logger.info("nacos_disconnected")
        except Exception as e:
            logger.error("nacos_disconnect_error", error=str(e))

    async def get_config(
        self,
        data_id: str | None = None,
        group: str | None = None,
    ) -> str | None:
        """从 Nacos 配置中心拉取配置."""
        if not self._config_service:
            return None

        try:
            from v2.nacos.config.model.config_param import ConfigParam

            param = ConfigParam(
                data_id=data_id or getattr(
                    self._settings, "nacos_config_data_id", "openagent"
                ),
                group=group or getattr(
                    self._settings, "nacos_config_group", "DEFAULT_GROUP"
                ),
            )
            content = await self._config_service.get_config(param)
            logger.debug("nacos_config_fetched", data_id=param.data_id, group=param.group)
            return str(content) if content else None
        except Exception as e:
            logger.error("nacos_config_fetch_failed", error=str(e))
            return None

    async def publish_config(
        self,
        data_id: str,
        content: str,
        group: str | None = None,
        config_format: str = "yaml",
    ) -> bool:
        """发布配置到 Nacos 配置中心."""
        if not self._config_service:
            return False

        try:
            from v2.nacos.config.model.config_param import ConfigParam

            param = ConfigParam(
                data_id=data_id,
                group=group or self._group,
                content=content,
                type=config_format,
            )
            result = await self._config_service.publish_config(param)
            logger.info("nacos_config_published", data_id=data_id, group=param.group)
            return bool(result)
        except Exception as e:
            logger.error("nacos_config_publish_failed", data_id=data_id, error=str(e))
            return False

    async def register_service(
        self,
        service_name: str | None = None,
        ip: str | None = None,
        port: int | None = None,
    ) -> bool:
        """将 Hub 注册到 Nacos 服务注册表."""
        if not self._naming_service:
            return False

        try:
            from v2.nacos.naming.model.naming_param import RegisterInstanceParam

            service_name = service_name or getattr(
                self._settings, "nacos_service_name", "openagent-hub"
            )
            ip = ip or getattr(self._settings, "nacos_service_ip", "") or _detect_local_ip()
            port = port or getattr(self._settings, "nacos_service_port", 8000)

            param = RegisterInstanceParam(
                service_name=service_name,
                ip=ip,
                port=port,
                group_name=self._group,
                ephemeral=True,
            )
            await self._naming_service.register_instance(param)
            logger.info(
                "nacos_service_registered",
                service_name=service_name, ip=ip, port=port,
            )
            return True
        except Exception as e:
            logger.error("nacos_service_register_failed", error=str(e))
            return False

    async def deregister_service(
        self,
        service_name: str | None = None,
        ip: str | None = None,
        port: int | None = None,
    ) -> bool:
        """从 Nacos 服务注册表注销 Hub."""
        if not self._naming_service:
            return False

        try:
            from v2.nacos.naming.model.naming_param import DeregisterInstanceParam

            service_name = service_name or getattr(
                self._settings, "nacos_service_name", "openagent-hub"
            )
            ip = ip or getattr(self._settings, "nacos_service_ip", "") or _detect_local_ip()
            port = port or getattr(self._settings, "nacos_service_port", 8000)

            param = DeregisterInstanceParam(
                service_name=service_name,
                ip=ip,
                port=port,
                group_name=self._group,
            )
            await self._naming_service.deregister_instance(param)
            logger.info("nacos_service_deregistered", service_name=service_name)
            return True
        except Exception as e:
            logger.error("nacos_service_deregister_failed", error=str(e))
            return False
