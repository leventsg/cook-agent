# =============================================================================
# CookAgent NeMo Guardrails 封装
# =============================================================================
# 提供统一的安全检查 API，封装 NeMo Guardrails 功能
# =============================================================================

import asyncio
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Tuple

from app.llm import get_llm_context

logger = logging.getLogger(__name__)


def _compile_block_patterns(
    patterns: list[tuple[str, str]], group_prefix: str
) -> tuple[re.Pattern[str], dict[str, tuple[str, str]]]:
    """
    将多个块级匹配模式编译为单个正则表达式，并保留对应的分组元数据
    """
    group_map = {}
    grouped_patterns = []

    for index, (pattern, threat_type) in enumerate(patterns):
        group_name = f"{group_prefix}_{index}"
        grouped_patterns.append(f"(?P<{group_name}>{pattern})")
        group_map[group_name] = (pattern, threat_type)

    return re.compile("|".join(grouped_patterns), re.IGNORECASE), group_map


class GuardResult(Enum):
    """安全检查结果枚举"""

    SAFE = "safe"  # 安全，可以继续
    BLOCKED = "blocked"  # 阻止，拒绝处理
    WARNING = "warning"  # 警告，记录但允许

@dataclass
class SecurityCheckResult:
    """安全检查结果"""

    result: GuardResult
    reason: str = ""
    details: Optional[dict] = None

    @property
    def is_safe(self) -> bool:
        return self.result != GuardResult.BLOCKED

    @property
    def should_block(self) -> bool:
        return self.result == GuardResult.BLOCKED
    
