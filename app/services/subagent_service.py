"""
Subagent 管理服务

负责将用户自定义的 Subagent 配置持久化到数据库并同步到内存注册表
"""

import re
from typing import Optional

from sqlalchemy import select

from app.agent.database.models import AgentSubagentConfigModel
from app.agent.registry import AgentHub
from app.agent.subagents.base import SubagentConfig
from app.agent.subagents.registry import subagent_registry
from app.database.session import get_session_context

NAME_PATTERN = re.compile(r"^[a-z0-9_]{2,64}$")


class SubagentService:
    """
    用于管理用户自定义 Subagent 及其状态的服务。
    """

    async def list_configs(self, user_id: str) -> list[SubagentConfig]:
        async with get_session_context() as session:
            stmt = select(AgentSubagentConfigModel).where(
                AgentSubagentConfigModel.user_id == user_id
            )
            result = await session.execute(stmt)
            configs = list(result.scalars().all())

        return [self._config_from_model(model) for model in configs]

    async def sync_user_subagents(self, user_id: str) -> list[SubagentConfig]:
        configs = await self.list_configs(user_id)

        builtin_names = set(subagent_registry.get_builtin_names())
        custom_configs = [config for config in configs if config.name not in builtin_names]
        builtin_overrides = {
            config.name: config.enabled
            for config in configs
            if config.name in builtin_names
        }

        enabled = {
            name for name in builtin_names if builtin_overrides.get(name, True)
        }
        enabled.update({config.name for config in custom_configs if config.enabled})

        subagent_registry.set_user_configs(user_id, custom_configs)
        subagent_registry.set_user_enabled(user_id, enabled)

        return subagent_registry.get_all_configs(user_id)

    async def create_subagent(
        self,
        *,
        user_id: str,
        name: str,
        display_name: str,
        description: str,
        system_prompt: str,
        tools: Optional[list[str]] = None,
        max_iterations: int = 10,
        category: str = "custom",
    ) -> SubagentConfig:
        self._validate_name(name)
        self._validate_tools(tools or [], user_id)

        if name in subagent_registry.get_builtin_names():
            raise ValueError("Subagent name conflicts with builtin subagent")

        async with get_session_context() as session:
            existing_stmt = select(AgentSubagentConfigModel).where(
                AgentSubagentConfigModel.user_id == user_id,
                AgentSubagentConfigModel.name == name,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                raise ValueError("Subagent name already exists")

            config = AgentSubagentConfigModel(
                user_id=user_id,
                name=name,
                display_name=display_name,
                description=description,
                system_prompt=system_prompt,
                tools=tools or [],
                max_iterations=max_iterations,
                category=category,
                enabled=True,
            )
            session.add(config)

        await self.sync_user_subagents(user_id)
        return self._config_from_model(config)

    async def delete_subagent(self, user_id: str, name: str) -> bool:
        if name in subagent_registry.get_builtin_names():
            raise ValueError("Builtin subagent cannot be deleted")

        async with get_session_context() as session:
            stmt = select(AgentSubagentConfigModel).where(
                AgentSubagentConfigModel.user_id == user_id,
                AgentSubagentConfigModel.name == name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                return False

            await session.delete(existing)

        await self.sync_user_subagents(user_id)
        return True

    async def update_subagent(
        self,
        *,
        user_id: str,
        name: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        tools: Optional[list[str]] = None,
        max_iterations: Optional[int] = None,
        category: Optional[str] = None,
    ) -> SubagentConfig | None:
        if name in subagent_registry.get_builtin_names():
            raise ValueError("Builtin subagent cannot be updated")

        if tools is not None:
            self._validate_tools(tools, user_id)

        async with get_session_context() as session:
            stmt = select(AgentSubagentConfigModel).where(
                AgentSubagentConfigModel.user_id == user_id,
                AgentSubagentConfigModel.name == name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            if not existing:
                return None

            if display_name is not None:
                existing.display_name = display_name
            if description is not None:
                existing.description = description
            if system_prompt is not None:
                existing.system_prompt = system_prompt
            if tools is not None:
                existing.tools = tools
            if max_iterations is not None:
                existing.max_iterations = max_iterations
            if category is not None:
                existing.category = category

        await self.sync_user_subagents(user_id)
        return self._config_from_model(existing)

    async def set_enabled(self, user_id: str, name: str, enabled: bool) -> bool:
        builtin_names = set(subagent_registry.get_builtin_names())
        async with get_session_context() as session:
            stmt = select(AgentSubagentConfigModel).where(
                AgentSubagentConfigModel.user_id == user_id,
                AgentSubagentConfigModel.name == name,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()

            if name in builtin_names:
                if not existing:
                    builtin_config = self._get_builtin_config(name)
                    if not builtin_config:
                        return False
                    existing = AgentSubagentConfigModel(
                        user_id=user_id,
                        name=builtin_config.name,
                        display_name=builtin_config.display_name,
                        description=builtin_config.description,
                        system_prompt=builtin_config.system_prompt,
                        tools=list(builtin_config.tools or []),
                        max_iterations=builtin_config.max_iterations,
                        category=builtin_config.category,
                        enabled=enabled,
                    )
                    session.add(existing)
                else:
                    existing.enabled = enabled
            else:
                if not existing:
                    return False
                existing.enabled = enabled

        await self.sync_user_subagents(user_id)
        return True

    def _validate_name(self, name: str) -> None:
        if not NAME_PATTERN.match(name):
            raise ValueError("Subagent name must be 2-64 chars with lowercase and _")

    def _validate_tools(self, tools: list[str], user_id: str) -> None:
        for tool_name in tools:
            if tool_name.startswith("subagent_"):
                raise ValueError("Subagent cannot call another subagent")
            tool = AgentHub.get_tool(tool_name, user_id=user_id)
            if not tool:
                raise ValueError(f"Tool '{tool_name}' not found")

    def _config_from_model(self, model: AgentSubagentConfigModel) -> SubagentConfig:
        return SubagentConfig(
            name=model.name,
            display_name=model.display_name,
            description=model.description,
            system_prompt=model.system_prompt,
            tools=list(model.tools or []),
            max_iterations=model.max_iterations,
            enabled=model.enabled,
            builtin=False,
            category=model.category or "custom",
        )

    def _get_builtin_config(self, name: str) -> Optional[SubagentConfig]:
        for config in subagent_registry.get_builtin_configs():
            if config.name == name:
                return config
        return None


subagent_service = SubagentService()
