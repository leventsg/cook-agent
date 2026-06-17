"""
图片存储工具模块

提供将图片上传至外部存储服务（imgbb）的相关工具

从 image_generator.py 中拆分出来，
以便在整个应用中复用
"""
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def upload_to_imgbb(
    image_data: str,
    mime_type: str = "image/jpeg",
) -> Optional[dict]:
    """
    将 base64 图像数据上传到 imgbb 以持久化存储

    Args:
        image_data: Base64 编码的图像数据

    Returns:
        包含 URL、显示 URL、删除 URL 和缩略图 URL 的字典
        或在上传失败时返回 None
    """
    storage_config = settings.image_storage
    if not storage_config.enabled:
        logger.info("Image storage is disabled, skipping upload")
        return None

    if not storage_config.api_key:
        logger.warning("imgbb API key is not configured, skipping upload")
        return None

    try:
        params = {
            "key": storage_config.api_key,
            "image": image_data,
        }
        if storage_config.expiration:
            params["expiration"] = str(storage_config.expiration)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                storage_config.upload_url,
                data=params,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("success"):
                return {
                    "url": result["data"]["url"],
                    "display_url": result["data"]["display_url"],
                    "delete_url": result["data"]["delete_url"],
                    "thumb_url": result["data"].get("thumb", {}).get("url"),
                }
            else:
                logger.error(f"imgbb upload failed: {result}")
                return None

    except Exception as e:
        logger.exception(f"Failed to upload image to imgbb: {e}")
        return None


__all__ = ["upload_to_imgbb"]
