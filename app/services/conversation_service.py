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
    Manages conversations with LLM and RAG integration.

    Context building strategy:
    1. System Message - Base system prompt
    2. Compressed Summary - Summary of compressed messages (if exists)
    3. Uncompressed Messages - Original messages not yet compressed (history[compressed_count:])
    4. Extra System Prompt - RAG context if applicable

    Key invariant: Every message is either in compressed_summary or in context as original.
    """

    # Number of recent uncompressed messages to keep before considering compression
    RECENT_MESSAGES_LIMIT = 20
    # Number of messages to compress each time
    COMPRESSION_THRESHOLD = 10

    def __init__(self):
        """Initialize the conversation service with modular components."""
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
    # Main Chat Entry Point
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
        Process a chat message and generate a response.

        Yields SSE-formatted events:
        - {"type": "vision", "data": {...}} - Vision analysis result (if images provided)
        - {"type": "intent", "data": {...}} - Detected intent
        - {"type": "thinking", "content": "..."} - Thinking step
        - {"type": "text", "content": "..."} - Text chunk
        - {"type": "sources", "data": [...]} - Sources (unified format)
        - {"type": "done", "conversation_id": "..."} - Completion signal

        Args:
            message: The user's message
            conversation_id: Optional existing conversation ID
            user_id: Optional user ID for personalization and memory
            stream: Whether to stream the response
            extra_options: Optional features like {"web_search": true}
            images: Optional list of images for multimodal understanding
        """
        # Start timing thinking phase
        tmp = time.time()

        # Phase 1: Initialize context
        ctx = await self._initialize_context(
            message=message,
            conversation_id=conversation_id,
            user_id=user_id,
            extra_options=extra_options,
            images=images,
        )
        ctx.thinking_start_time = tmp

        # Phase 1.5: Vision Analysis (if images provided)
        if ctx.images:
            async for event in self._process_vision(ctx):
                yield event

            # If vision result indicates non-food content, return direct response
            if ctx.vision_result and not ctx.vision_result.is_food_related:
                # Save user message before returning (include vision context)
                await self._save_user_message(ctx)
                async for event in self._handle_non_food_image(ctx):
                    yield event
                return

        # Save user message (with vision context if available)
        await self._save_user_message(ctx)

        # Phase 2: Intent Detection
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

        # Phase 3: Web Search (if enabled and proactive)
        web_search_decision: Optional[WebSearchDecision] = None
        if ctx.options.web_search:
            web_search_decision, events = await self._process_web_search_decision(ctx)
            for event in events:
                yield event

            # Execute proactive web search if confidence is high
            if web_search_decision and web_search_decision.should_search:
                events = await self._execute_web_search(ctx, web_search_decision)
                for event in events:
                    yield event

        # Phase 4: RAG Retrieval (if needed) - Only prepare data, don't generate response
        if intent_result.need_rag:
            async for event in self._prepare_rag_context(
                ctx=ctx,
                web_search_decision=web_search_decision,
            ):
                yield event
        else:
            # No RAG needed, just emit thinking
            yield self._emit_thinking(ctx, "💬 无需检索知识库，直接回答...")

        # Phase 5: Unified output - Sources and Response Generation
        # Always emit sources (may be empty list if no sources collected)
        sources_data = [s.to_dict() for s in ctx.sources]
        yield f"data: {json.dumps({'type': 'sources', 'data': sources_data})}\n\n"

        # Generate response with all collected context
        yield self._emit_thinking(ctx, "🤖 开始生成回答...")

        # End thinking phase, start answer phase
        ctx.thinking_end_time = time.time()
        ctx.answer_start_time = time.time()

        full_response = ""
        async for chunk in self._generate_response(ctx):
            full_response += chunk
            yield f"data: {json.dumps({'type': 'text', 'content': chunk})}\n\n"

        # End answer phase
        ctx.answer_end_time = time.time()

        # Phase 6: Save response and complete
        await self._save_response(ctx, full_response, intent_result)
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': ctx.conv_id})}\n\n"

        # Trigger async context compression
        asyncio.create_task(
            self.context_compressor.maybe_compress(
                ctx.conv_id, conversation_repository, user_id=ctx.user_id
            )
        )

    # =========================================================================
    # Phase 1: Context Initialization
    # =========================================================================

    async def _initialize_context(
        self,
        message: str,
        conversation_id: Optional[str],
        user_id: Optional[str],
        extra_options: Optional[Dict[str, Any]],
        images: Optional[List[Dict[str, str]]] = None,
    ) -> ChatContext:
        """Initialize chat context with conversation data.

        Note: User message is NOT saved here. It will be saved after vision
        analysis completes (if images are provided) so that the vision context
        can be included in the message content.
        """
        options = ExtraOptions.from_dict(extra_options)

        # Get or create conversation
        conversation = await conversation_repository.get_or_create(
            conversation_id, user_id=user_id
        )
        conv_id = str(conversation.id)

        # NOTE: User message will be saved later after vision analysis
        # to include vision context in the message content

        # Load history (before adding new message)
        history = await conversation_repository.get_history(conv_id, limit=100) or []
        (
            compressed_summary,
            compressed_count,
        ) = await conversation_repository.get_compressed_summary(conv_id)

        # Build history structures (append sources to assistant content)
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

        # Load user personalization context
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
        Save user message to database with vision context if available.

        This method is called after vision analysis completes so that
        the vision context can be included in the message content.
        This ensures that follow-up messages can access the image analysis
        results from conversation history.
        """
        # Build message content with vision context
        content = ctx.message

        # Build sources with image URLs for persistence
        sources = None
        if ctx.images:
            # Store image URLs in sources field for retrieval after refresh
            image_sources = []
            for i, img in enumerate(ctx.images):
                # Upload to imgbb for persistent URL
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

        # Save to database
        await conversation_repository.add_message(
            conversation_id=ctx.conv_id,
            role="user",
            content=content,
            sources=sources,
        )

        # Update history with the new message (for current request context)
        new_message = {"role": "user", "content": content}
        ctx.history.append(new_message)
        ctx.history_dicts.append(new_message)

        # Rebuild history text to include the new message
        ctx.history_text = self.context_manager.build_history_text(
            history=ctx.history_dicts,
            compressed_count=ctx.compressed_count,
            compressed_summary=ctx.compressed_summary,
        )

    # =========================================================================
    # Phase 2: Intent Detection
    # =========================================================================

    async def _detect_intent(self, ctx: ChatContext) -> IntentDetectionResult:
        """Detect user intent from message and history."""
        # If we have vision context, include it in intent detection
        history_text = ctx.history_text
        if ctx.vision_context:
            history_text = f"{history_text}\n\n{ctx.vision_context}"
        return await self.intent_detector.detect(
            history_text,
            user_id=ctx.user_id,
            conversation_id=ctx.conv_id,
        )

    # =========================================================================
    # Phase 1.5: Vision Processing
    # =========================================================================

    async def _process_vision(self, ctx: ChatContext) -> AsyncGenerator[str, None]:
        """
        Process images using vision model.

        Yields SSE events for vision analysis progress.
        """
        if not ctx.images:
            return

        yield self._emit_thinking(
            ctx, f"📷 检测到 {len(ctx.images)} 张图片，正在分析..."
        )

        try:
            # Convert image data to ImageInput objects
            image_inputs = []
            for img_data in ctx.images:
                image_inputs.append(
                    ImageInput.from_base64(
                        data=img_data["data"],
                        mime_type=img_data.get("mime_type", "image/jpeg"),
                    )
                )

            # Analyze images with vision agent
            vision_result = await vision_agent.analyze(
                images=image_inputs,
                user_query=ctx.message,
                history_context=ctx.history_text[:2000] if ctx.history_text else "",
                user_id=ctx.user_id,
                conversation_id=ctx.conv_id,
            )

            # Store result in context
            ctx.vision_result = vision_result

            # Emit vision result event
            yield f"data: {json.dumps({'type': 'vision', 'data': vision_result.to_dict()})}\n\n"

            # Log and emit thinking
            yield self._emit_thinking(
                ctx,
                f"📷 图片分析完成: {'与食物相关' if vision_result.is_food_related else '与食物无关'}",
            )
            yield self._emit_thinking(
                ctx, f"📷 识别内容: {vision_result.description[:100]}"
            )

            if vision_result.is_food_related:
                # Build context for RAG pipeline
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
            # Continue without vision context on error

    async def _handle_non_food_image(
        self, ctx: ChatContext
    ) -> AsyncGenerator[str, None]:
        """
        Handle non-food related image with direct response.

        This short-circuits the normal conversation flow for non-cooking content.
        """
        if not ctx.vision_result or not ctx.vision_result.direct_response:
            return

        yield self._emit_thinking(ctx, "💬 图片与烹饪无关，直接回复...")

        # End thinking phase
        ctx.thinking_end_time = time.time()
        ctx.answer_start_time = time.time()

        # Use direct response from vision analysis
        response = ctx.vision_result.direct_response
        yield f"data: {json.dumps({'type': 'text', 'content': response})}\n\n"

        ctx.answer_end_time = time.time()

        # Emit empty sources (no RAG used)
        yield f"data: {json.dumps({'type': 'sources', 'data': []})}\n\n"

        # Save response with vision intent
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
        Process web search decision.

        Returns:
            Tuple of (decision, list of SSE events to yield)
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
        Execute web search and update context.

        Returns:
            List of SSE events to yield
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

            # Update context
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
        Prepare RAG context by rewriting query and retrieving documents.

        This method only prepares data (sources, rag_context, rewritten_query).
        It does NOT emit sources or generate the final response.

        Yields:
            SSE thinking events only.
        """
        yield self._emit_thinking(ctx, "⏳ 正在结合对话历史重写查询语句...")

        try:
            # Query rewriting
            ctx.rewritten_query = await self.query_rewriter.rewrite(
                current_query=ctx.message,
                history_text=ctx.history_text,
                user_id=ctx.user_id,
                conversation_id=ctx.conv_id,
            )
            yield self._emit_thinking(ctx, f"✍️ 重写后的查询语句: {ctx.rewritten_query}")

            # RAG retrieval
            yield self._emit_thinking(ctx, "🔎 正在从 CookHero 知识库中检索相关资料...")

            retrieval_result = await rag_service_instance.retrieve(
                ctx.rewritten_query,
                skip_rewrite=True,
                user_id=ctx.user_id,
                conversation_id=ctx.conv_id,
            )

            # Process retrieval results (updates ctx.sources and ctx.rag_context)
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
        """Process RAG retrieval results and handle fallback web search."""
        doc_count = len(retrieval_result.documents)

        # Convert RAG sources to unified format
        if retrieval_result.sources:
            for source in retrieval_result.sources:
                ctx.sources.append(UnifiedSource.from_rag_source(source))

        # Store RAG context
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

            # Fallback to web search if RAG returns no results
            should_fallback = (
                ctx.options.web_search
                and web_search_decision
                and web_search_decision.search_params
                and not ctx.web_search_context  # Haven't done web search yet
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
        Generate LLM response with context.

        Yields:
            Raw text chunks (not SSE formatted). Caller is responsible for formatting.
        """
        # Build combined context prompt
        context_prompt = self._build_combined_context_prompt(
            rag_context=ctx.rag_context,
            web_context=ctx.web_search_context,
            rewritten_query=ctx.rewritten_query,
            vision_context=ctx.vision_context,
        )

        # Build LLM messages
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
    # Phase 5: Save Response
    # =========================================================================

    async def _save_response(
        self,
        ctx: ChatContext,
        full_response: str,
        intent_result: IntentDetectionResult,
    ) -> None:
        """Save assistant response to database and schedule evaluation."""
        sources_data = [s.to_dict() for s in ctx.sources] if ctx.sources else None

        # Calculate durations in milliseconds
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

        # Schedule RAG evaluation if context was used
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
        """Helper to emit thinking step and update context."""
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
        Build context prompt combining vision, RAG, and web search results.
        Clearly distinguishes between different context sources.
        """
        parts = []

        # Add vision context first (if available)
        if vision_context.strip():
            parts.append(
                "【图片工具分析结果】\n"
                "用户上传了图片，以下是工具分析结果，请参考回答：\n"
                f"{vision_context.strip()}\n"
            )

        if rewritten_query.strip():
            parts.append(f"【重写后的检索语句】\n{rewritten_query}\n")

        # Add RAG context (local knowledge)
        if rag_context.strip():
            parts.append(
                "【本地知识库工具分析结果】\n"
                "下面是 CookHero 知识库中与当前问题最相关的资料，请参考回答：\n"
                f"{rag_context.strip()}\n"
            )

        # Add web search context
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
        Format assistant message content with sources appended.

        For LLM context, we append sources in a brief structured way so the model
        knows what references were used in previous responses.

        Args:
            content: The assistant's response content
            sources: Optional list of source dicts with type, info, url

        Returns:
            Formatted content with sources appended
        """
        if not sources:
            return content

        # Format sources as brief appendix
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
        """Get conversation history."""
        return await conversation_repository.get_history(conversation_id)

    async def clear_conversation(self, conversation_id: str) -> bool:
        """Clear a conversation."""
        return await conversation_repository.clear(conversation_id)

    async def list_conversations(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """List all conversations with basic metadata for UI switching.

        Returns:
            Tuple of (conversations list, total count)
        """
        return await conversation_repository.list_conversations(
            user_id=user_id,
            limit=limit,
            offset=offset,
        )

    async def update_conversation_title(self, conversation_id: str, title: str) -> bool:
        """Update the title of a conversation."""
        return await conversation_repository.update_title(conversation_id, title)


# Singleton instance
conversation_service = ConversationService()
