"""对话处理相关的数据类"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.tools.web_search import WebSearchResult
from app.vision import VisionAnalysisResult


@dataclass
class ExtraOptions:
    """请求额外选项，用于控制对话处理行为"""

    web_search: bool = False
    # Future extensibility: add more options here
    # deep_reasoning: bool = False
    # multimodal: bool = False

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ExtraOptions":
        if not data:
            return cls()
        return cls(
            web_search=data.get("web_search", False),
        )


@dataclass
class UnifiedSource:
    """
    统一的来源结构，用于前端显示

    Attributes:
        type: 来源类型 - "rag"（知识库）或 "web"
        info: 显示文本，描述来源
    """

    type: str  # "rag" | "web"
    info: str
    url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.type, "info": self.info}
        if self.url:
            result["url"] = self.url
        return result

    @classmethod
    def from_rag_source(cls, source_dict: Dict[str, Any]) -> "UnifiedSource":
        """将 RAG 服务来源转换为统一格式"""
        info = source_dict.get("info") or source_dict.get("title") or "CookAgent 知识库"
        return cls(
            type="rag",
            info=info,
            url=source_dict.get("url"),
        )

    @classmethod
    def from_web_result(cls, result: WebSearchResult) -> "UnifiedSource":
        """将网络搜索结果转换为统一格式"""
        # 如果有标题，使用标题作为显示文本；否则使用来源作为显示文本
        info = f"{result.title}" if result.title else result.source
        return cls(
            type="web",
            info=info,
            url=result.url,
        )


@dataclass
class ChatContext:
    """封装聊天处理过程中所需的全部上下文信息"""

    conv_id: str
    message: str
    user_id: Optional[str]
    options: ExtraOptions
    history: List[Dict]
    history_dicts: List[Dict[str, str]]
    history_text: str
    compressed_summary: Optional[str]
    compressed_count: int

    # 用户个性化上下文
    user_profile: Optional[str] = None
    user_instruction: Optional[str] = None

    # 处理过程中的可变状态
    sources: List[UnifiedSource] = field(default_factory=list)
    thinking_steps: List[str] = field(default_factory=list)
    web_search_context: str = ""
    rag_context: str = ""
    rewritten_query: str = ""

    # 视觉/多模态上下文信息
    images: Optional[List[Dict[str, str]]] = (
        None  # List of {"data": base64, "mime_type": ...}
    )
    vision_result: Optional[VisionAnalysisResult] = None
    vision_context: str = ""  # Context built from vision analysis

    # 时间指标（毫秒）
    thinking_start_time: Optional[float] = None
    thinking_end_time: Optional[float] = None
    answer_start_time: Optional[float] = None
    answer_end_time: Optional[float] = None
