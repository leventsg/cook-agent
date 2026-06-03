from dataclasses import dataclass, field
import random

@dataclass
class AlertThresholds:
    """
    质量告警阈值配置。
    属性：
        faithfulness: 答案忠实度阈值
        answer_relevancy: 答案相关性阈值
    """
    faithfulness: float = 0.3
    answer_relevancy: float = 0.5


@dataclass
class EvaluationConfig:
    """
    RAG 评测配置。

    属性：
        enabled: 是否启用评测功能
        async_mode: 是否以异步方式执行评测（推荐）
        sample_rate: 参与评测的请求采样比例（0.0 ~ 1.0）
        metrics: 需要计算的评测指标列表
        llm_type: 用于评测的 LLM 层级（推荐使用 fast 以降低成本）
        timeout_seconds: 评测超时时间（秒）
        alert_thresholds: 质量告警阈值配置
    """
    enabled: bool = False
    async_mode: bool = True
    sample_rate: float = 1.0
    # 需要计算的 RAGAS 评测指标
    # 注意：
    # context_precision（上下文精确率）和 context_recall（上下文召回率）
    # 依赖于 reference（真实标注/标准答案），而实时在线评测场景通常无法获得
    # 该类参考数据。
    # 因此，在无 reference 的情况下，仅以下指标可用于实时评测：
    # - faithfulness（答案忠实度）
    # - answer_relevancy（答案相关性）
    metrics: list[str] = field(default_factory=lambda: [
        "faithfulness",
        "answer_relevancy",
    ])

    llm_type: str = "fast"

    # 评测超时时间（秒）10分钟
    timeout_seconds: int = 600

    alert_thresholds: AlertThresholds = field(default_factory=AlertThresholds)

    def should_evaluate(self) -> bool:
        """
        判断当前请求是否应该参与评测，基于采样比例。
        返回：
            bool: 是否参与评测
        """
        if not self.enabled:
            return False
        if self.sample_rate >= 1.0:
            return True
        return random.random() < self.sample_rate
    
#Default configuration
DefaultEvaluationConfig = EvaluationConfig()