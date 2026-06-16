"""
CookAgent 上下文压缩器

负责将较早的对话历史压缩为摘要

核心职责：
1. 判断何时需要执行上下文压缩
2. 通过 LLM 生成历史消息摘要
3. 支持增量式/滚动式压缩
4. 将压缩后的摘要持久化存储到数据库

压缩规则：
- 当未压缩消息数量 >= COMPRESSION_THRESHOLD + RECENT_MESSAGES_LIMIT 时：
  - 从未压缩消息中选取最早的 COMPRESSION_THRESHOLD 条进行压缩
  - 以确保未压缩消息数量始终保持在 [RECENT_MESSAGES_LIMIT, COMPRESSION_THRESHOLD + RECENT_MESSAGES_LIMIT) 区间内
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context

from app.database.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


COMPRESSION_SYSTEM_PROMPT = """
你是 CookAgent 的「对话上下文摘要助手」，专门负责将较早的对话历史压缩为**简洁、结构清晰、信息完整的长期摘要**，用于后续烹饪推荐与饮食决策。你的目标不是复述对话，而是**提炼对后续推荐最有价值的信息**。

【必须重点保留的信息】
1. 用户的明确需求与目标  
   - 想做什么菜 / 想解决什么问题（如“快手晚餐”“减脂餐”“招待朋友”）
   - 使用场景（早餐 / 午餐 / 晚餐 / 聚会 / 健身后等）

2. 与烹饪和饮食强相关的事实信息  
   - 提到的**食材、菜品名称、菜系**
   - 饮食偏好（清淡 / 重口 / 川菜 / 粤菜等）
   - 饮食限制或禁忌（过敏、忌口、素食、减脂、高蛋白等）
   - 人数、预算、时间限制、厨具条件

3. 助手已经给出的**重要结论或建议**  
   - 已推荐过的菜品名称
   - 明确给出的做法思路、搭配建议、替代方案
   - 已被用户认可、采纳或明确否定的建议

【可以弱化或忽略的内容】
- 闲聊、寒暄、情绪性表达
- 重复出现、但不影响决策的信息
- 已被明确推翻或放弃的方案细节

【摘要表达要求】
1. 使用**第三人称客观描述**（如“用户希望…”，“系统已推荐…”）
2. 语言简洁、信息密集、偏事实性总结
3. 允许使用条目化或自然段落，但不要像聊天记录
4. 不要加入任何新的建议或推测，只能基于已有对话
5. 摘要长度根据对话内容灵活调整，确保信息完整即可

【增量摘要规则】
- 如果提供了「之前的对话摘要」，请将**新增对话内容与已有摘要进行融合**
- 输出应是一个**完整的、可直接使用的综合摘要**
- 不要提及“之前摘要 / 新摘要”等元信息