class CookAgentGuard:
    """
    CookAgent 安全防护封装

    CookAgent 安全防护封装，基于 NeMo Guardrails 提供：
    - 输入层：Prompt Injection 检测、Jailbreak 检测、话题检测
    - 输出层：系统提示泄露检测、敏感内容过滤

    使用方式：
    ```python
    guard = CookAgentGuard()

    # 检查输入
    result = await guard.check_input("用户消息")
    if not result.is_safe:
        raise HTTPException(400, result.reason)

    # 检查输出
    result = await guard.check_output("AI 响应")
    if not result.is_safe:
        return safe_response
    ```
    """

    # 配置路径
    CONFIG_PATH = Path(__file__).parent / "config"

    MODULE_NAME = "safety_guardrails"

    # 标准安全拒答响应
    BLOCKED_RESPONSES = {
        "jailbreak": "抱歉，我无法回答这个问题。我是 CookAgent，专注于烹饪相关的帮助。🍳",
        "prompt_injection": "检测到潜在的恶意输入，请修改您的问题。",
        "off_topic": "作为您的烹饪助手，我只能回答与烹饪、食物、厨房相关的问题。有什么美食问题我可以帮您解答吗？🥗",
        "output_leak": "抱歉，我无法提供这类信息。让我们继续聊烹饪相关的话题吧！🍳",
        "default": "抱歉，我无法处理这个请求。",
    }

    # 危险输入模式检测 - 与 prompt_guard.py 保持一致
    BASIC_INPUT_PATTERNS = [
        # 系统提示覆盖 - 扩展版本
        (
            r"ignore\s+(all\s+)?(previous|prior|above|your|these)\s+(instructions?|prompts?|rules?)",
            "jailbreak",
        ),
        (
            r"忽略\s*(之前|上面|以前|先前|你的|所有|这些)\s*的?\s*(指令|提示|规则|要求)",
            "jailbreak",
        ),
        (r"(新的|覆盖|替换)\s*(系统)?\s*(指令|提示)", "jailbreak"),
        # 不要遵守/违背/打破规则
        (
            r"(don't|do\s+not)\s+(follow|obey|comply\s+with)\s+(your\s+)?(instructions?|rules?)",
            "jailbreak",
        ),
        (r"不要\s*遵守\s*(你的)?\s*(指令|规则)", "jailbreak"),
        (r"违背\s*(你的)?\s*(指令|规则)", "jailbreak"),
        (r"打破\s*(你的)?\s*(限制|规则)", "jailbreak"),
        # 角色扮演操控
        # 只拦截明显的系统提示覆盖行为，而非所有角色扮演
        (r"你现在是.*?(没有|解除|绕过|无视|忽略).*?(限制|规则|指令)", "jailbreak"),
        (r"你现在是.*?(自由|随便|任何|全部).*?(回答|说|做)", "jailbreak"),
        (r"从现在开始.*?(没有|解除|绕过|无视|忽略).*?(限制|规则|指令)", "jailbreak"),
        (
            r"you\s+are\s+now.*?(without\s+|no\s+|ignore\s+|bypass\s+).*?(restrictions?|rules?|instructions?)",
            "jailbreak",
        ),
        (r"pretend\s+to\s+be\s+(unrestricted|free|without\s+limits)", "jailbreak"),
        # 分隔符注入
        (r"\[system\]", "prompt_injection"),
        (r"\[assistant\]", "prompt_injection"),
        (r"<\|system\|>", "prompt_injection"),
        (r"<\|assistant\|>", "prompt_injection"),
        (r"<\|im_start\|>", "prompt_injection"),
        (r"<<SYS>>", "prompt_injection"),
        # Jailbreak 尝试
        (r"(dan|developer)\s+mode", "jailbreak"),
        (r"(开发者|开发人员)\s*模式", "jailbreak"),
        (r"bypass\s+(your\s+)?restrictions?", "jailbreak"),
        (r"绕过\s*(你的)?\s*限制", "jailbreak"),
        # 忘记/清除规则
        (r"(forget|clear|erase)\s+(your\s+)?(rules?|instructions?)", "jailbreak"),
        (r"(忘记|清除|抹除)\s*(你的)?\s*(规则|指令)", "jailbreak"),
    ]
    BASIC_INPUT_REGEX, BASIC_INPUT_GROUP_MAP = _compile_block_patterns(
        BASIC_INPUT_PATTERNS, "input_pattern"
    )

    BASIC_OUTPUT_PATTERNS = [
        # 英文模式
        (r"my\s+(system\s+)?prompt\s+is", "output_leak"),
        (r"my\s+instructions?\s+(are|is)", "output_leak"),
        (r"API[_\s]?key", "output_leak"),
        (r"I\s+am\s+(GPT|Claude|Gemini|LLaMA)", "output_leak"),
        # 中文模式
        (r"我的.{0,10}(系统)?(提示|指令).{0,5}是", "output_leak"),
        (r"系统提示.{0,5}(是|为)", "output_leak"),
        (r"API\s*密钥", "output_leak"),
        (r"我是\s*(GPT|Claude|Gemini|LLaMA|OpenAI|Anthropic)", "output_leak"),
    ]
    BASIC_OUTPUT_REGEX, BASIC_OUTPUT_GROUP_MAP = _compile_block_patterns(
        BASIC_OUTPUT_PATTERNS, "output_pattern"
    )

    def __init__(self, enabled: bool = True):
        """
        初始化 Guardrails

        Args:
            enabled: 是否启用安全检查
        """
        self.enabled = enabled
        self._rails: Any = None 
        self._initialized = False

    async def _ensure_initialized(self) -> bool:
        """确保 Guardrails 已初始化"""
        if self._initialized:
            return self._rails is not None

        if not self.enabled:
            self._initialized = True
            return False

        try:
            from nemoguardrails import RailsConfig, LLMRails

            # 检查配置目录是否存在
            if not self.CONFIG_PATH.exists():
                logger.error(f"Guardrails config path not found: {self.CONFIG_PATH}")
                self._initialized = True
                return False

            # 从应用配置获取 LLM 设置
            from app.config.config import settings

            llm_config = settings.llm.fast  # 使用 fast LLM 进行安全检查（低延迟）

            # 设置环境变量供 NeMo Guardrails 使用
            # NeMo Guardrails 通过 LangChain 初始化，需要这些环境变量
            if llm_config.api_key:
                os.environ["OPENAI_API_KEY"] = llm_config.api_key
            if llm_config.base_url:
                os.environ["OPENAI_API_BASE"] = llm_config.base_url

            # 加载配置
            config = RailsConfig.from_path(str(self.CONFIG_PATH))

            # 动态设置模型名称为应用配置中的模型
            if hasattr(llm_config, "pick_default_model"):
                model_name = llm_config.pick_default_model()
                config.models[0].model = model_name
                logger.info(f"Guardrails model set to: {model_name}")

            self._rails = LLMRails(config)

            logger.info("NeMo Guardrails initialized successfully")
            self._initialized = True
            return True

        except ImportError:
            logger.warning(
                "nemoguardrails not installed, falling back to basic protection"
            )
            self._initialized = True
            return False
        except Exception as e:
            logger.error(f"Failed to initialize Guardrails: {e}")
            self._initialized = True
            return False
        
    async def _log_guardrails_usage(self, duration_ms: int) -> None:
        """
        记录 Guardrails 的 LLM 使用情况
        由于 NeMo Guardrails 不提供 Token 使用统计信息，
        因此相关 Token 字段以 None 进行记录
        """
        try:
            from app.database.llm_usage_repository import llm_usage_repository

            ctx = get_llm_context()

            await llm_usage_repository.create_log(
                request_id=str(uuid.uuid4()),
                module_name=self.MODULE_NAME,
                user_id=ctx.user_id if ctx else None,
                conversation_id=ctx.conversation_id if ctx else None,
                model_name="guardrails",  # NeMo uses its own model config
                input_tokens=None,
                output_tokens=None,
                total_tokens=None,
                duration_ms=duration_ms,
            )
        except Exception as e:
            logger.warning(f"Failed to log guardrails usage: {e}")

    async def check_input(self, message: str) -> SecurityCheckResult:
        """
        检查用户输入是否安全

        Args:
            message: 用户输入消息

        Returns:
            SecurityCheckResult: 包含检查结果和原因
        """
        # 1. 基础检查（始终执行，不依赖 Guardrails）
        basic_result = self._basic_input_check(message)
        if basic_result.should_block:
            return basic_result

        # 2. Guardrails 深度检查
        if await self._ensure_initialized() and self._rails:
            try:
                return await self._guardrails_input_check(message)
            except Exception as e:
                logger.error(f"Guardrails input check failed: {e}")
                # 失败时不阻止，但记录警告
                return SecurityCheckResult(
                    result=GuardResult.WARNING,
                    reason="安全检查异常，已记录",
                    details={"error": str(e)},
                )

        return SecurityCheckResult(result=GuardResult.SAFE)

    async def check_output(self, response: str) -> SecurityCheckResult:
        """
        检查 AI 输出是否安全

        Args:
            response: AI 生成的响应

        Returns:
            SecurityCheckResult: 包含检查结果和原因
        """
        # 1. 基础输出检查
        basic_result = self._basic_output_check(response)
        if basic_result.should_block:
            return basic_result

        # 2. Guardrails 深度检查
        if await self._ensure_initialized() and self._rails:
            try:
                return await self._guardrails_output_check(response)
            except Exception as e:
                logger.error(f"Guardrails output check failed: {e}")
                return SecurityCheckResult(
                    result=GuardResult.WARNING,
                    reason="输出安全检查异常",
                    details={"error": str(e)},
                )

        return SecurityCheckResult(result=GuardResult.SAFE)

    def _match_basic_pattern(
        self,
        text: str,
        regex: re.Pattern[str],
        group_map: dict[str, tuple[str, str]],
    ) -> Optional[tuple[str, str]]:
        match = regex.search(text)
        if not match or not match.lastgroup:
            return None

        return group_map[match.lastgroup]

    def _basic_input_check(self, message: str) -> SecurityCheckResult:
        """基础输入检查（不依赖 LLM）"""
        matched_pattern = self._match_basic_pattern(
            message, self.BASIC_INPUT_REGEX, self.BASIC_INPUT_GROUP_MAP
        )
        if matched_pattern:
            pattern, threat_type = matched_pattern
            logger.warning(
                f"Basic input check blocked: {threat_type}, pattern: {pattern[:50]}"
            )
            return SecurityCheckResult(
                result=GuardResult.BLOCKED,
                reason=self.BLOCKED_RESPONSES.get(
                    threat_type, self.BLOCKED_RESPONSES["default"]
                ),
                details={"threat_type": threat_type, "pattern": pattern},
            )

        return SecurityCheckResult(result=GuardResult.SAFE)

    def _basic_output_check(self, response: str) -> SecurityCheckResult:
        """基础输出检查（不依赖 LLM）"""
        matched_pattern = self._match_basic_pattern(
            response, self.BASIC_OUTPUT_REGEX, self.BASIC_OUTPUT_GROUP_MAP
        )
        if matched_pattern:
            pattern, threat_type = matched_pattern
            logger.warning(
                f"Basic output check blocked: {threat_type}, pattern: {pattern[:50]}"
            )
            return SecurityCheckResult(
                result=GuardResult.BLOCKED,
                reason=self.BLOCKED_RESPONSES.get(
                    threat_type, self.BLOCKED_RESPONSES["output_leak"]
                ),
                details={"threat_type": threat_type, "pattern": pattern},
            )

        return SecurityCheckResult(result=GuardResult.SAFE)
    
    async def _guardrails_input_check(self, message: str) -> SecurityCheckResult:
        """使用 NeMo Guardrails 进行深度输入检查"""
        start_time = time.time()
        try:
            # 使用 Guardrails 生成响应
            # 如果触发了安全规则，rails 会返回拒绝响应
            result = await self._rails.generate_async(
                messages=[{"role": "user", "content": message}]
            )

            # Log usage
            duration_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(self._log_guardrails_usage(duration_ms))

            logger.debug(f"Guardrails generate_async result: {result}")

            # 检查结果结构
            if result and isinstance(result, dict):
                bot_message = result.get("content", "")
                logger.debug(f"Bot message: {bot_message}")

                # 检查是否是标准拒绝响应
                if self._is_rejection_response(bot_message):
                    return SecurityCheckResult(
                        result=GuardResult.BLOCKED,
                        reason=bot_message,
                        details={"source": "guardrails"},
                    )

            # 如果没有被拦截，认为是安全的
            return SecurityCheckResult(result=GuardResult.SAFE)

        except Exception as e:
            # Log usage even on error
            duration_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(self._log_guardrails_usage(duration_ms))

            logger.error(f"Guardrails input check error: {e}")
            # 如果是安全相关的异常，可能意味着输入被阻止
            if (
                "block" in str(e).lower()
                or "reject" in str(e).lower()
                or "unsafe" in str(e).lower()
            ):
                return SecurityCheckResult(
                    result=GuardResult.BLOCKED,
                    reason="Input blocked by guardrails",
                    details={"error": str(e)},
                )
            return SecurityCheckResult(
                result=GuardResult.WARNING,
                reason="Guardrails 检查异常",
                details={"error": str(e)},
            )
        
    async def _guardrails_output_check(self, response: str) -> SecurityCheckResult:
        """使用 NeMo Guardrails 进行输出检查"""
        start_time = time.time()
        try:
            # 使用 output rails 检查
            result = await self._rails.generate_async(
                messages=[
                    {"role": "user", "content": "检查输出"},
                    {"role": "assistant", "content": response},
                ]
            )

            # Log usage
            duration_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(self._log_guardrails_usage(duration_ms))

            # 如果输出被修改，说明触发了输出 rails
            if result and isinstance(result, dict):
                new_content = result.get("content", "")
                if new_content != response and self._is_rejection_response(new_content):
                    return SecurityCheckResult(
                        result=GuardResult.BLOCKED,
                        reason=self.BLOCKED_RESPONSES["output_leak"],
                        details={"original": response[:100], "filtered": new_content},
                    )

            return SecurityCheckResult(result=GuardResult.SAFE)

        except Exception as e:
            # Log usage even on error
            duration_ms = int((time.time() - start_time) * 1000)
            asyncio.create_task(self._log_guardrails_usage(duration_ms))

            logger.error(f"Guardrails output check error: {e}")
            return SecurityCheckResult(
                result=GuardResult.WARNING,
                reason="输出检查异常",
                details={"error": str(e)},
            )

    def _is_rejection_response(self, response: str) -> bool:
        """检查响应是否是拒绝响应"""
        rejection_keywords = [
            "抱歉，我无法",
            "我无法回答",
            "无法提供",
            "检测到潜在",
            "sorry, i can't",
            "i cannot answer",
            "i'm sorry, i can't",
        ]
        result = any(
            keyword.lower() in response.lower() for keyword in rejection_keywords
        )
        logger.debug(f"Checking rejection for '{response}': {result}")
        return result

    def get_safe_response(self, threat_type: str = "default") -> str:
        """获取安全的拒绝响应"""
        return self.BLOCKED_RESPONSES.get(
            threat_type, self.BLOCKED_RESPONSES["default"]
        )
    
# =============================================================================
# 全局实例
# =============================================================================

# 从环境变量读取是否启用
_enabled = os.getenv("GUARDRAILS_ENABLED", "false").lower() == "true"

# 全局 guard 实例
guard = CookAgentGuard(enabled=_enabled)

# =============================================================================
# 便捷函数
# =============================================================================


async def check_input(message: str) -> Tuple[bool, str]:
    """
    便捷函数：检查输入是否安全

    Returns:
        Tuple[bool, str]: (is_safe, reason)
    """
    result = await guard.check_input(message)
    return result.is_safe, result.reason


async def check_output(response: str) -> Tuple[bool, str]:
    """
    便捷函数：检查输出是否安全

    Returns:
        Tuple[bool, str]: (is_safe, reason)
    """
    result = await guard.check_output(response)
    return result.is_safe, result.reason
