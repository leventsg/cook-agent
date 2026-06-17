"""
基于 RAGAS 框架的 RAG 评估服务

提供对 RAG 回答结果的异步评估能力，
用于质量监控与效果分析
"""

import asyncio
import logging
import math
import time
from typing import Any, Dict, List, Optional

from app.config import settings
from app.config.evaluation_config import EvaluationConfig
from app.database.evaluation_repository import evaluation_repository
from app.llm import LLMProvider, get_usage_callbacks, llm_context

logger = logging.getLogger(__name__)


class FilteredChatOpenAI:
    """
    ChatOpenAI 的包装器，用于过滤不被支持的参数

    部分 API 提供商（例如 ModelScope）
    不支持 RAGAS 内部使用的 `n` 参数，
    因此在调用前会自动移除这类不兼容参数
    """

    # 不被部分 API 不支持的参数列表
    UNSUPPORTED_PARAMS = {"n"}

    def __init__(self, base_llm, callbacks=None):
        self._base_llm = base_llm
        self._callbacks = callbacks or []
        for attr in ["model_name", "temperature", "max_tokens", "model"]:
            if hasattr(base_llm, attr):
                setattr(self, attr, getattr(base_llm, attr))

    def _filter_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """从 kwargs 中移除不被支持的参数"""
        filtered = {k: v for k, v in kwargs.items() if k not in self.UNSUPPORTED_PARAMS}
        # 如果 callbacks 参数不存在，则添加
        if self._callbacks and "callbacks" not in filtered:
            filtered["callbacks"] = self._callbacks
        return filtered

    def invoke(self, *args, **kwargs):
        return self._base_llm.invoke(*args, **self._filter_kwargs(kwargs))

    async def ainvoke(self, *args, **kwargs):
        return await self._base_llm.ainvoke(*args, **self._filter_kwargs(kwargs))

    def generate(self, *args, **kwargs):
        return self._base_llm.generate(*args, **self._filter_kwargs(kwargs))

    async def agenerate(self, *args, **kwargs):
        return await self._base_llm.agenerate(*args, **self._filter_kwargs(kwargs))

    def generate_prompt(self, *args, **kwargs):
        return self._base_llm.generate_prompt(*args, **self._filter_kwargs(kwargs))

    async def agenerate_prompt(self, *args, **kwargs):
        return await self._base_llm.agenerate_prompt(
            *args, **self._filter_kwargs(kwargs)
        )

    def bind(self, **kwargs):
        """绑定参数到 ChatOpenAI 实例"""
        bound_llm = self._base_llm.bind(**self._filter_kwargs(kwargs))
        return FilteredChatOpenAI(bound_llm, callbacks=self._callbacks)

    def __getattr__(self, name):
        return getattr(self._base_llm, name)