你的输出将作为后续对话的系统上下文，请确保**信息准确、稳定、可长期使用**。
"""


class ContextCompressor:
    """
    使用 LLM 将对话历史压缩为摘要
    压缩策略：
    - 触发条件：
    uncompressed_count >= compression_threshold + recent_messages_limit
    - 压缩范围：
    从未压缩消息中选取最早的 compression_threshold 条消息进行压缩
    - 压缩结果：
    uncompressed_count 减少 compression_threshold
    - 不变性约束：
    每条消息要么已被压缩到摘要中，要么以原始形式保留在上下文中
    """

    MODULE_NAME = "context_compression"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.NORMAL,
        compression_threshold: int = 6,
        recent_messages_limit: int = 10,
        max_messages_per_compression: int = 200,
        history_text_max_len: int = 8096,
        provider: LLMProvider | None = None,
    ):
        """
        初始化 ContextCompressor

        Args:
            llm_type: 使用的 LLM 类型（快速/普通）
            compression_threshold: 每次压缩的消息数量
            recent_messages_limit: 保留的最近未压缩消息数量上限
            max_messages_per_compression: 每次压缩的最大数量
            history_text_max_len: 历史文本最大长度
        """
        self._llm_type = llm_type
        self.compression_threshold = compression_threshold
        self.recent_messages_limit = recent_messages_limit
        self.max_messages_per_compression = max_messages_per_compression
        self.history_text_max_len = history_text_max_len

        self._provider = provider or LLMProvider(settings.llm)
        # 使用跟踪调用器以记录使用统计
        self._llm = self._provider.create_invoker(llm_type, temperature=0.3)

    async def maybe_compress(
        self,
        conversation_id: str,
        repository: ConversationRepository,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        检查是否需要执行上下文压缩，并在满足条件时执行压缩
        这是压缩逻辑的主要入口
        负责：
        - 压缩决策
        - 上下文压缩
        - 压缩结果持久化

        压缩规则：
        - 当 uncompressed_count >= compression_threshold + recent_messages_limit 时：
        - 从未压缩消息中选取最早的 compression_threshold 条消息进行压缩

        Args:
            conversation_id: 会话 ID
            repository: ConversationRepository
            user_id: 用户 ID（可选）

        Returns:
            True 如果压缩操作成功，否则 False 否则返回
        """
        try:
            # 获取消息总数和压缩状态
            total_count = await repository.get_message_count(conversation_id)
            (
                existing_summary,
                compressed_count,
            ) = await repository.get_compressed_summary(conversation_id)

            # 计算未压缩消息数量
            uncompressed_count = total_count - compressed_count

            # 检查是否满足压缩条件
            trigger_threshold = self.compression_threshold + self.recent_messages_limit
            if uncompressed_count < trigger_threshold:
                logger.debug(
                    "Compression not needed for %s: uncompressed=%d, threshold=%d",
                    conversation_id,
                    uncompressed_count,
                    trigger_threshold,
                )
                return False

            logger.info(
                "Triggering compression for %s: total=%d, compressed=%d, uncompressed=%d",
                conversation_id,
                total_count,
                compressed_count,
                uncompressed_count,
            )

            # 获取完整历史记录
            full_history = (
                await repository.get_history(conversation_id, limit=1000) or []
            )
            history_dicts = [
                {"role": h["role"], "content": h["content"]} for h in full_history
            ]

            # 获取待压缩消息（最早的 compression_threshold 条）
            uncompressed_messages = history_dicts[compressed_count:]
            messages_to_compress = uncompressed_messages[: self.compression_threshold]

            if not messages_to_compress:
                return False

            # 执行压缩操作
            new_summary = await self._compress(
                messages_to_compress,
                existing_summary=existing_summary,
                user_id=user_id,
                conversation_id=conversation_id,
            )

            if new_summary:
                # 更新压缩消息数量计数
                new_compressed_count = compressed_count + len(messages_to_compress)

                # 持久化压缩结果
                await repository.update_compressed_summary(
                    conversation_id,
                    new_summary,
                    new_compressed_count,
                )

                logger.info(
                    "Compressed %d messages for %s, new compressed_count=%d",
                    len(messages_to_compress),
                    conversation_id,
                    new_compressed_count,
                )
                return True

            return False

        except Exception as e:
            logger.error(
                "Failed to compress context for %s: %s",
                conversation_id,
                e,
                exc_info=True,
            )
            return False

    async def _compress(
        self,
        messages: List[Dict[str, str]],
        existing_summary: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str:
        """
        将消息压缩为摘要（内部方法）

        如果提供了 existing_summary，则执行增量式压缩，
        将新的消息内容与已有摘要进行融合

        Args:
            messages: 待压缩的消息字典列表
            existing_summary: 可选的已有摘要，用于在其基础上继续构建
            user_id: 用户 ID，用于追踪记录（可选）
            conversation_id: 会话 ID，用于追踪记录（可选）

        Returns:
            压缩后的摘要文本
        """
        if not messages:
            return existing_summary or ""

        # 限制每次参与压缩的消息数量，防止上下文长度溢出
        messages_to_process = messages[-self.max_messages_per_compression :]

        # 格式化消息
        messages_text = self._format_messages_for_compression(messages_to_process)

        # 构建压缩提示
        if existing_summary:
            user_prompt = (
                f"【之前的对话摘要】\n{existing_summary}\n\n"
                f"【新增的对话内容】\n{messages_text}\n\n"
                "请将新增的对话内容与之前的摘要整合，生成一个更新后的综合摘要。"
            )
        else:
            user_prompt = (
                f"【对话内容】\n{messages_text}\n\n请为上述对话生成一个简洁的摘要。"
            )

        try:
            # 调用 LLM 模型进行压缩
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                response = await self._llm.ainvoke(
                    [
                        SystemMessage(content=COMPRESSION_SYSTEM_PROMPT),
                        HumanMessage(content=user_prompt),
                    ]
                )

            content = response.content
            if isinstance(content, str):
                summary = content.strip()
            else:
                # 处理内容可能为列表的情况
                summary = str(content).strip()

            logger.info(
                "Compressed %d messages into summary (len=%d)",
                len(messages_to_process),
                len(summary),
            )
            return summary

        except Exception as e:
            logger.error("Failed to compress messages: %s", e, exc_info=True)
            # 返回已有摘要或空字符串，失败时保持上下文完整性
            return existing_summary or ""

    def _format_messages_for_compression(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """格式化消息为压缩提示文本"""
        parts = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # 截断过长的内容
            if len(content) > self.history_text_max_len:
                content = content[: self.history_text_max_len] + "..."
            role_label = "用户" if role == "user" else "助手"
            parts.append(f"{role_label}: {content}")
        return "\n".join(parts)
