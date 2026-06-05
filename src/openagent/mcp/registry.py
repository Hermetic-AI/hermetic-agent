"""MCP 工具注册中心。

统一管理本地工具处理器与远程 MCP 端点，并提供 OpenCode / Claude Code
两种格式的转换能力。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx
import structlog

logger = structlog.get_logger(__name__)


class ToolHandler(Protocol):
    """工具处理器协议；任意可调用对象都可作为 handler 使用。"""

    async def __call__(self, **kwargs: Any) -> Any:
        ...


@dataclass
class MCPTool:
    """表示一个 MCP 工具的配置与执行入口。

    可以是本地 handler，也可以是远程 URL 调用；通过 ``enabled`` 控制
    是否对外暴露。
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None
    remote_url: str | None = None
    remote_tool_name: str | None = None
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典形式，便于在响应或日志中输出。

        Returns:
            包含工具元数据的字典（不含 handler 可调用对象）。
        """
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "remote_url": self.remote_url,
            "remote_tool_name": self.remote_tool_name,
            "enabled": self.enabled,
        }


class MCPRegistry:
    """MCP 工具注册中心，集中管理工具的注册、调用与格式转换。"""

    def __init__(self) -> None:
        self._tools: dict[str, MCPTool] = {}
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """懒加载并返回用于远程工具调用的共享 HTTP 客户端。"""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        """关闭共享的 HTTP 客户端；进程退出前调用以释放连接。"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def register(
        self,
        name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
        handler: ToolHandler | None = None,
        remote_url: str | None = None,
        remote_tool_name: str | None = None,
        enabled: bool = True,
    ) -> MCPTool:
        """注册一个新工具到注册中心。

        Args:
            name: 工具唯一名称。
            description: 人类可读的描述，会注入到模型提示中。
            input_schema: 工具入参的 JSON Schema。
            handler: 本地异步处理函数。
            remote_url: 远程 MCP 端点 URL。
            remote_tool_name: 远程端点上的实际工具名。
            enabled: 是否启用；禁用后 ``call_tool`` 会拒绝执行。

        Returns:
            已注册完成的 ``MCPTool`` 实例。
        """
        logger.info(
            "register_tool_start",
            name=name,
            has_handler=handler is not None,
            is_remote=remote_url is not None,
        )
        tool = MCPTool(
            name=name,
            description=description,
            input_schema=input_schema or {},
            handler=handler,
            remote_url=remote_url,
            remote_tool_name=remote_tool_name,
            enabled=enabled,
        )
        self._tools[name] = tool
        logger.debug("tool_registered", name=name, has_handler=handler is not None, is_remote=remote_url is not None)
        return tool

    def register_synthetic_tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
    ) -> MCPTool:
        """注册一个"合成"工具 — 仅出现在 LLM 的工具列表中, 实际执行由框架拦截.

        用途: LLM 调 ``ask_user`` 推 UI 卡片时, OpenCode 不会真正执行它,
        框架在 chat_controller 的 streaming_fn 里看到 ``tool_use(name=ask_user)``
        就把它转成 ``card`` SSE 事件并抑制对应的 ``tool_result``.

        这里的 handler 是 no-op (返回 success 占位), 保证 ``to_opencode_format``
        能把它正确导出, 不会因为缺 handler 报错.
        """
        async def _noop_handler(**kwargs: Any) -> dict[str, Any]:
            """Synthetic tool no-op. 框架会在 stream 中拦截并替代真实响应."""
            return {
                "synthetic": True,
                "tool": name,
                "received": kwargs,
                "ack": "framework_will_handle_card_emission",
            }
        return self.register(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=_noop_handler,
        )

    def register_handler(self, name: str, handler: ToolHandler) -> None:
        """为已存在的工具绑定本地 handler。

        Args:
            name: 已注册工具名。
            handler: 异步可调用对象。

        Raises:
            ValueError: 当 ``name`` 尚未注册时。
        """
        logger.info("register_handler_start", name=name)
        if name not in self._tools:
            logger.error("register_handler_failed", name=name, error="tool_not_found")
            raise ValueError(f"Tool '{name}' not found in registry. Register it first.")
        self._tools[name].handler = handler
        logger.debug("handler_registered", name=name)

    def register_remote(
        self,
        name: str,
        remote_url: str,
        remote_tool_name: str,
        description: str = "",
        input_schema: dict[str, Any] | None = None,
    ) -> None:
        """注册一个指向远程 MCP 端点的工具。

        Args:
            name: 本地工具名（用于路由）。
            remote_url: 远程端点 URL。
            remote_tool_name: 远程端点上的实际工具名。
            description: 人类可读描述。
            input_schema: 工具入参的 JSON Schema。
        """
        logger.info(
            "register_remote_tool_start",
            name=name,
            remote_url=remote_url,
            remote_tool_name=remote_tool_name,
        )
        self.register(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=None,
            remote_url=remote_url,
            remote_tool_name=remote_tool_name,
            enabled=True,
        )
        logger.debug("remote_tool_registered", name=name, remote_url=remote_url)

    async def call_tool(self, name: str, **kwargs: Any) -> Any:
        """根据工具配置调用本地 handler 或远程端点。

        Args:
            name: 工具名。
            **kwargs: 透传给工具的参数。

        Returns:
            工具执行结果；本地 handler 直接返回其值，远程调用返回
            响应 JSON 中的 ``result`` 字段。

        Raises:
            KeyError: 工具未注册。
            RuntimeError: 工具被禁用或配置无效。
            httpx.HTTPError: 远程调用失败时。
        """
        logger.info("call_tool_start", name=name, args_keys=list(kwargs.keys()))
        if name not in self._tools:
            logger.error("call_tool_failed", name=name, error="tool_not_found")
            raise KeyError(f"Tool '{name}' not found in registry")

        tool = self._tools[name]
        if not tool.enabled:
            logger.warning("call_tool_disabled", name=name)
            raise RuntimeError(f"Tool '{name}' is disabled")

        if tool.handler is not None:
            logger.debug("calling_local_tool", name=name)
            return await tool.handler(**kwargs)

        if tool.remote_url is not None and tool.remote_tool_name is not None:
            logger.debug("calling_remote_tool", name=name, remote_url=tool.remote_url)
            try:
                client = await self._get_client()
                payload = {
                    "tool_name": tool.remote_tool_name,
                    "arguments": kwargs,
                }
                response = await client.post(
                    tool.remote_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            except httpx.HTTPError as e:
                logger.error(
                    "call_tool_remote_failed",
                    name=name,
                    remote_url=tool.remote_url,
                    error=str(e),
                )
                raise
            result = response.json()
            return result.get("result", result)

        logger.error("call_tool_failed", name=name, error="no_handler_or_remote")
        raise RuntimeError(f"Tool '{name}' has neither handler nor remote configuration")

    def set_enabled(self, name: str, enabled: bool) -> None:
        """启用或禁用指定工具。

        Args:
            name: 工具名。
            enabled: ``True`` 启用，``False`` 禁用。

        Raises:
            KeyError: 工具未注册。
        """
        logger.info("set_enabled_start", name=name, enabled=enabled)
        if name not in self._tools:
            logger.error("set_enabled_failed", name=name, error="tool_not_found")
            raise KeyError(f"Tool '{name}' not found in registry")
        self._tools[name].enabled = enabled
        logger.debug("tool_enabled_changed", name=name, enabled=enabled)

    def list_all(self) -> list[MCPTool]:
        """列出注册中心中所有工具的副本列表。"""
        return list(self._tools.values())

    def get_tool(self, name: str) -> MCPTool | None:
        """按名称获取工具实例；不存在时返回 ``None``。"""
        return self._tools.get(name)

    def to_opencode_format(
        self, names: Iterable[str] | None = None
    ) -> list[dict[str, Any]]:
        """按 OpenCode SDK 的格式导出工具列表。

        Args:
            names: 可选的名字过滤器；为 ``None`` 时导出全部启用的工具。

        Returns:
            适配 OpenCode 的工具字典列表（只包含 ``enabled=True`` 的项）。
        """
        if names is None:
            tools = list(self._tools.values())
        else:
            wanted = set(names)
            tools = [t for t in self._tools.values() if t.name in wanted]
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
            if tool.enabled
        ]

    def to_claude_code_format(
        self, names: Iterable[str] | None = None
    ) -> list[dict[str, Any]]:
        """按 Claude Code SDK 的格式导出工具列表。

        返回扁平的工具 spec 字典列表（不带外层信封），匹配
        ``ClaudeAgentOptions.tools`` 期望的形状。

        Args:
            names: 可选的名字过滤器；为 ``None`` 时导出全部启用的工具。

        Returns:
            适配 Claude Code 的工具字典列表（只包含 ``enabled=True`` 的项）。
        """
        if names is None:
            tools = list(self._tools.values())
        else:
            wanted = set(names)
            tools = [t for t in self._tools.values() if t.name in wanted]
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in tools
            if tool.enabled
        ]

    def list_all_by_names(self, names: Iterable[str]) -> list[MCPTool]:
        """按名字顺序返回对应的 ``MCPTool`` 对象。

        Args:
            names: 工具名列表；未知名称会被静默跳过。

        Returns:
            按入参顺序、仅包含已注册工具的列表。
        """
        return [t for t in (self._tools.get(n) for n in names) if t is not None]

    @classmethod
    def from_config(cls, config: list[dict[str, Any]]) -> MCPRegistry:
        """从配置字典列表构建注册中心。

        ``settings.mcp_tools_config`` 始终为列表形式（list-shape），不再支持
        旧的 ``{"tools": {name: {...}}}`` 字典形态。

        Args:
            config: 工具配置字典的列表；非 dict 或无 ``name`` 的项会被跳过。

        Returns:
            填充好的 ``MCPRegistry`` 实例。

        Raises:
            TypeError: 当 ``config`` 不是 list 时。
        """
        logger.info("registry_from_config_start", config_count=len(config) if isinstance(config, list) else 0)
        if not isinstance(config, list):
            logger.error("registry_from_config_failed", error="not_a_list", got_type=type(config).__name__)
            raise TypeError(
                f"mcp_tools_config must be a list of tool dicts, got {type(config).__name__}"
            )
        registry = cls()
        for tool_config in config:
            if not isinstance(tool_config, dict):
                continue
            name = tool_config.get("name")
            if not name:
                continue
            remote_url = tool_config.get("remote_url")
            if remote_url:
                registry.register_remote(
                    name=name,
                    remote_url=remote_url,
                    remote_tool_name=tool_config.get("remote_tool_name", name),
                    description=tool_config.get("description", ""),
                    input_schema=tool_config.get("input_schema"),
                )
            else:
                registry.register(
                    name=name,
                    description=tool_config.get("description", ""),
                    input_schema=tool_config.get("input_schema"),
                    enabled=tool_config.get("enabled", True),
                )
        return registry

    async def __aenter__(self) -> MCPRegistry:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
