"""Nacos AI Registry Sync - MCP/Agent/Skill/Prompt 双向同步.

将本地注册表与 Nacos AI 注册表进行同步:
- MCP Server: 本地 MCPRegistry → Nacos MCP 注册表 (release_mcp_server + register endpoint)
- Agent Card: 本地 AgentPool → Nacos A2A 注册表 (release_agent_card + register endpoint)
- Prompt: Nacos Prompt 注册表 → 本地 (get_prompt / subscribe_prompt)
"""

from __future__ import annotations

import socket
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _detect_ip() -> str:
    """探测本机 IP."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip: str = str(s.getsockname()[0])
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class NacosAISync:
    """Nacos AI 注册表同步器."""

    def __init__(self, nacos_client: Any, settings: Any) -> None:
        """初始化同步器."""
        self._client = nacos_client
        self._settings = settings
        self._ai_enabled: bool = getattr(settings, "nacos_ai_enabled", True)
        self._mcp_sync: bool = getattr(settings, "nacos_ai_mcp_sync", True)
        self._agent_sync: bool = getattr(settings, "nacos_ai_agent_sync", True)
        self._skill_sync: bool = getattr(settings, "nacos_ai_skill_sync", True)
        self._prompt_sync: bool = getattr(settings, "nacos_ai_prompt_sync", True)

    async def sync_all(
        self,
        mcp_registry: Any = None,
        agent_bridge: Any = None,
        skill_registry: Any = None,
    ) -> dict[str, bool]:
        """执行全量同步."""
        if not self._client.connected or not self._ai_enabled:
            logger.info("nacos_ai_sync_skipped", reason="not_connected_or_disabled")
            return {"mcp": False, "agent": False, "skill": False, "prompt": False}

        results: dict[str, bool] = {}

        if self._mcp_sync and mcp_registry:
            results["mcp"] = await self._sync_mcp_servers(mcp_registry)
        else:
            results["mcp"] = False

        if self._agent_sync and agent_bridge:
            results["agent"] = await self._sync_agents(agent_bridge)
        else:
            results["agent"] = False

        if self._skill_sync and skill_registry:
            results["skill"] = await self._sync_skills(skill_registry)
        else:
            results["skill"] = False

        if self._prompt_sync:
            results["prompt"] = await self._sync_prompts()
        else:
            results["prompt"] = False

        logger.info("nacos_ai_sync_completed", results=results)
        return results

    async def _sync_mcp_servers(self, mcp_registry: Any) -> bool:
        """将本地 MCP 工具发布到 Nacos MCP Server 注册表.

        调用 release_mcp_server 发布 MCP server 定义 + 工具规格,
        然后调用 register_mcp_server_endpoint 注册实际端点.
        """
        ai_service = self._client.ai_service
        if not ai_service:
            return False

        try:
            from v2.nacos.ai.model.ai_param import (
                RegisterMcpServerEndpointParam,
                ReleaseMcpServerParam,
            )
            from v2.nacos.ai.model.mcp.mcp import (
                McpServerBasicInfo,
                McpTool,
                McpToolSpecification,
            )

            tools = mcp_registry.list_all()
            mcp_tools = [
                McpTool(
                    name=tool.name,
                    description=tool.description,
                    inputSchema=tool.input_schema,
                )
                for tool in tools
            ]

            tool_spec = McpToolSpecification(tools=mcp_tools)
            from v2.nacos.ai.model.mcp.mcp import (
                McpServerRemoteServiceConfig,
                McpServiceRef,
            )
            from v2.nacos.ai.model.mcp.registry import ServerVersionDetail

            namespace = getattr(self._settings, "nacos_namespace", "")
            service_ref = McpServiceRef(
                namespaceId=namespace,
                groupName="DEFAULT_GROUP",
                serviceName="openagent-hub",
            )
            remote_config = McpServerRemoteServiceConfig(
                serviceRef=service_ref,
            )
            server_spec = McpServerBasicInfo(
                name="openagent-mcp",
                description="OpenAgent Hub MCP tools collection",
                protocol="mcp",
                version="1.0.0",
                versionDetail=ServerVersionDetail(
                    version="1.0.0",
                    is_latest=True,
                ),
                remoteServerConfig=remote_config,
                enabled=True,
            )

            release_param = ReleaseMcpServerParam(
                server_spec=server_spec,
                tool_spec=tool_spec,
            )
            await ai_service.release_mcp_server(release_param)
            logger.info("nacos_mcp_released", tool_count=len(mcp_tools))

            ip = _detect_ip()
            reg_param = RegisterMcpServerEndpointParam(
                mcp_name="openagent-mcp",
                address=ip,
                port=8000,
            )
            await ai_service.register_mcp_server_endpoint(reg_param)
            logger.info("nacos_mcp_endpoint_registered", address=ip, port=8000)
            return True
        except Exception as e:
            logger.error("nacos_mcp_sync_failed", error=str(e))
            return False

    async def _sync_agents(self, agent_bridge: Any) -> bool:
        """将本地 AgentBridge 注册到 Nacos A2A Agent Card 注册表.

        调用 release_agent_card 发布 AgentCard,
        然后调用 register_agent_endpoint 注册实际端点.
        """
        ai_service = self._client.ai_service
        if not ai_service:
            return False

        try:
            from a2a.types import AgentCapabilities, AgentSkill
            from v2.nacos.ai.model.a2a.a2a import AgentCard
            from v2.nacos.ai.model.ai_param import (
                RegisterAgentEndpointParam,
                ReleaseAgentCardParam,
            )

            agents = agent_bridge.list_agents()
            for name, agent_cfg in agents.items():
                base_url = getattr(agent_cfg, "base_url", "")
                card = AgentCard(
                    name=name,
                    description=f"OpenAgent sandbox: {name}",
                    url=base_url,
                    version="1.0.0",
                    capabilities=AgentCapabilities(streaming=True),
                    defaultInputModes=["text"],
                    defaultOutputModes=["text", "sse"],
                    skills=[
                        AgentSkill(
                            id="chat",
                            name="chat",
                            description="Agent chat capability",
                            tags=["chat", "agent"],
                        ),
                    ],
                )
                release_param = ReleaseAgentCardParam(
                    agent_card=card,
                    set_as_latest=True,
                )
                await ai_service.release_agent_card(release_param)
                logger.info("nacos_agent_card_released", name=name)

                ip = _detect_ip()
                reg_param = RegisterAgentEndpointParam(
                    agent_name=name,
                    version="1.0.0",
                    address=ip,
                    port=8000,
                    transport="http",
                    path="/agent/chat",
                )
                await ai_service.register_agent_endpoint(reg_param)
                logger.info("nacos_agent_endpoint_registered", name=name, ip=ip)

            logger.info("nacos_agent_sync_done", count=len(agents))
            return True
        except Exception as e:
            logger.error("nacos_agent_sync_failed", error=str(e))
            return False

    async def _sync_skills(self, skill_registry: Any) -> bool:
        """记录 Skill 元数据 (Nacos Skill 注册表需要 ZIP 上传, 此处仅日志)."""
        try:
            skills = skill_registry.list_all()
            for skill in skills:
                logger.info(
                    "nacos_skill_info",
                    name=skill.name,
                    version=skill.version,
                    description=skill.description[:80] if skill.description else "",
                )
            logger.info("nacos_skill_sync_done", count=len(skills))
            return True
        except Exception as e:
            logger.error("nacos_skill_sync_failed", error=str(e))
            return False

    async def _sync_prompts(self) -> bool:
        """从 Nacos Prompt 注册表拉取模板."""
        ai_service = self._client.ai_service
        if not ai_service:
            return False

        try:
            from v2.nacos.ai.model.ai_param import GetPromptParam

            param = GetPromptParam(prompt_key="openagent-system")
            prompt = await ai_service.get_prompt(param)
            if prompt:
                logger.info(
                    "nacos_prompt_fetched",
                    key=param.prompt_key,
                    version=getattr(prompt, "version", "?"),
                )
            else:
                logger.debug("nacos_prompt_not_found", key=param.prompt_key)
            return True
        except Exception as e:
            logger.debug("nacos_prompt_sync_skipped", reason=str(e))
            return True
