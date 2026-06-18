# app/agent/subagents/registry.py
"""
SubagentRegistry - Subagent 注册和管理中心

管理所有内置和用户自定义的 Subagent，提供统一的访问接口。
"""

import logging
from typing import TYPE_CHECKING, Optional, Type

if TYPE_CHECKING:
    from app.agent.subagents.base import BaseSubagent, SubagentConfig
    from app.agent.subagents.tool import SubagentTool

logger = logging.getLogger(__name__)


class SubagentRegistry:
    """
    Subagent 注册中心。

    职责：
    1. 管理内置 Subagent 的注册
    2. 管理用户自定义 Subagent
    3. 提供 Subagent 的查询和获取接口
    4. 生成 Subagent 对应的 Tool
    """

    _instance: Optional["SubagentRegistry"] = None

    def __new__(cls) -> "SubagentRegistry":
        """单例模式。"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """初始化注册中心。"""
        if self._initialized:
            return

        # 内置 Subagent 类注册表
        # key: subagent name, value: (SubagentClass, SubagentConfig)
        self._builtin_registry: dict[
            str, tuple[Type["BaseSubagent"], "SubagentConfig"]
        ] = {}

        # 用户自定义 Subagent 配置
        # key: user_id, value: {subagent_name: SubagentConfig}
        self._user_configs: dict[str, dict[str, "SubagentConfig"]] = {}

        # 用户启用的 Subagent
        # key: user_id, value: set of enabled subagent names
        self._user_enabled: dict[str, set[str]] = {}

        self._initialized = True
        logger.info("SubagentRegistry initialized")

    # ==================== 内置 Subagent 管理 ====================

    def register_builtin(
        self,
        subagent_cls: Type["BaseSubagent"],
        config: "SubagentConfig",
    ) -> None:
        """
        注册内置 Subagent。

        Args:
            subagent_cls: Subagent 类
            config: Subagent 配置
        """
        config.builtin = True
        self._builtin_registry[config.name] = (subagent_cls, config)
        logger.info(f"Registered builtin subagent: {config.name}")

    def get_builtin_configs(self) -> list["SubagentConfig"]:
        """获取所有内置 Subagent 配置。"""
        return [config for _, config in self._builtin_registry.values()]

    def get_builtin_names(self) -> list[str]:
        """获取所有内置 Subagent 名称。"""
        return list(self._builtin_registry.keys())

    def get_builtin_subagent(self, name: str) -> Optional["BaseSubagent"]:
        """
        获取内置 Subagent 实例。

        Args:
            name: Subagent 名称

        Returns:
            Subagent 实例，不存在则返回 None
        """
        entry = self._builtin_registry.get(name)
        if entry:
            subagent_cls, config = entry
            return subagent_cls(config)
        return None

    # ==================== 用户 Subagent 管理 ====================

    def register_user_subagent(
        self,
        user_id: str,
        config: "SubagentConfig",
    ) -> None:
        """
        注册用户自定义 Subagent。

        Args:
            user_id: 用户 ID
            config: Subagent 配置
        """
        config.builtin = False
        if user_id not in self._user_configs:
            self._user_configs[user_id] = {}
        self._user_configs[user_id][config.name] = config

        # 默认启用
        if user_id not in self._user_enabled:
            self._user_enabled[user_id] = set()
        self._user_enabled[user_id].add(config.name)

        logger.info(f"Registered user subagent: {config.name} for user {user_id}")

    def set_user_configs(self, user_id: str, configs: list["SubagentConfig"]) -> None:
        """设置用户 Subagent 配置缓存。"""
        self._user_configs[user_id] = {c.name: c for c in configs}

    def set_user_enabled(self, user_id: str, enabled_names: set[str]) -> None:
        """设置用户启用的 Subagent 名称缓存。"""
        self._user_enabled[user_id] = set(enabled_names)

    def unregister_user_subagent(
        self,
        user_id: str,
        name: str,
    ) -> bool:
        """
        删除用户自定义 Subagent。

        Args:
            user_id: 用户 ID
            name: Subagent 名称

        Returns:
            是否成功删除
        """
        if user_id in self._user_configs and name in self._user_configs[user_id]:
            del self._user_configs[user_id][name]
            if user_id in self._user_enabled:
                self._user_enabled[user_id].discard(name)
            return True
        return False

    def get_user_configs(self, user_id: str) -> list["SubagentConfig"]:
        """获取用户自定义的 Subagent 配置列表。"""
        if user_id not in self._user_configs:
            return []
        return list(self._user_configs[user_id].values())

    # ==================== 启用/禁用管理 ====================

    def enable_subagent(self, user_id: str, name: str) -> bool:
        """
        为用户启用 Subagent。

        Args:
            user_id: 用户 ID
            name: Subagent 名称

        Returns:
            是否成功
        """
        # 检查是否存在
        if name not in self._builtin_registry:
            if (
                user_id not in self._user_configs
                or name not in self._user_configs[user_id]
            ):
                return False

        if user_id not in self._user_enabled:
            self._user_enabled[user_id] = set()
        self._user_enabled[user_id].add(name)
        return True

    def disable_subagent(self, user_id: str, name: str) -> bool:
        """
        为用户禁用 Subagent。

        Args:
            user_id: 用户 ID
            name: Subagent 名称

        Returns:
            是否成功
        """
        if user_id in self._user_enabled:
            self._user_enabled[user_id].discard(name)
            return True
        return False

    def is_enabled(self, user_id: str, name: str) -> bool:
        """检查 Subagent 是否为用户启用。"""
        if user_id not in self._user_enabled:
            # 默认启用所有内置 Subagent
            return name in self._builtin_registry
        return name in self._user_enabled[user_id]

    def get_enabled_subagents(self, user_id: str) -> list[str]:
        """获取用户启用的 Subagent 名称列表。"""
        if user_id not in self._user_enabled:
            # 默认返回所有内置
            return list(self._builtin_registry.keys())
        return list(self._user_enabled[user_id])

    def init_user_defaults(self, user_id: str) -> None:
        """
        初始化用户的默认 Subagent 设置（启用所有内置）。

        Args:
            user_id: 用户 ID
        """
        if user_id not in self._user_enabled:
            self._user_enabled[user_id] = set(self._builtin_registry.keys())

    # ==================== 综合查询接口 ====================

    def get_all_configs(self, user_id: str) -> list["SubagentConfig"]:
        """
        获取用户可用的所有 Subagent 配置（内置 + 自定义）。

        Args:
            user_id: 用户 ID

        Returns:
            Subagent 配置列表
        """
        configs = []

        # 添加内置
        for name, (_, config) in self._builtin_registry.items():
            # 创建副本并设置 enabled 状态
            config_dict = config.to_dict()
            config_dict["enabled"] = self.is_enabled(user_id, name)
            from app.agent.subagents.base import SubagentConfig

            configs.append(SubagentConfig.from_dict(config_dict))

        # 添加用户自定义
        for config in self.get_user_configs(user_id):
            config_dict = config.to_dict()
            config_dict["enabled"] = self.is_enabled(user_id, config.name)
            from app.agent.subagents.base import SubagentConfig

            configs.append(SubagentConfig.from_dict(config_dict))

        return configs

    def get_subagent(
        self, name: str, user_id: Optional[str] = None
    ) -> Optional["BaseSubagent"]:
        """
        获取 Subagent 实例。

        Args:
            name: Subagent 名称
            user_id: 用户 ID（用于查找用户自定义 Subagent）

        Returns:
            Subagent 实例，不存在则返回 None
        """
        # 优先查找用户自定义
        if user_id and user_id in self._user_configs:
            config = self._user_configs[user_id].get(name)
            if config:
                # 用户自定义 Subagent 使用通用实现
                from app.agent.subagents.builtin.generic import GenericSubagent

                return GenericSubagent(config)

        # 查找内置
        return self.get_builtin_subagent(name)

    def get_enabled_subagent_tools(self, user_id: str) -> list["SubagentTool"]:
        """
        获取用户启用的所有 Subagent 对应的 Tool 列表。

        Args:
            user_id: 用户 ID

        Returns:
            SubagentTool 列表
        """
        from app.agent.subagents.tool import SubagentTool

        tools = []
        enabled_names = self.get_enabled_subagents(user_id)

        for name in enabled_names:
            subagent = self.get_subagent(name, user_id)
            if subagent:
                tools.append(SubagentTool(subagent))

        return tools

    # ==================== 工具方法 ====================

    def clear(self) -> None:
        """清空所有注册（主要用于测试）。"""
        self._builtin_registry.clear()
        self._user_configs.clear()
        self._user_enabled.clear()


# 单例
subagent_registry = SubagentRegistry()


__all__ = ["SubagentRegistry", "subagent_registry"]
