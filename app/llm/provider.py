"""
LLM Provider - 统一的 LLM 初始化和调用入口

核心概念:
1. LLMProvider - 全局 LLM 提供者，管理配置和创建 LLM 实例
2. LLMInvoker - LLM 调用器，封装了调用逻辑和 usage tracking
"""
from __future__ import annotations

import random
from typing import Any, AsyncIterator, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_openai import ChatOpenAI
from app.config.llm_config import LLMConfig, LLMProfileConfig, LLMType

class LLMProvider:
    """
    LLMProvider - 统一的 LLM 创建和管理入口

    使用方式:
        provider = LLMProvider(settings.llm)

        # 创建带 usage tracking 的 invoker（推荐）
        invoker = provider.create_invoker("fast")
        response = await invoker.ainvoke(messages)

        # 直接创建 ChatOpenAI 实例（不推荐，除非有特殊需求）
        llm = provider.create_llm("normal", streaming=True)
    """

    def __init__(self, config: LLMConfig):
        """
        初始化 LLM Provider

        Args:
            config: LLM 配置（通常来自 settings.llm）
        """
        self._config = config

    def get_profile(self, llm_type: LLMType | str | None = None) -> LLMProfileConfig:
        """获取指定类型的 LLM 配置 profile"""
        return self._config.get_profile(llm_type)

    def pick_model(self, llm_type: LLMType | str | None = None) -> str:
        """
        随机选择一个模型名称（用于负载均衡）

        Args:
            llm_type: LLM 类型 (fast/normal)

        Returns:
            选中的模型名称
        """
        profile = self.get_profile(llm_type)
        if not profile.model_names:
            raise ValueError("model_names cannot be empty")
        return random.choice(profile.model_names)
    
    def create_llm(
        self,
        llm_type: LLMType | str | None = None,
        *,
        streaming: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> ChatOpenAI:
        """
        创建原生 ChatOpenAI 实例

        注意: 此方法创建的实例不包含 usage tracking，
        推荐使用 create_invoker() 方法获取带 tracking 的调用器

        Args:
            llm_type: LLM 类型 (fast/normal/vision)
            streaming: 是否启用流式输出
            temperature: 温度参数（可选覆盖配置）
            max_tokens: 最大 tokens（可选覆盖配置）
            timeout: 请求超时时间（可选，vision profile 默认 120s）
            **kwargs: 其他 ChatOpenAI 参数

        Returns:
            ChatOpenAI 实例
        """
        profile = self.get_profile(llm_type)

        effective_timeout = timeout
        if effective_timeout is None and hasattr(profile, "request_timeout"):
            effective_timeout = profile.request_timeout # type: ignore

        llm_kwargs = {
            "model": profile.pick_default_model(),
            "api_key": profile.api_key,
            "base_url": profile.base_url,
            "temperature": temperature if temperature is not None else profile.temperature,
            "max_completion_tokens": max_tokens if max_tokens is not None else profile.max_tokens,
            "streaming": streaming,
            "stream_usage": True,
            **kwargs,
        }

        if effective_timeout is not None:
            llm_kwargs["timeout"] = effective_timeout

        return ChatOpenAI(**llm_kwargs)
    
    def create_invoker(
        self,
        llm_type: LLMType | str | None = None,
        *,
        streaming: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> "LLMInvoker":
        """
        创建带 usage tracking 的 LLM 调用器（推荐使用）

        Args:
            llm_type: LLM 类型 (fast/normal)
            streaming: 是否启用流式输出
            temperature: 温度参数（可选覆盖配置）
            max_tokens: 最大 tokens（可选覆盖配置）
            **kwargs: 其他 ChatOpenAI 参数

        Returns:
            LLMInvoker 实例
        """
        from app.llm.callbacks import get_usage_callbacks

        base_llm = self.create_llm(
            llm_type,
            streaming=streaming,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return LLMInvoker(
            provider=self,
            llm_type=llm_type,
            base_llm=base_llm,
            callbacks=get_usage_callbacks(),
        )
    
class LLMInvoker:
    """
    LLMInvoker - 封装 LLM 调用逻辑

    特性:
    - 自动附加 usage tracking callbacks
    - 支持动态模型选择（每次调用可选择不同模型）
    - 支持 tool calling
    - 支持流式输出

    使用方式:
        # 普通调用
        response = await invoker.ainvoke(messages)

        # 流式调用
        async for chunk in invoker.astream(messages):
            print(chunk.content)

        # 带 tools 调用
        response = await invoker.ainvoke_with_tools(messages, tools)
    """

    def __init__(
        self,
        provider: LLMProvider,
        llm_type: LLMType | str | None,
        base_llm: ChatOpenAI,
        callbacks: List[BaseCallbackHandler] | None = None,
    ):
        self._provider = provider
        self._llm_type = llm_type
        self._base_llm = base_llm
        self._callbacks = callbacks or []

    def _get_llm_with_model(self, tools: list[Any] | None = None) -> ChatOpenAI:
        """
        获取绑定了随机模型的 LLM 实例

        每次调用都会随机选择一个模型，实现负载均衡
        """
        model = self._provider.pick_model(self._llm_type)
        llm = self._base_llm.bind(model=model)

        if tools:
            llm = llm.bind(tools=tools)  

        return llm 

    def _prepare_config(self, kwargs: dict) -> dict:
        """准备调用配置，合并 callbacks"""
        # 提取已有的 callbacks
        call_callbacks = kwargs.pop("callbacks", None) or []
        config = kwargs.pop("config", None) or {}

        if isinstance(config, dict):
            config_callbacks = config.get("callbacks", []) or []
        else:
            config_callbacks = []

        # 合并所有 callbacks
        merged = list(call_callbacks) + list(config_callbacks) + self._callbacks
        if merged:
            kwargs["config"] = {"callbacks": merged}

        return kwargs

    async def ainvoke(self, messages: list, **kwargs: Any) -> Any:
        """异步调用 LLM"""
        kwargs = self._prepare_config(kwargs)
        return await self._get_llm_with_model().ainvoke(messages, **kwargs)

    async def ainvoke_with_tools(
        self, messages: list, tools: list, **kwargs: Any
    ) -> Any:
        """异步调用 LLM（带 tools）"""
        kwargs = self._prepare_config(kwargs)
        return await self._get_llm_with_model(tools=tools).ainvoke(messages, **kwargs)
    
    def astream(self, messages: list, **kwargs: Any) -> AsyncIterator[Any]:
        """流式调用 LLM"""
        kwargs = self._prepare_config(kwargs)
        return self._get_llm_with_model().astream(messages, **kwargs)

    async def astream_with_tools(
        self, messages: list, tools: list, **kwargs: Any
    ) -> AsyncIterator[Any]:
        """流式调用 LLM（带 tools）"""
        kwargs = self._prepare_config(kwargs)
        async for chunk in self._get_llm_with_model(tools=tools).astream(
            messages, **kwargs
        ):
            yield chunk