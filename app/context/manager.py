"""
CookAgent 上下文管理器
负责构建并组装供 LLM 使用的会话上下文

上下文结构：
1. System Message
   基础系统提示词
2. Compressed Summary
   已压缩历史消息的摘要（如果存在）
3. Uncompressed Messages
   尚未压缩的原始消息
   （history[compressed_count:]）
4. Extra System Prompt
   额外上下文信息（例如 RAG 检索得到的内容）

核心不变性约束：
- 每一条历史消息必须满足以下条件之一：
  a) 已包含在 compressed_summary 中（语义得到保留）
  b) 以原始消息形式存在于当前上下文中
- 任何消息都不应被“丢失”
  （既不在摘要中，也不在上下文中的情况是不允许的）

注意：
本模块不会直接调用 LLM
上下文压缩逻辑由 ContextCompressor 负责处理
"""

from sys import path
from typing import Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage


class ContextManager:
    """
    构建并管理供 LLM 使用的会话上下文
    职责：
    - 组合系统提示词、压缩后的历史摘要以及未压缩消息
    - 将消息格式化为 LLM 可接受的输入格式
    - 提供统一的上下文构建接口

    上下文组装过程通过 compressed_count 对历史消息进行切分：
    - history[:compressed_count]
    -> 这些消息已被汇总到 compressed_summary 中
    - history[compressed_count:]
    -> 这些消息保持原始形式，并直接加入上下文
    """

    def __init__(
        self,
        system_prompt: str,
        history_text_max_len: int = 8096,
    ):
        """
        初始化 ContextManager
        
        Args:
            system_prompt: 系统prompt
            history_text_max_len: 每条消息文本的最大长度
        """
        self.system_prompt = system_prompt
        self.history_text_max_len = history_text_max_len

    def build_llm_messages(
        self,
        history: List[Dict[str, str]],
        compressed_count: int = 0,
        compressed_summary: Optional[str] = None,
        extra_prompt: Optional[str] = None,
        user_profile: Optional[str] = None,
        user_instruction: Optional[str] = None,
    ) -> List[BaseMessage]:
        """
        构建 LLM 消息并进行适当的上下文组装。
        
        上下文结构:
        1. 用户个性化上下文 (profile + instruction) - 高优先级
        2. 系统消息 (base prompt)
        3. 带压缩摘要的系统消息 (如果存在)
        4. 未压缩消息 (history[compressed_count:])
        5. 额外系统提示 (例如，RAG 上下文) - 添加在末尾

        Args:
            history: 完整的对话历史，作为包含 'role' 和 'content' 键的字典列表
            compressed_count: 已经被压缩的消息数量 (从历史记录的开始处计算)
            compressed_summary: 压缩消息的摘要 (来自 ContextCompressor)
            extra_system_prompt: 额外的上下文 (例如，RAG 检索到的内容)
            user_profile: 用户的个人信息和偏好
            user_instruction: 用户为 LLM 提供的自定义指令
            
        Returns:
            包含 LLM 消息的 LangMessage 对象的列表
        """
        result: List[BaseMessage] = []
        
        # 添加用户个性化上下文（高优先级，位于 system_prompt 之前）
        if user_profile or user_instruction:
            personalization_prompt = self._format_user_personalization(user_profile, user_instruction)
            result.append(SystemMessage(content=personalization_prompt))

        result.append(SystemMessage(content=self.system_prompt))
        
        # 添加压缩摘要（如果存在）
        if compressed_summary:
            compress_prompt = self._format_compressed_summary(compressed_summary)
            result.append(SystemMessage(content=compress_prompt))
        
        # 获取未压缩消息（尚未总结的消息）
        uncompressed_messages = history[compressed_count:]
        
        # 添加未压缩消息
        for msg in uncompressed_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                result.append(HumanMessage(content=content))
            else:
                result.append(AIMessage(content=content))
        
        # 添加额外系统提示（例如，RAG 上下文）在末尾
        if extra_prompt:
            result.append(AIMessage(content=extra_prompt))
        
        return result

    def build_history_text(
        self,
        history: List[Dict[str, str]],
        compressed_count: int = 0,
        compressed_summary: Optional[str] = None,
        empty_placeholder: str = "(无历史对话)",
    ) -> str:
        """
        构建格式化的历史对话文本
        用于意图识别、查询改写等场景

        Args:
            history: 完整的会话历史
            compressed_count: 已被压缩的消息数量
            compressed_summary: 可选的历史消息压缩摘要
            limit: 可选，未压缩消息数量限制（用于意图识别等场景）
            empty_placeholder: 当历史为空时返回的占位文本

        Returns:
            格式化后的历史对话字符串表示
        """
        # 获取未压缩消息
        uncompressed = history[compressed_count:]
        
        if not uncompressed and not compressed_summary:
            return empty_placeholder
        
        parts: List[str] = []
        
        # 添加压缩摘要（如果存在）
        if compressed_summary:
            parts.append(f"[历史对话摘要]\n{compressed_summary}\n")
        
        # 添加未压缩消息
        if uncompressed:
            parts.append("[最近对话]")
            for msg in uncompressed[:-1]:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if len(content) > self.history_text_max_len:
                    content = content[:self.history_text_max_len] + "..."
                parts.append(f"{role}:\n {content}\n")
            # 添加当前用户查询（最后一个消息）
            last_msg = uncompressed[-1]
            role = last_msg.get("role", "")
            content = last_msg.get("content", "")
            parts.append(f"{role} (**当前问题**):\n {content}\n")
        
        return "\n".join(parts)

    def _format_compressed_summary(self, summary: str) -> str:
        """格式化压缩摘要作为systemprompt"""
        return (
            "以下是之前对话的摘要,请在回答时参考这些背景信息:\n\n"
            f"{summary}"
        )
    
    def _format_user_personalization(
        self, 
        user_profile: Optional[str], 
        user_instruction: Optional[str]
    ) -> str:
        """格式化用户个性化上下文（个人信息和自定义指令）作为systemprompt"""
        parts = []
        
        if user_profile:
            parts.append(f"## 用户个人信息 (User Profile)\n{user_profile}")
        
        if user_instruction:
            parts.append(f"## 用户自定义指令 (User Instruction)\n{user_instruction}")
        
        if not parts:
            return ""
        
        header = "以下是用户的个人信息和自定义指令,请在所有回答中遵循这些设定:\n"
        return header + "\n\n".join(parts)
