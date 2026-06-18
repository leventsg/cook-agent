"""
图片生成 Tool

使用 OpenAI 兼容的 API 根据文本描述生成图片。
支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
生成后自动上传到 imgbb 进行持久化存储。
"""

import logging

from app.agent.tools.base import BaseTool
from app.agent.types import ToolResult
from app.utils.image_storage import upload_to_imgbb

logger = logging.getLogger(__name__)


class ImageGeneratorTool(BaseTool):
    """
    图片生成 Tool。

    使用 OpenAI 兼容的 API 根据文本描述生成图片。
    支持 DALL-E 3 以及其他 OpenAI 兼容的图片生成服务。
    生成后自动上传到 imgbb 进行持久化存储。
    """

    name = "image_generator"
    description = "根据文本描述生成图片，并返回可访问的图片 URL。"
    parameters = {
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "图片描述，尽量具体（主体、风格、场景、构图）",
            },
            "size": {
                "type": "string",
                "enum": ["auto", "1024x1024", "1536x1024", "1024x1536", "256x256", "512x512", "1792x1024", "1024x1792"],
                "default": "1536x1024",
                "description": "图片尺寸（宽x高）",
            },
            "quality": {
                "type": "string",
                "enum": ["standard", "hd", "auto"],
                "default": "standard",
                "description": "图片质量：standard 标准，hd 高清，auto 自动",
            },
            "style": {
                "type": "string",
                "enum": ["vivid", "natural"],
                "default": "vivid",
                "description": "图片风格：vivid 生动，natural 自然",
            },
        },
        "required": ["prompt"],
    }

    async def execute(
        self,
        prompt: str = "",
        size: str = "1024x1024",
        quality: str = "standard",
        style: str = "vivid",
        **kwargs,
    ) -> ToolResult:
        """生成图片并上传到 imgbb 持久化存储。"""
        if not prompt:
            return ToolResult(success=False, error="Prompt is required")

        try:
            from openai import AsyncOpenAI
            from app.config import settings

            config = settings.image_generation
            api_key = config.api_key
            if not api_key:
                return ToolResult(
                    success=False,
                    error="Image generation API key is not configured",
                )

            if not config.enabled:
                return ToolResult(
                    success=False,
                    error="Image generation is disabled",
                )

            client_kwargs = {"api_key": api_key}
            if config.base_url:
                client_kwargs["base_url"] = config.base_url

            client = AsyncOpenAI(
                **client_kwargs, 
            )

            response = await client.images.generate(
                model=config.model,
                prompt=prompt,
                size=size, 
                quality=quality, 
                style=style, 
                n=1,
            )

            # 获取生存的图片 url
            image_data = response.data[0] 
            original_url = image_data.url
            revised_prompt = image_data.revised_prompt

            if not original_url:
                return ToolResult(
                    success=False,
                    error="Image generation returned no URL",
                )

            # 上传图片到 imgbb 进行持久化存储
            storage_result = await upload_to_imgbb(original_url)

            if storage_result:
                return ToolResult(
                    success=True,
                    data={
                        "prompt": prompt,
                        "url": storage_result["url"],
                        "display_url": storage_result["display_url"],
                        "thumb_url": storage_result.get("thumb_url"),
                        "revised_prompt": revised_prompt,
                        "storage": "imgbb",
                    },
                )
            else:
                logger.warning("imgbb upload failed, using original URL")
                return ToolResult(
                    success=True,
                    data={
                        "prompt": prompt,
                        "url": original_url,
                        "revised_prompt": revised_prompt,
                        "storage": "original",
                    },
                )

        except ImportError:
            return ToolResult(
                success=False,
                error="openai package is not installed. Run: pip install openai",
            )
        except Exception as e:
            logger.exception(f"Image generation failed: {e}")
            return ToolResult(success=False, error=f"Image generation failed: {str(e)}")


__all__ = ["ImageGeneratorTool"]
