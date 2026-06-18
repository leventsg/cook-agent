"""
Agent 模块类型定义

Agent 模块是独立的对话处理系统，与现有 ConversationService 完全分离。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class AgentChunkType(str, Enum):
    """Agent 输出块类型"""

    CONTENT = "content"  # 文本内容
    TRACE = "trace"  # 执行轨迹
    TOOL_CALL = "tool_call"  # Tool 调用
    TOOL_RESULT = "tool_result"  # Tool 执行结果
    VISION = "vision"  # 图片分析结果
    ERROR = "error"  # 错误信息
    DONE = "done"  # 完成信号


@dataclass
class AgentChunk:
    """Agent 输出块"""

    type: AgentChunkType
    data: Any


@dataclass
class ToolCallInfo:
    """Tool 调用信息"""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolResultInfo:
    """Tool 执行结果信息"""

    tool_call_id: str
    name: str
    success: bool
    result: Any
    error: str | None = None


@dataclass
class TraceStep:
    """执行轨迹步骤"""

    iteration: int
    action: Literal["tool_call", "tool_result", "finish", "error", "subagent_output"]
    tool_calls: list[dict] | None = None
    content: str | None = None
    error: str | None = None
    source: Literal["agent", "subagent"] = "agent"
    subagent_name: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ToolResult(BaseModel):
    """Tool 执行结果"""

    success: bool
    data: Any = None
    error: str | None = None

@dataclass
class AgentContext:
    """Agent 执行所需的完整上下文"""

    system_prompt: str  # Agent 系统提示词
    user_id: str | None = None  # 用户 ID（用于 LLM 调用跟踪）
    session_id: str | None = None  # Session ID（用于 LLM 调用跟踪）
    user_profile: str | None = None  # 用户画像
    user_instruction: str | None = None  # 用户长期指令
    history_summary: str | None = None  # 历史摘要（压缩后）
    recent_messages: list[dict] = field(default_factory=list)  # 近期消息
    available_tools: list[dict] = field(default_factory=list)  # 可用 Tool schema
    current_message: str = ""  # 当前用户消息
    images: list[dict] | None = None  # [{data, mime_type, url}]
    vision_analysis: dict | None = None  # Vision analysis result
    vision_tool_call_id: str | None = None  # Vision tool call id


@dataclass
class AgentConfig:
    """Agent 配置"""

    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)  # Tool 名称列表
    max_iterations: int = 32


@dataclass
class AgentSession:
    """Agent 会话数据"""

    id: str
    user_id: str
    agent_name: str
    created_at: datetime
    updated_at: datetime
    compressed_summary: str | None = None
    compressed_count: int = 0


@dataclass
class AgentMessage:
    """Agent 消息数据"""

    id: str
    session_id: str
    role: Literal["user", "assistant", "tool"]
    content: str
    created_at: datetime
    trace: list[dict] | None = None  # 执行轨迹（仅 assistant）
    tool_calls: list[dict] | None = None  # Tool/Skill 调用记录
    tool_call_id: str | None = None
    tool_name: str | None = None
