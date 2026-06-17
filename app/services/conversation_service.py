# app/services/conversation_service.py
"""
会话服务
负责协调包含 RAG 与多模态能力的对话处理流程
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.database.document_repository import document_repository
from app.conversation import (
    ChatContext,
    ContextCompressor,
    ContextManager,
    ExtraOptions,
    IntentDetectionResult,
    IntentDetector,
    LLMOrchestrator,
    QueryRewriter,
    SYSTEM_PROMPT,
    UnifiedSource,
    conversation_repository,
)
from app.services.rag_service import rag_service_instance, RetrievalResult
from app.services.user_service import user_service
from app.services.evaluation_service import evaluation_service
from app.tools.web_search import (
    WebSearchDecision,
    web_search_tool,
)
from app.vision import vision_agent
from app.vision.provider import ImageInput

logger = logging.getLogger(__name__)


class ConversationService:
    """
    控制 LLM 与 RAG 的对话流程

    上下文构建策略：
    1. System Message
    2. Compressed Summary
    3. Uncompressed Messages: (history[compressed_count:])
    4. Extra System Prompt

    核心不变性约束：
    每条消息必须满足以下条件之一：
    - 已包含在 compressed_summary 中
    - 以原始消息形式存在于当前上下文中
    """

    # 最近消息限制（不含 compressed_summary 中的消息）
    RECENT_MESSAGES_LIMIT = 20
    # 压缩阈值（每次压缩的消息数量）
    COMPRESSION_THRESHOLD = 10

    def __init__(self):
        """初始化会话服务"""
        self.context_manager = ContextManager(
            system_prompt=SYSTEM_PROMPT,
        )
        self.context_compressor = ContextCompressor(
            llm_type="normal",
            compression_threshold=self.COMPRESSION_THRESHOLD,
            recent_messages_limit=self.RECENT_MESSAGES_LIMIT,
        )
        self.llm_orchestrator = LLMOrchestrator(llm_type="normal")
        self.intent_detector = IntentDetector(llm_type="fast")
        self.query_rewriter = QueryRewriter(llm_type="fast")

    # =========================================================================
    # 主聊天入口点
    # 处理用户消息并生成响应的异步生成器
    # =========================================================================

    async def chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None,
        stream: bool = True,
        extra_options: Optional[Dict[str, Any]] = None,
        images: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        处理聊天消息并生成响应

        生成 SSE 格式的事件：
        - {"type": "vision", "data": {...}} - 视觉分析结果（如果有图片）
        - {"type": "intent", "data": {...}} - 意图检测结果
        - {"type": "thinking", "content": "..."} - 思考步骤
        - {"type": "text", "content": "..."} - 文本块
        - {"type": "sources", "data": [...]} - 来源列表（统一格式）
        - {"type": "done", "conversation_id": "..."} - 完成信号

        Args:
            message: 用户消息
            conversation_id: 可选的现有会话 ID
            user_id: 用户 ID，用于个性化和记忆
            stream: 是否流式输出响应
            extra_options: 可选的功能，如 {"web_search": true}
            images: 可选的图片列表，用于视觉多模态理解
        """
        # 开始记录思考时间
        tmp = time.time()

        # 1.初始化上下文
        ctx = await self._initialize_context(
            message=message,
            conversation_id=conversation_id,
            user_id=user_id,
            extra_options=extra_options,
            images=images,
        )
        ctx.thinking_start_time = tmp

        # 视觉分析
        if ctx.images:
            async for event in self._process_vision(ctx):
                yield event

            # 如果视觉分析结果指示非食物内容，直接返回直接响应
            if ctx.vision_result and not ctx.vision_result.is_food_related:
                # 保存用户消息（包含视觉分析文）
                await self._save_user_message(ctx)
                async for event in self._handle_non_food_image(ctx):
                    yield event
                return

        # 保存用户消息（包含视觉分析上下文）
        await self._save_user_message(ctx)

        # 2.意图检测
        intent_result = await self._detect_intent(ctx)
        yield f"data: {json.dumps({'type': 'intent', 'data': {'need_rag': intent_result.need_rag, 'intent': intent_result.intent.value, 'reason': intent_result.reason}})}\n\n"

        yield self._emit_thinking(ctx, f"🔍 意图识别完成: {intent_result.intent.value}")
        yield self._emit_thinking(
            ctx, f"📋 是否需要检索: {'是' if intent_result.need_rag else '否'}"
        )
        yield self._emit_thinking(ctx, f"💭 判断依据: {intent_result.reason}")

        logger.info(
            "chat route need_rag=%s intent=%s reason=%s history_len=%d images=%d",
            intent_result.need_rag,
            intent_result.intent.value,
            intent_result.reason[:120],
            len(ctx.history),
            len(ctx.images) if ctx.images else 0,
        )

        # 3.网络搜索（如果启用）
        web_search_decision: Optional[WebSearchDecision] = None
        if ctx.options.web_search:
            web_search_decision, events = await self._process_web_search_decision(ctx)
            for event in events:
                yield event

            # 如果置信度高，则执行主动网络搜索
            if web_search_decision and web_search_decision.should_search:
                events = await self._execute_web_search(ctx, web_search_decision)
                for event in events:
                    yield event

        # 4.RAG 检索（如果需要）
        if intent_result.need_rag:
            async for event in self._prepare_rag_context(
                ctx=ctx,
                web_search_decision=web_search_decision,
            ):
                yield event
        else:
            yield self._emit_thinking(ctx, "💬 无需检索知识库，直接回答...")

        # 5.统一输出 - 源数据和响应生成
        # 始终发出源数据（如果没有收集到源数据，则可能是一个空列表）
        sources_data = [s.to_dict() for s in ctx.sources]
        yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

        # 使用所有收集到的上下文生成响应
        yield self._emit_thinking(ctx, "🤖 开始生成回答...")

        # 结束思考阶段，开始回答阶段
        ctx.thinking_end_time = time.time()
        ctx.answer_start_time = time.time()

        full_response = ""
        async for chunk in self._generate_response(ctx):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"

        # 结束回答阶段
        ctx.answer_end_time = time.time()

        # 6.保存完整响应
        await self._save_response(ctx, full_response, intent_result)
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': ctx.conv_id})}\n\n"

        # 触发异步上下文压缩任务
        asyncio.create_task(
            self.context_compressor.maybe_compress(
                ctx.conv_id, conversation_repository, user_id=ctx.user_id
            )
        )

    # =========================================================================
    # 1.上下文初始化
    # =========================================================================

    async def _initialize_context(
        self,
        message: str,
        conversation_id: Optional[str],
        user_id: Optional[str],
        extra_options: Optional[Dict[str, Any]],
        images: Optional[List[Dict[str, str]]] = None,
    ) -> ChatContext:
        """
        初始化聊天上下文，包含对话数据。

        注意：此处不会保存用户消息
        如果提供了图片，用户消息将在视觉分析完成后再保存
        以便将视觉分析得到的上下文信息一并写入消息内容中
        """
        options = ExtraOptions.from_dict(extra_options)

        # 获取或创建对话
        conversation = await conversation_repository.get_or_create(
            conversation_id, user_id=user_id
        )
        conv_id = str(conversation.id)

        # 注意：此处不会保存用户消息
        # 以便将视觉分析得到的上下文信息一并写入消息内容中

        # 加载历史消息（在添加新消息之前）
        history = await conversation_repository.get_history(conv_id, limit=100) or []
        (
            compressed_summary,
            compressed_count,
        ) = await conversation_repository.get_compressed_summary(conv_id)

        # 构建历史消息结构（将来源信息添加到assistant消息内容）
        history_dicts = [
            {
                "role": h["role"],
                "content": self._format_content_with_sources(
                    h["content"], h.get("sources")
                )
                if h["role"] == "assistant"
                else h["content"],
            }
            for h in history
        ]
        history_text = self.context_manager.build_history_text(
            history=history_dicts,
            compressed_count=compressed_count,
            compressed_summary=compressed_summary,
        )

        # 加载用户个性化上下文
        user_profile = None
        user_instruction = None
        if user_id:
            user_data = await user_service.get_user_by_id(user_id)
            if user_data:
                user_profile = user_data.profile
                user_instruction = user_data.user_instruction

        return ChatContext(
            conv_id=conv_id,
            message=message,
            user_id=user_id,
            options=options,
            history=history,
            history_dicts=history_dicts,
            history_text=history_text,
            compressed_summary=compressed_summary,
            compressed_count=compressed_count,
            user_profile=user_profile,
            user_instruction=user_instruction,
            images=images,
        )

    async def _save_user_message(self, ctx: ChatContext) -> None:
        """
        保存用户消息到数据库，包含视觉上下文（如果有）

        该方法会在视觉分析完成后被调用，
        以便将视觉分析得到的上下文信息写入消息内容中
        这样后续对话消息便能够从会话历史中获取并利用图像分析结果
        """
        content = ctx.message

        sources = None
        if ctx.images:
            # 在 sources 字段中保存图片 URL，便于页面刷新后恢复访问
            image_sources = []
            for i, img in enumerate(ctx.images):
                # 上传图片到 imgbb 以持久化 URL
                from app.utils.image_storage import upload_to_imgbb
                try:
                    upload_result = await upload_to_imgbb(
                        img["data"],
                        img.get("mime_type", "image/jpeg"),
                    )
                    if upload_result:
                        image_sources.append({
                            "type": "image",
                            "url": upload_result.get("url"),
                            "display_url": upload_result.get("display_url"),
                            "thumb_url": upload_result.get("thumb_url"),
                        })
                except Exception as e:
                    logger.warning(f"Failed to upload image {i} to imgbb: {e}")
            if image_sources:
                sources = image_sources

        # 保存消息到数据库
        await conversation_repository.add_message(
            conversation_id=ctx.conv_id,
            role="user",
            content=content,
            sources=sources,
        )
        
        # 更新当前请求上下文的历史消息
        new_message = {"role": "user", "content": content}
        ctx.history.append(new_message)
        ctx.history_dicts.append(new_message)

        # 重新构建历史消息文本
        ctx.history_text = self.context_manager.build_history_text(
            history=ctx.history_dicts,
            compressed_count=ctx.compressed_count,
            compressed_summary=ctx.compressed_summary,
        )

    # =========================================================================
    # Phase 2: Intent Detection
    # =========================================================================

    async def _detect_intent(self, ctx: ChatContext) -> IntentDetectionResult:
        """从历史消息和用户查询中检测意图"""
        history_text = ctx.history_text
        if ctx.vision_context:
            history_text = f"{history_text}\n\n{ctx.vision_context}"
        return await self.intent_detector.detect(
            history_text,
            user_id=ctx.user_id,
            conversation_id=ctx.conv_id,
        )

    # =========================================================================
    # Vision Processing
    # =========================================================================

    async def _process_vision(self, ctx: ChatContext) -> AsyncGenerator[str, None]:
        """
        使用视觉模型处理图像
        以 SSE 事件的形式持续输出视觉分析进度
        """
        if not ctx.images:
            return

        yield self._emit_thinking(
            ctx, f"📷 检测到 {len(ctx.images)} 张图片，正在分析..."
        )

        try:
            # 将图像数据转换为 ImageInput 对象列表
            image_inputs = []
            for img_data in ctx.images:
                image_inputs.append(
                    ImageInput.from_base64(
                        data=img_data["data"],
                        mime_type=img_data.get("mime_type", "image/jpeg"),
                    )
                )

            # 使用视觉智能体分析图像
            vision_result = await vision_agent.analyze(
                images=image_inputs,
                user_query=ctx.message,
                history_context=ctx.history_text[:2000] if ctx.history_text else "",
                user_id=ctx.user_id,
                conversation_id=ctx.conv_id,
            )

            # 存储视觉分析结果到上下文
            ctx.vision_result = vision_result

            # 发送视觉分析结果事件
            yield f"data: {json.dumps({'type': 'vision', 'data': vision_result.to_dict()})}\n\n"

            # 记录并发送思考事件
            yield self._emit_thinking(
                ctx,
                f"📷 图片分析完成: {'与食物相关' if vision_result.is_food_related else '与食物无关'}",
            )
            yield self._emit_thinking(
                ctx, f"📷 识别内容: {vision_result.description[:100]}"
            )

            if vision_result.is_food_related:
                # 为 RAG 检索构建上下文
                ctx.vision_context = vision_agent.build_context_for_rag(
                    vision_result, ctx.message
                )
                yield self._emit_thinking(ctx, f"📷 意图: {vision_result.intent.value}")

            logger.info(
                "Vision analysis: food_related=%s, intent=%s, confidence=%.2f",
                vision_result.is_food_related,
                vision_result.intent.value,
                vision_result.confidence,
            )

        except Exception as e:
            logger.error(f"Vision processing error: {e}", exc_info=True)
            yield self._emit_thinking(ctx, f"📷 图片分析出错: {str(e)[:50]}")

    async def _handle_non_food_image(
        self, ctx: ChatContext
    ) -> AsyncGenerator[str, None]:
        """
        处理与食物无关的图片并直接生成回复

        对于非烹饪相关内容，
        将直接返回结果，不再进入后续标准对话处理流程
        """
        if not ctx.vision_result or not ctx.vision_result.direct_response:
            return

        yield self._emit_thinking(ctx, "💬 图片与烹饪无关，直接回复...")

        # 结束思考阶段
        ctx.thinking_end_time = time.time()
        ctx.answer_start_time = time.time()

        # 直接回复
        response = ctx.vision_result.direct_response
        yield f"data: {json.dumps({'type': 'text', 'content': response})}\n\n"

        ctx.answer_end_time = time.time()

        # 发送空的来源事件（未使用 RAG 检索）
        yield f"data: {json.dumps({'type': 'sources', 'data': []})}\n\n"

        # 保存回复和视觉意图到数据库
        await conversation_repository.add_message(
            conversation_id=ctx.conv_id,
            role="assistant",
            content=response,
            sources=None,
            intent=ctx.vision_result.intent.value,
            thinking=ctx.thinking_steps,
            thinking_duration_ms=int(
                (ctx.thinking_end_time - ctx.thinking_start_time) * 1000
            )
            if ctx.thinking_start_time and ctx.thinking_end_time
            else None,
            answer_duration_ms=int((ctx.answer_end_time - ctx.answer_start_time) * 1000)
            if ctx.answer_start_time and ctx.answer_end_time
            else None,
        )

        yield f"data: {json.dumps({'type': 'done', 'conversation_id': ctx.conv_id})}\n\n"

    # =========================================================================
    # Phase 3: Web Search Processing
    # =========================================================================

    async def _process_web_search_decision(
        self,
        ctx: ChatContext,
    ) -> tuple[Optional[WebSearchDecision], List[str]]:
        """
        处理网络搜索决策。

        Returns:
            (决策, 要生成的 SSE 事件列表)
        """
        events = []
        events.append(self._emit_thinking(ctx, "🌐 正在判断是否需要 Web 搜索..."))

        decision = await web_search_tool.decide_search(
            query=ctx.message,
            document_summary=document_repository.get_metadata_options(
                user_id=ctx.user_id
            ),
            history_text=ctx.history_text,
            user_id=ctx.user_id,
            conversation_id=ctx.conv_id,
        )

        events.append(
            self._emit_thinking(
                ctx,
                f"🌐 搜索关键词: {decision.search_params.query if decision.search_params else 'None'}，搜索置信度: {decision.confidence}/10，判断: {decision.reason}",
            )
        )

        return decision, events

    async def _execute_web_search(
        self,
        ctx: ChatContext,
        decision: WebSearchDecision,
    ) -> List[str]:
        """
        执行网络搜索并更新上下文。

        Returns:
            要生成的 SSE 事件列表
        """
        events = []

        if not decision.search_params:
            return events

        events.append(self._emit_thinking(ctx, "🌐 正在执行 Web 搜索..."))

        search_results = await web_search_tool.execute_search(decision.search_params)

        if search_results:
            events.append(
                self._emit_thinking(
                    ctx, f"🌐 Web 搜索找到 {len(search_results)} 条结果"
                )
            )

            # Log top results
            for i, result in enumerate(search_results[:3]):
                events.append(
                    self._emit_thinking(
                        ctx, f"  🔗 [{i + 1}] {result.title} ({result.source})"
                    )
                )
            if len(search_results) > 3:
                events.append(
                    self._emit_thinking(
                        ctx, f"  ...还有 {len(search_results) - 3} 条结果"
                    )
                )

            # 更新上下文
            ctx.web_search_context = web_search_tool.format_results_for_context(
                search_results
            )
            ctx.sources.extend(
                [UnifiedSource.from_web_result(r) for r in search_results]
            )
        else:
            events.append(self._emit_thinking(ctx, "🌐 Web 搜索未找到相关结果"))

        return events

    # =========================================================================
    # Phase 4: RAG Context Preparation
    # =========================================================================

    async def _prepare_rag_context(
        self,
        ctx: ChatContext,
        web_search_decision: Optional[WebSearchDecision],
    ) -> AsyncGenerator[str, None]:
        """
        准备用于 RAG 上下文。

        该方法仅负责准备数据（sources、rag_context、rewritten_query）
        不会输出 sources，
        也不会生成最终回复内容

        Yields:
            仅产生 SSE 类型的 Thinking 事件
        """
        yield self._emit_thinking(ctx, "⏳ 正在结合对话历史重写查询语句...")

        try:
            # query重写
            ctx.rewritten_query = await self.query_rewriter.rewrite(
                current_query=ctx.message,
                history_text=ctx.history_text,
                user_id=ctx.user_id,
                conversation_id=ctx.conv_id,
            )
            yield self._emit_thinking(ctx, f"✍️ 重写后的查询语句: {ctx.rewritten_query}")

            # RAG 检索
            yield self._emit_thinking(ctx, "🔎 正在从 CookAgent 知识库中检索相关资料...")

            retrieval_result = await rag_service_instance.retrieve(
                ctx.rewritten_query,
                skip_rewrite=True,
                user_id=ctx.user_id,
                conversation_id=ctx.conv_id,
            )

            # 处理检索结果
            async for event in self._process_retrieval_results(
                ctx=ctx,
                retrieval_result=retrieval_result,
                web_search_decision=web_search_decision,
            ):
                yield event

        except Exception as e:
            logger.error(f"RAG error: {e}", exc_info=True)
            yield self._emit_thinking(
                ctx, f"❌ 检索遇到问题: {str(e)[:50]}，改为直接回答。"
            )

    async def _process_retrieval_results(
        self,
        ctx: ChatContext,
        retrieval_result: RetrievalResult,
        web_search_decision: Optional[WebSearchDecision],
    ) -> AsyncGenerator[str, None]:
        """
        处理 RAG 检索结果，并在需要时执行降级网络搜索

        当 RAG 检索结果不足或未命中时，
        负责触发并处理备用的网络搜索流程
        """
        doc_count = len(retrieval_result.documents)

        # 转换 RAG 源为统一格式
        if retrieval_result.sources:
            for source in retrieval_result.sources:
                ctx.sources.append(UnifiedSource.from_rag_source(source))

        # 存储 RAG 上下文
        ctx.rag_context = retrieval_result.context

        if doc_count:
            yield self._emit_thinking(ctx, f"📚 检索到 {doc_count} 条相关资料")

            # Log top documents
            for i, doc in enumerate(retrieval_result.documents[:3]):
                doc_title = doc.metadata.get("dish_name", "")
                doc_difficulty = doc.metadata.get("difficulty", "")
                doc_category = doc.metadata.get("category", "")
                doc_preview = doc.page_content[:200].replace("\n", " ")
                if len(doc.page_content) > 200:
                    doc_preview += "..."
                yield self._emit_thinking(
                    ctx,
                    f"  📄 [{i + 1}] {doc_title} (难度: {doc_difficulty}, 分类: {doc_category}): {doc_preview}",
                )

            if doc_count > 3:
                yield self._emit_thinking(ctx, f"  ...还有 {doc_count - 3} 条资料")
        else:
            yield self._emit_thinking(ctx, "⚠️ 知识库里没有找到直接相关的资料")

            # 降级到网络搜索如果 RAG 检索结果不足
            should_fallback = (
                ctx.options.web_search
                and web_search_decision
                and web_search_decision.search_params
                and not ctx.web_search_context 
            )

            if should_fallback and web_search_decision:
                events = await self._execute_web_search(ctx, web_search_decision)
                for event in events:
                    yield event

    async def _generate_response(
        self,
        ctx: ChatContext,
    ) -> AsyncGenerator[str, None]:
        """
        生成 LLM 响应

        Yields:
            SSE 格式的原始文本块
        """
        # 构建上下文prompt时，将视觉上下文、RAG 上下文和网络搜索上下文结合起来
        context_prompt = self._build_combined_context_prompt(
            rag_context=ctx.rag_context,
            web_context=ctx.web_search_context,
            rewritten_query=ctx.rewritten_query,
            vision_context=ctx.vision_context,
        )

        # 构建 LLM 输入消息，确保包含所有必要的上下文信息
        messages_for_llm = self.context_manager.build_llm_messages(
            ctx.history_dicts,
            compressed_count=ctx.compressed_count,
            compressed_summary=ctx.compressed_summary,
            extra_prompt=context_prompt,
            user_profile=ctx.user_profile,
            user_instruction=ctx.user_instruction,
        )

        async for chunk in self.llm_orchestrator.stream(
            messages_for_llm,
            user_id=ctx.user_id,
            conversation_id=ctx.conv_id,
        ):
            yield chunk

    # =========================================================================
    # 5. 保存响应
    # =========================================================================

    async def _save_response(
        self,
        ctx: ChatContext,
        full_response: str,
        intent_result: IntentDetectionResult,
    ) -> None:
        """保存LLM响应到数据库并安排评估."""
        sources_data = [s.to_dict() for s in ctx.sources] if ctx.sources else None

        # 计算思考和回答阶段的持续时间（毫秒）
        thinking_duration_ms = None
        answer_duration_ms = None

        if ctx.thinking_start_time and ctx.thinking_end_time:
            thinking_duration_ms = int(
                (ctx.thinking_end_time - ctx.thinking_start_time) * 1000
            )

        if ctx.answer_start_time and ctx.answer_end_time:
            answer_duration_ms = int(
                (ctx.answer_end_time - ctx.answer_start_time) * 1000
            )

        # 保存对话消息到数据库
        message = await conversation_repository.add_message(
            conversation_id=ctx.conv_id,
            role="assistant",
            content=full_response,
            sources=sources_data,
            intent=intent_result.intent.value,
            thinking=ctx.thinking_steps if ctx.thinking_steps else None,
            thinking_duration_ms=thinking_duration_ms,
            answer_duration_ms=answer_duration_ms,
        )

        # RAG 评估
        if intent_result.need_rag and ctx.rag_context and message:
            asyncio.create_task(
                evaluation_service.schedule_evaluation(
                    message_id=str(message.id),
                    conversation_id=ctx.conv_id,
                    query=ctx.message,
                    context=ctx.rag_context,
                    response=full_response,
                    rewritten_query=ctx.rewritten_query,
                    user_id=ctx.user_id,
                )
            )

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _emit_thinking(self, ctx: ChatContext, step: str) -> str:
        """辅助发送 Thinking 事件并同步更新上下文状态"""
        ctx.thinking_steps.append(step)
        return f"data: {json.dumps({'type': 'thinking', 'content': step})}\n\n"

    def _build_combined_context_prompt(
        self,
        rag_context: str,
        web_context: str,
        rewritten_query: str,
        vision_context: str = "",
    ) -> str:
        """
        构建结合视觉、RAG 和网络搜索结果的上下文 prompt。
        清晰地区分不同的上下文来源。
        """
        parts = []

        if vision_context.strip():
            parts.append(
                "【图片工具分析结果】\n"
                "用户上传了图片，以下是工具分析结果，请参考回答：\n"
                f"{vision_context.strip()}\n"
            )

        if rewritten_query.strip():
            parts.append(f"【重写后的检索语句】\n{rewritten_query}\n")

        if rag_context.strip():
            parts.append(
                "【本地知识库工具分析结果】\n"
                "下面是 CookAgent 知识库中与当前问题最相关的资料，请参考回答：\n"
                f"{rag_context.strip()}\n"
            )

        if web_context.strip():
            parts.append(
                "【互联网搜索工具分析结果】\n"
                "下面是从互联网搜索获取的补充信息（请注意甄别信息可靠性）：\n"
                f"{web_context.strip()}\n"
            )

        return "\n".join(parts)

    def _format_content_with_sources(
        self,
        content: str,
        sources: Optional[List[Dict[str, Any]]],
    ) -> str:
        """
        为 Assistant 消息内容附加引用来源信息

        在构建 LLM 上下文时，会以简洁且结构化的方式附加来源信息，
        使模型能够了解之前回答所参考的资料来源

        Args:
            content: Assistant 的回复内容
            sources: 可选的来源列表，每个来源包含 type、info、url 等字段

        Returns:
            带有附加来源信息的内容字符串
        """
        if not sources:
            return content

        source_lines = []
        for src in sources:  # Limit to first 5
            src_type = src.get("type", "")
            src_info = src.get("info", "")[:8096]  # Truncate long info

            if src_type == "rag":
                source_lines.append(f"知识库: {src_info}")
            elif src_type == "web":
                src_url = src.get("url", "")
                source_lines.append(f"网络搜索: {src_info}({src_url})")
            else:
                source_lines.append(src_info)

        if not source_lines:
            return content

        sources_summary = "、".join(source_lines)

        return f"{content}\n\n[参考来源: {sources_summary}]"

    # =========================================================================
    # Other Public Methods
    # =========================================================================

    async def get_conversation_history(
        self, conversation_id: str
    ) -> Optional[List[Dict]]:
        """获取对话历史记录"""
        return await conversation_repository.get_history(conversation_id)

    async def clear_conversation(self, conversation_id: str) -> bool:
        """删除对话历史记录"""
        return await conversation_repository.clear(conversation_id)

    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """
        获取所有对话历史记录（用于 UI 切换）。

        Returns:
            (对话列表,总记录数）
        """
        return await conversation_repository.list_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """更新会话标题"""
        return await conversation_repository.update_title(conversation_id, title)


conversation_service = ConversationService()