class EvaluationService:
    """
    基于 RAGAS 框架的 RAG 评估服务

    提供对 RAG 回答结果的异步评估能力，
    用于质量监控与效果分析
    """

    MODULE_NAME = "quality_evaluation"

    def __init__(self, config: Optional[EvaluationConfig] = None):
        """
        初始化评估服务

        Args:
            config: 评估配置
        """
        self.config = config or settings.evaluation
        self._ragas_initialized = False
        self._metrics = None
        self._llm = None
        self._embeddings = None
        self._callbacks = get_usage_callbacks()

    def _init_ragas_sync(self):
        """
        同步初始化 RAGAS (在线程池中运行)。
        此方法可能会因 HuggingFace 模型下载而阻塞。
        """
        try:
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
            )
            from ragas.llms import LangchainLLMWrapper
            from ragas.embeddings import LangchainEmbeddingsWrapper

            # 获取 LLM 实例
            provider = LLMProvider(settings.llm)
            base_llm = provider.create_llm(self.config.llm_type, temperature=0.0)

            filtered_llm = FilteredChatOpenAI(base_llm, callbacks=self._callbacks)

            self._llm = LangchainLLMWrapper(filtered_llm)

            # 获取 RAG 配置中的embedding模型配置
            from app.rag.embeddings.embedding_factory import get_embedding_model

            # 获取rag的embedding模型实例
            base_embeddings = get_embedding_model(settings.rag)

            self._embeddings = LangchainEmbeddingsWrapper(base_embeddings)

            # 初始化评估指标实例
            self._metrics_map = {
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
            }

            self._metrics = [
                self._metrics_map[m]
                for m in self.config.metrics
                if m in self._metrics_map
            ]

            # 配置评估指标实例，将 LLM 实例和 embedding模型实例绑定到每个指标
            for metric in self._metrics:
                if hasattr(metric, "llm"):
                    metric.llm = self._llm
                if hasattr(metric, "embeddings"):
                    metric.embeddings = self._embeddings

            self._ragas_initialized = True
            logger.info(
                "RAGAS initialized with metrics: %s",
                [m.name for m in self._metrics],
            )

        except ImportError as e:
            logger.error("Failed to import RAGAS: %s", e)
            raise
        except Exception as e:
            logger.error("Failed to initialize RAGAS: %s", e)
            raise

    async def _init_ragas(self):
        """
        异步初始化 RAGAS 组件
        """
        if self._ragas_initialized:
            return

        await asyncio.to_thread(self._init_ragas_sync)

    async def evaluate(
        self,
        query: str,
        context: str,
        response: str,
    ) -> Dict[str, float]:
        """
        对 RAG 回答结果进行评估，返回指标分数

        Args:
            query: 用户查询文本
            context: RAG 检索到的上下文
            response: RAG 生成的响应文本

        Returns:
            评估指标分数Dict，key为指标名称，value为指标分数
        """
        await self._init_ragas()

        try:
            from datasets import Dataset
            from ragas import evaluate

            # 准备数据集，将上下文转换为字符串列表
            # 由于 RAGAS 准备数据格式为上下文列表，每个上下文为一个字符串
            contexts = [context] if context else [""]

            dataset = Dataset.from_dict(
                {
                    "question": [query],
                    "answer": [response],
                    "contexts": [contexts],
                }
            )

            # 运行评估
            result = await asyncio.to_thread(
                evaluate,
                dataset,
                metrics=self._metrics,
            )

            # 从 RAGAS 评估结果中提取得分
            # 在 RAGAS 0.4.x 版本中，result 为 EvaluationResult 对象
            # 因此需要采用不同的方式获取各项评分
            scores = {}

            if hasattr(result, "scores"):
                score_list = result.scores  # type: ignore
                if score_list and len(score_list) > 0:
                    first_score = score_list[0]
                    for metric_name in self.config.metrics:
                        if metric_name in first_score:
                            value = first_score[metric_name]
                            scores[metric_name] = (
                                float(value)
                                if value is not None and not math.isnan(value)
                                else None
                            )
            elif hasattr(result, "to_pandas"):
                df = result.to_pandas()  
                for metric_name in self.config.metrics:
                    if metric_name in df.columns:
                        value = df[metric_name].iloc[0]
                        scores[metric_name] = (
                            float(value)
                            if value is not None and not math.isnan(value)
                            else None
                        )
            else:
                for metric_name in self.config.metrics:
                    try:
                        if hasattr(result, metric_name):
                            value = getattr(result, metric_name)
                            if hasattr(value, "__iter__") and not isinstance(
                                value, str
                            ):
                                scores[metric_name] = (
                                    float(list(value)[0]) if value else None
                                )
                            else:
                                scores[metric_name] = (
                                    float(value)
                                    if value is not None and not math.isnan(value)  # type: ignore
                                    else None
                                )  # type: ignore
                    except Exception:
                        pass

            logger.info("Evaluation completed: %s", scores)
            return scores

        except Exception as e:
            logger.error("Evaluation failed: %s", e, exc_info=True)
            raise

    async def schedule_evaluation(
        self,
        message_id: str,
        conversation_id: str,
        query: str,
        context: str,
        response: str,
        rewritten_query: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        """
        为 RAG 回答安排一次异步评估任务
        该方法会创建一条评估记录，并在后台执行评估流程，
        不会阻塞主对话处理流程。

        参数：
            message_id:
                被评估消息的 ID
            conversation_id:
                所属会话 ID
            query:
                用户原始查询
            context:
                用于生成回答的检索上下文
            response:
                生成的回答内容
            rewritten_query:
                重写后的查询（如果存在）
            user_id:
                用户 ID（如果可获取）
        """
        if not self.config.enabled:
            logger.debug("Evaluation disabled, skipping")
            return

        if not self.config.should_evaluate():
            logger.debug("Evaluation skipped due to sampling")
            return

        if not context:
            logger.debug("No context provided, skipping evaluation")
            return

        if not response or not response.strip():
            logger.debug("No response provided, skipping evaluation")
            return

        try:
            evaluation = await evaluation_repository.create(
                message_id=message_id,
                conversation_id=conversation_id,
                query=query,
                context=context,
                response=response,
                rewritten_query=rewritten_query,
                user_id=user_id,
            )

            if self.config.async_mode:
                asyncio.create_task(
                    self._run_evaluation(
                        str(evaluation.id),
                        query,
                        context,
                        response,
                        user_id=user_id,
                        conversation_id=conversation_id,
                    )
                )
            else:
                await self._run_evaluation(
                    str(evaluation.id),
                    query,
                    context,
                    response,
                    user_id=user_id,
                    conversation_id=conversation_id,
                )

        except Exception as e:
            logger.error("Failed to schedule evaluation: %s", e, exc_info=True)

    async def _run_evaluation(
        self,
        evaluation_id: str,
        query: str,
        context: str,
        response: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ):
        """
        执行实际评估并更新数据库中的评估结果
        参数：
            evaluation_id:
                评估记录 ID
            query:
                用户原始查询
            context:
                检索得到的上下文内容
            response:
                生成的回答内容
            user_id:
                用户 ID，用于追踪记录（可选）
            conversation_id:
                会话 ID，用于追踪记录（可选）
        """
        start_time = time.time()

        try:
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                results = await asyncio.wait_for(
                    self.evaluate(query, context, response),
                    timeout=self.config.timeout_seconds,
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # 将评估结果更新到数据库
            await evaluation_repository.update_results(
                evaluation_id=evaluation_id,
                results=results,
                duration_ms=duration_ms,
                status="completed",
            )

            logger.info(
                "Evaluation %s completed in %dms: %s",
                evaluation_id,
                duration_ms,
                results,
            )

        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            await evaluation_repository.update_results(
                evaluation_id=evaluation_id,
                results={},
                duration_ms=duration_ms,
                status="failed",
                error_message=f"Evaluation timed out after {self.config.timeout_seconds}s",
            )
            logger.warning("Evaluation %s timed out", evaluation_id)

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            await evaluation_repository.update_results(
                evaluation_id=evaluation_id,
                results={},
                duration_ms=duration_ms,
                status="failed",
                error_message=str(e)[:500],
            )
            logger.error("Evaluation %s failed: %s", evaluation_id, e, exc_info=True)


evaluation_service = EvaluationService()
