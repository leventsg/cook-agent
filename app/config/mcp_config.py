from typing import Optional
from pydantic import BaseModel

class MCPServerConfig(BaseModel):
    """
    MCP 服务配置。
    """
    enabled: bool = True

class MCPConfig(BaseModel):
    """
    MCP 配置。
    """
    # 高德地图apikey
    amap_api_key: Optional[str] = None  # Loaded from .env (AMAP_API_KEY)
    amap: MCPServerConfig = MCPServerConfig()