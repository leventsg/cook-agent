from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional

class LLMType(str, Enum):
    FAST = "fast"
    NORMAL = "normal"
    VISION = "vision"

class LLMProfileConfig(BaseModel):
    base_url: Optional[str] = "https://api.siliconflow.cn/v1"
    api_key: Optional[str] = None

    model_names: list[str] = Field(
        default_factory=lambda: ["deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"]
    )

    temperature: float = 1.0
    max_tokens: int = 131072


    def pick_default_model(self) -> str:
        return self.model_names[0]

class FastLLMConfig(LLMProfileConfig):
    """
    Fast LLM 配置（更偏向低延迟/低成本）
    """

class NormalLLMConfig(LLMProfileConfig):
    """
    Normal LLM 配置
    """

class VisionLLMConfig(LLMProfileConfig):
    """
    Vision LLM 配置
    """

class LLMConfig(BaseModel):
    """
    分层 LLM 配置：fast/normal/vision 三类
    """
    fast: FastLLMConfig = Field(default_factory=FastLLMConfig)
    normal: NormalLLMConfig = Field(default_factory=NormalLLMConfig)
    vision: VisionLLMConfig = Field(default_factory=VisionLLMConfig)

    default_type: LLMType = LLMType.NORMAL
    
    def get_profile(self, llm_type: LLMType | str | None) -> LLMProfileConfig:
        if llm_type is None:
            llm_type = self.default_type
        if isinstance(llm_type, str):
            llm_type = LLMType(llm_type)
        if llm_type == LLMType.FAST:
            return self.fast
        elif llm_type == LLMType.VISION:
            return self.vision
        else:
            return self.normal