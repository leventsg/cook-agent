"""
Vision Configuration

用于配置视觉分析中的领域检测相关参数。
模型配置由 LLMConfig.vision（VisionLLMConfig）统一管理。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ImageGenerationConfig(BaseModel):
    """
    使用 OpenAI 兼容 API（如 DALL·E 3 等）进行图像生成的相关配置。
    """

    enabled: bool = True
    api_key: str | None = None  # Loaded from .env (OPENAI_IMAGE_API_KEY)
    base_url: str | None = None  # Optional custom base URL for OpenAI-compatible APIs
    model: str = "dall-e-3"
    temperature: float = 1.0  # Only used for some compatible APIs


class ImageStorageConfig(BaseModel):
    """
    使用 imgbb API 进行图像存储的配置。
    用于持久化生成的图像。
    """

    enabled: bool = True
    api_key: str | None = None  # Loaded from .env (IMGBB_STORAGE_API_KEY)
    upload_url: str = "https://api.imgbb.com/1/upload"
    expiration: int | None = None  # Optional expiration in seconds (60-15552000), None = never


class VisionConfig(BaseModel):
    """
    用于美食领域检测的视觉配置。
    模型配置由 LLMConfig.vision 统一管理。
    """

    # 美食领域检测设置
    food_related_keywords: list[str] = Field(
        default_factory=lambda: [
            "菜品", "食材", "烹饪", "做菜", "食物", "美食", "饭菜",
            "炒", "煮", "蒸", "烤", "煎", "炸", "焖", "炖",
            "蔬菜", "水果", "肉类", "海鲜", "调料", "配料",
            "早餐", "午餐", "晚餐", "甜点", "饮品",
            "厨房", "刀工", "火候", "调味"
        ]
    )
