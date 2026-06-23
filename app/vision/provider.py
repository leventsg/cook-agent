"""
Vision Model Provider。

基于统一的 LLMProvider 架构封装视觉模型调用能力，
为图像理解、多模态分析等场景提供统一接口。
"""

import base64
import logging
from dataclasses import dataclass
from typing import List, Optional, Type, TypeVar, Union

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel

from app.config import settings
from app.config.llm_config import VisionLLMConfig
from app.llm import get_usage_callbacks, llm_context

logger = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)

@dataclass
class ImageInput:
    """
    表示用于视觉处理的图像输入。

    支持两种输入模式：

    - URL 模式：image_url 为图像的直接访问地址
    - Base64 模式：image_data 为经过 Base64 编码的图像数据，
    并通过 mime_type 指定图像 MIME 类型
    """

    image_url: Optional[str] = None
    image_data: Optional[str] = None  # Base64 encoded
    mime_type: str = "image/jpeg"

    def to_message_content(self) -> dict:
        # 转换为 LangChain 消息内容格式
        if self.image_url:
            return {"type": "image_url", "image_url": {"url": self.image_url}}
        elif self.image_data:
            data_url = f"data:{self.mime_type};base64,{self.image_data}"
            return {"type": "image_url", "image_url": {"url": data_url}}
        else:
            raise ValueError("Either image_url or image_data must be provided")

    @classmethod
    def from_url(cls, url: str) -> "ImageInput":
        """从 URL 创建 ImageInput 实例"""
        return cls(image_url=url)

    @classmethod
    def from_base64(cls, data: str, mime_type: str = "image/jpeg") -> "ImageInput":
        """从 Base64 编码数据创建 ImageInput 实例"""
        return cls(image_data=data, mime_type=mime_type)

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str = "image/jpeg") -> "ImageInput":
        """从 bytes 创建 ImageInput 实例"""
        encoded = base64.b64encode(data).decode("utf-8")
        return cls(image_data=encoded, mime_type=mime_type)

class VisionProvider:
    """
    VisionProvider

    基于统一的 LLMProvider 基础设施实现，
    并使用 llm_type="vision" 作为模型类型
    """

    MODULE_NAME = "vision_understanding"

    def __init__(self):
        """
        使用 LLMProvider 初始化视觉模型提供器（VisionProvider）。
        """
        from app.llm.provider import LLMProvider

        self._provider = LLMProvider(settings.llm)
        self._invoker = self._provider.create_invoker(llm_type="vision")
        self._callbacks = get_usage_callbacks()

    @property
    def config(self) -> VisionLLMConfig:
        """获取vison 模型配置."""
        profile = self._provider.get_profile("vision")
        return profile 

    @property
    def is_enabled(self) -> bool:
        """检查 vison 模型是否已启用."""
        return bool(self.config.api_key)

    def build_multimodal_message(
        self,
        text: str,
        images: List[ImageInput],
    ) -> HumanMessage:
        """
        构建包含文本和图像输入的 multimodal HumanMessage。

        Args:
            text: prompt/query 文本
            images: 图像输入列表

        Returns:
            HumanMessage 实例
        """
        content: List[Union[str, dict]] = []

        # 添加文本内容
        if text:
            content.append({"type": "text", "text": text})

        # 添加图像内容
        for image in images:
            content.append(image.to_message_content())

        return HumanMessage(content=content)  # type: ignore

    async def analyze(
        self,
        text: str,
        images: List[ImageInput],
        system_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        分析图像和文本内容

        Args:
            text: prompt/query 文本
            images: 图像输入列表
            system_prompt: 系统提示（可选）
            user_id: 用户 ID（可选）
            conversation_id: 对话 ID（可选）

        Returns:
            模型响应字符串格式
        """
        if not self.is_enabled:
            raise RuntimeError("Vision module is not enabled or API key is missing")

        if not images:
            raise ValueError("At least one image is required")

        messages: List[BaseMessage] = []

        if system_prompt:
            from langchain_core.messages import SystemMessage

            messages.append(SystemMessage(content=system_prompt))

        # 构建 multimodal 消息，包含文本和图像输入
        human_msg = self.build_multimodal_message(text, images)
        messages.append(human_msg)

        logger.info(
            f"Vision analysis: text='{text[:50]}...', images={len(images)}, "
            f"model={self.config.model_names[0]}"
        )

        try:
            # 使用 llm_context 进行调用上下文管理
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                response = await self._invoker.ainvoke(
                    messages,
                    response_format={
                        "type": "json_object"
                    }, 
                )
            result = str(response.content)
            logger.debug(f"Vision response: {result[:200]}...")
            return result
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}", exc_info=True)
            raise

    async def analyze_json(
        self,
        text: str,
        images: List[ImageInput],
        schema: Type[ModelT],
        system_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> ModelT:
        """分析图像和文本内容，并按 Pydantic schema 返回结构化 JSON."""
        if not self.is_enabled:
            raise RuntimeError("Vision module is not enabled or API key is missing")

        if not images:
            raise ValueError("At least one image is required")

        messages: List[BaseMessage] = []

        if system_prompt:
            from langchain_core.messages import SystemMessage

            messages.append(SystemMessage(content=system_prompt))

        messages.append(self.build_multimodal_message(text, images))

        logger.info(
            f"Vision structured analysis: text='{text[:50]}...', "
            f"images={len(images)}, model={self.config.model_names[0]}"
        )

        try:
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                return await self._invoker.ainvoke_json(messages, schema)
        except Exception as e:
            logger.error(f"Vision structured analysis failed: {e}", exc_info=True)
            raise

    def validate_image(
        self, mime_type: str, size_bytes: int
    ) -> tuple[bool, Optional[str]]:
        """
        验证图像格式和大小是否符合要求。

        Args:
            mime_type: 图像 MIME 类型
            size_bytes: 图像大小（字节）

        Returns:
            (is_valid, error_message)
        """
        config = self.config

        # 检查图像格式是否受支持
        if mime_type not in config.supported_formats:
            return (
                False,
                f"Unsupported image format: {mime_type}. Supported: {config.supported_formats}",
            )

        # 检查大小是否超过最大限制
        max_size_bytes = config.max_image_size_mb * 1024 * 1024
        if size_bytes > max_size_bytes:
            return (
                False,
                f"Image too large: {size_bytes / 1024 / 1024:.2f}MB. Maximum: {config.max_image_size_mb}MB",
            )

        return True, None


vision_provider = VisionProvider()
