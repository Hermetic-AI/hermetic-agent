"""ScenarioRegistry — 集中管理所有加载到的 ScenarioConfig.

支持:
- 从目录递归加载 *.scenario.yaml
- 从字典列表注册
- 运行时 register / unregister / get / list
- 热重载 (reload)
- DB 覆盖 (load_from_db, stub)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import structlog

from hermetic_agent.scenarios.config import ScenarioConfig
from hermetic_agent.scenarios.errors import ScenarioNotFoundError
from hermetic_agent.scenarios.loader import load_scenario

logger = structlog.get_logger(__name__)


class ScenarioRegistry:
    """Scenario 配置中心.

    Usage:
        reg = ScenarioRegistry()
        reg.load_from_paths("/work/scenarios/")
        cfg = reg.get("flight_booking")
    """

    def __init__(self, ctx: dict[str, str] | None = None) -> None:
        self._scenarios: dict[str, ScenarioConfig] = {}
        self._ctx = ctx or {}

    # ------------------------------------------------------------------
    # 加载
    # ------------------------------------------------------------------

    def load_from_paths(
        self, *paths: str | os.PathLike[str]
    ) -> list[ScenarioConfig]:
        """从指定路径加载所有 *.scenario.yaml 文件.

        接受目录 (递归) 或单个文件; 解析失败的条目会被跳过并打 warning.
        占位符解析使用构造时传入的 ctx; 每个文件加载时自动注入
        ``SCENARIO_DIR`` = ``work/scenarios/{name}/`` (基于文件名).
        """
        loaded: list[ScenarioConfig] = []
        for raw in paths:
            p = Path(raw)
            if not p.exists():
                logger.warning("scenario_path_not_found", path=str(p))
                continue
            candidates: list[Path] = (
                [p] if p.is_file() else sorted(p.rglob("*.scenario.yaml"))
            )
            for cand in candidates:
                file_ctx = self._file_ctx(cand)
                try:
                    cfg = load_scenario(cand, file_ctx)
                except Exception as e:  # noqa: BLE001 - 加载失败仅记日志
                    logger.warning(
                        "scenario_load_failed",
                        path=str(cand),
                        error=str(e),
                    )
                    continue
                self._scenarios[cfg.name] = cfg
                loaded.append(cfg)
        logger.info(
            "scenarios_loaded", count=len(loaded), total=len(self._scenarios)
        )
        return loaded

    def _file_ctx(self, path: Path) -> dict[str, str]:
        """构建 per-file 解析上下文, 自动注入 SCENARIO_DIR.

        ``{name}.scenario.yaml`` → SCENARIO_DIR = ``{parent}/{name}/``
        """
        ctx = dict(self._ctx)
        if path.suffix == ".yaml" and path.name.endswith(".scenario.yaml"):
            stem = path.name[: -len(".scenario.yaml")]
            if stem:
                ctx["SCENARIO_DIR"] = str(path.parent / stem)
        return ctx

    def load_from_dict(
        self, configs: list[dict[str, Any]]
    ) -> list[ScenarioConfig]:
        """从字典列表直接注册 (绕过 YAML 加载, 用于测试或 DB 反序列化)."""
        loaded: list[ScenarioConfig] = []
        for cfg_dict in configs:
            try:
                cfg = ScenarioConfig.model_validate(cfg_dict)
            except Exception as e:  # noqa: BLE001
                logger.warning("scenario_dict_invalid", error=str(e))
                continue
            self._scenarios[cfg.name] = cfg
            loaded.append(cfg)
        return loaded

    def load_from_db(
        self, rows: list[dict[str, Any]] | None = None,
        service_container: Any = None,
    ) -> list[ScenarioConfig]:
        """从 DB 加载并覆盖 YAML 默认.

        Args:
            rows: 向前兼容 — 直接传 dict 列表跳过 service 查询.
            service_container: ServiceContainer 实例, 有 scenario_service.

        Returns:
            成功加载的 ScenarioConfig 列表.
        """
        if rows is None and service_container is not None:
            import asyncio
            try:
                db_scenarios = asyncio.get_event_loop().run_until_complete(
                    service_container.scenario_service.list_active()
                )
            except RuntimeError:
                # 嵌套 event loop — 跳过 DB 加载, 返回空列表
                logger.warning("load_from_db_nested_loop_skipped")
                return []
            rows = []
            for s in db_scenarios:
                rows.append({
                    "name": s.name,
                    "version": str(s.version),
                    "description": s.description,
                    "config": s.config,
                    "source": s.source,
                    "enabled": s.status == "enabled",
                })
        if not rows:
            logger.info("load_from_db_empty")
            return []
        loaded = self.load_from_dict(rows)
        logger.info("scenarios_loaded_from_db", count=len(loaded))
        return loaded

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, cfg: ScenarioConfig, override: bool = True) -> None:
        """注册一个 scenario. 默认同名覆盖 (override=True)."""
        if not override and cfg.name in self._scenarios:
            logger.warning("scenario_already_registered", name=cfg.name)
            return
        self._scenarios[cfg.name] = cfg
        logger.debug("scenario_registered", name=cfg.name)

    def unregister(self, name: str) -> bool:
        """注销指定 scenario. 返回是否实际删除了一项."""
        if name in self._scenarios:
            del self._scenarios[name]
            logger.debug("scenario_unregistered", name=name)
            return True
        return False

    def get(self, name: str) -> ScenarioConfig | None:
        """按名称获取 scenario, 不存在返回 None."""
        return self._scenarios.get(name)

    def get_or_raise(self, name: str) -> ScenarioConfig:
        """按名称获取, 不存在抛 ScenarioNotFoundError."""
        cfg = self.get(name)
        if cfg is None:
            raise ScenarioNotFoundError(
                f"Scenario {name!r} not found",
                action=f"Available: {sorted(self._scenarios.keys())}",
            )
        return cfg

    # ------------------------------------------------------------------
    # 列表
    # ------------------------------------------------------------------

    def list_all(self) -> list[ScenarioConfig]:
        """返回所有 scenario 列表 (按 name 排序)."""
        return [self._scenarios[k] for k in sorted(self._scenarios)]

    def list_enabled(self) -> list[ScenarioConfig]:
        """返回所有 enabled=True 的 scenario."""
        return [c for c in self.list_all() if c.enabled]

    def list_names(self) -> list[str]:
        """返回所有 scenario 名 (排序)."""
        return sorted(self._scenarios)

    # ------------------------------------------------------------------
    # 热重载
    # ------------------------------------------------------------------

    def reload(
        self, *paths: str | os.PathLike[str]
    ) -> list[ScenarioConfig]:
        """清空当前注册表, 从 paths 重新加载."""
        self._scenarios.clear()
        return self.load_from_paths(*paths)

    def get_routing_log(self) -> list[dict[str, Any]]:
        """导出 routing 历史 — 当前 stub, P7 阶段接 router.routing_log."""
        return []


__all__ = ["ScenarioRegistry"]
