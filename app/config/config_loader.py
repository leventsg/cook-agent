'''
CookAgent 配置加载模块。
负责从 config.yml 加载配置，并与环境变量中的敏感信息进行合并。

环境变量加载机制：

使用 load_dotenv() 将 .env 文件中的配置加载至 os.environ
所有敏感参数均通过 os.getenv() 读取
支持配置继承机制（例如：RERANKER_API_KEY 未配置时，将自动回退使用 LLM_API_KEY）
'''
import os
import yaml

from pathlib import Path
from dotenv import load_dotenv
from typing import Any, Dict

from app.config.llm_config import LLMConfig
from app.config.database_config import DatabaseConfig

load_dotenv()

def _load_config_data() -> Dict[str, Any]:
    """将原始 YAML 配置加载为字典对象"""
    config_path = Path("config.yml")
    if not config_path.exists():
        raise FileNotFoundError("config.yml not found in the project root.")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}
    
def load_llm_config() -> LLMConfig:
    '''
    加载全局 LLM 提供商配置。
    环境变量说明：
    LLM_API_KEY：普通 LLM 的 API Key
    FAST_LLM_API_KEY / LLM_FAST_API_KEY：fast LLM 的 API Key
    VISION_API_KEY：视觉 LLM 的 API Key（未配置时将回退使用 LLM_API_KEY）
    '''
    config_data = _load_config_data()
    llm_root = config_data.get("llm", {}) or {}
    llm_data = dict(llm_root)
    
    #从环境中注入 API 密钥
    normal_api_key = os.getenv("LLM_API_KEY")
    fast_api_key = os.getenv("FAST_LLM_API_KEY")
    vision_api_key = os.getenv("VISION_API_KEY")
    
    normal_data = dict(llm_data.get("normal", {}) or {})
    fast_data = dict(llm_data.get("fast", {}) or {})
    vision_data = dict(llm_data.get("vision", {}) or {})
    
    if normal_api_key:
        normal_data["api_key"] = normal_api_key

    if fast_api_key:
        fast_data["api_key"] = fast_api_key

    if vision_api_key:
        vision_data["api_key"] = vision_api_key
        
    llm_data["normal"] = normal_data
    llm_data["fast"] = fast_data
    llm_data["vision"] = vision_data
    
    return LLMConfig.model_validate(llm_data)

def load_database_config() -> DatabaseConfig:
    ''''''

    
    
