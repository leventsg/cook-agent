"""
CookAgent Prompt 注入防护模块

在用户输入到达 LLM 之前，
检测并拦截潜在的 Prompt 注入攻击
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Prompt 注入威胁等级"""
    SAFE = "safe"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class ScanResult:
    """Prompt 注入扫描结果"""
    threat_level: ThreatLevel
    matched_patterns: List[str] = field(default_factory=list)
    sanitized_input: str = ""
    reason: str = ""

class PromptGuard:
    """
    Prompt 注入攻击检测与防护
    检测多种类型的 Prompt 注入攻击：
    - 尝试覆盖系统提示词（System Prompt）
    - 角色扮演操纵攻击
    - 指令注入攻击
    - 分隔符攻击（Delimiter Attack）
    """
     # 危险模式匹配规则 (English)
    DANGEROUS_PATTERNS_EN = [
        # 系统提示词覆盖
        (r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", "system_override"),
        (r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", "system_override"),
        (r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", "system_override"),
        (r"(new|override|replace)\s+(system\s+)?instructions?", "system_override"),
        (r"system\s*prompt\s*[:=]", "system_override"),

        # 角色扮演操纵攻击
        (r"you\s+are\s+(now|no\s+longer)", "role_override"),
        (r"pretend\s+(to\s+be|you\s+are)", "role_override"),
        (r"act\s+as\s+(if\s+you\s+are|a)", "role_override"),
        (r"roleplay\s+as", "role_override"),

        # 指令注入攻击
        (r"\[system\]", "injection"),
        (r"\[assistant\]", "injection"),
        (r"<\|system\|>", "injection"),
        (r"<\|assistant\|>", "injection"),
        (r"```system", "injection"),

        # 越狱攻击
        (r"(dan|developer)\s+mode", "jailbreak"),
        (r"(enable|activate)\s+jailbreak", "jailbreak"),
        (r"bypass\s+(your\s+)?restrictions?", "jailbreak"),
    ]

    # 危险模式匹配规则 (Chinese)
    DANGEROUS_PATTERNS_CN = [
        # 系统提示词覆盖
        (r"忽略\s*(之前|上面|以前|先前|你的|所有|这些)\s*的?\s*(指令|提示|规则|要求)", "system_override"),
        (r"无视\s*(之前|上面|以前|先前|你的|所有|这些)\s*的?\s*(指令|提示|规则)", "system_override"),
        (r"忘记\s*(之前|上面|以前|先前|你的|所有|这些)\s*的?\s*(指令|提示|规则)", "system_override"),
        (r"(新的|覆盖|替换|改变)\s*(系统)?\s*(指令|提示)", "system_override"),
        (r"不要\s*遵守\s*(你的)?\s*(指令|规则)", "system_override"),
        (r"违背\s*(你的)?\s*(指令|规则)", "system_override"),
        (r"打破\s*(你的)?\s*(限制|规则)", "system_override"),

        # 角色扮演操纵攻击
        (r"你现在是", "role_override"),
        (r"你不再是", "role_override"),
        (r"假装你是", "role_override"),
        (r"扮演\s*(一个)?", "role_override"),
        (r"从现在开始.*?你是", "role_override"),
        (r"成为\s*(一个)?", "role_override"),

        # 越狱攻击
        (r"(开发者|开发人员)\s*模式", "jailbreak"),
        (r"(启用|激活)\s*越狱", "jailbreak"),
        (r"绕过\s*(你的)?\s*限制", "jailbreak"),
        (r"解除\s*(你的)?\s*限制", "jailbreak"),
        (r"破解\s*(你的)?\s*(防护|安全)", "jailbreak"),
    ]

    # 敏感话题检测模式（非烹饪相关的敏感内容）
    SENSITIVE_TOPIC_PATTERNS = [
        # 政治敏感
        (r"(写|帮我写|输出|生成).{0,10}(政治|反动|颠覆)", "off_topic_political"),
        (r"(关于|涉及|讨论)\s*(政治|政府|选举|政策)", "off_topic_political"),
        
        # 暴力/仇恨内容
        (r"(写|帮我写|输出|生成).{0,10}(暴力|仇恨|歧视|恐怖)", "off_topic_violence"),
        (r"(如何|怎么|教我)\s*(伤害|攻击|杀|打|揍)", "off_topic_violence"),
        
        # 非法活动
        (r"(如何|怎么|教我).{0,10}(黑客|入侵|破解|盗取)", "off_topic_illegal"),
        (r"(如何|怎么|教我).{0,10}(制造|制作).{0,10}(炸弹|武器|毒品)", "off_topic_illegal"),
        
        # 明确要求输出敏感内容
        (r"输出\s*(反动|敏感|违法|仇恨)\s*(言论|内容)", "off_topic_sensitive"),
    ]

    # 警告模式匹配规则 (Chinese)
    WARNING_PATTERNS = [
        (r"(what|tell\s+me)\s+(is|are)\s+your\s+(system\s+)?(prompt|instructions?)", "probe"),
        (r"repeat\s+(your\s+)?instructions?", "probe"),
        (r"(显示|告诉我)\s*(你的)?\s*(系统)?\s*(提示词|指令)", "probe"),
        (r"重复\s*(你的)?\s*指令", "probe"),
    ]

    def __init__(self, enabled: bool = True, max_length: int = 10000):
        """
        初始化 Prompt 保护器

        Args:
            enabled: 是否启用保护器
            max_length: 最大输入长度
        """
        self.enabled = enabled if enabled else settings.PROMPT_GUARD_ENABLED
        self.max_length = max_length if max_length else settings.MAX_MESSAGE_LENGTH

        # 编译危险模式匹配规则
        self._dangerous_patterns = [
            (re.compile(p, re.IGNORECASE), t)
            for p, t in self.DANGEROUS_PATTERNS_EN + self.DANGEROUS_PATTERNS_CN + self.SENSITIVE_TOPIC_PATTERNS
        ]
        self._warning_patterns = [
            (re.compile(p, re.IGNORECASE), t)
            for p, t in self.WARNING_PATTERNS
        ]

    def scan(self, text: str) -> ScanResult:
        """
        扫描文本以检测潜在的恶意注入尝试

        Args:
            text: 用户输入文本

        Returns:
            ScanResult 结果
        """
        if not self.enabled:
            return ScanResult(
                threat_level=ThreatLevel.SAFE,
                sanitized_input=text,
            )

        matched_patterns = []
        threat_level = ThreatLevel.SAFE

        # 检查输入长度是否超过最大限制
        if len(text) > self.max_length:
            return ScanResult(
                threat_level=ThreatLevel.BLOCKED,
                matched_patterns=["length_exceeded"],
                sanitized_input=text[:self.max_length],
                reason=f"输入长度 {len(text)} 超过限制 {self.max_length}",
            )
        
        # 检查危险模式匹配规则（阻塞）
        for pattern, threat_type in self._dangerous_patterns:
            if pattern.search(text):
                matched_patterns.append(f"{threat_type}:{pattern.pattern[:50]}")
                threat_level = ThreatLevel.BLOCKED

        if threat_level == ThreatLevel.BLOCKED:
            logger.warning(
                f"Prompt injection BLOCKED: patterns={matched_patterns}, "
                f"input_preview={text[:100]}..."
            )
            return ScanResult(
                threat_level=ThreatLevel.BLOCKED,
                matched_patterns=matched_patterns,
                sanitized_input="",
                reason="检测到潜在的恶意输入，请修改您的问题",
            )

        # 检查警告模式（记录日志但允许）
        for pattern, threat_type in self._warning_patterns:
            if pattern.search(text):
                matched_patterns.append(f"warning:{threat_type}")
                threat_level = ThreatLevel.WARNING

        if threat_level == ThreatLevel.WARNING:
            logger.info(
                f"Prompt injection WARNING: patterns={matched_patterns}, "
                f"input_preview={text[:100]}..."
            )

        return ScanResult(
            threat_level=threat_level,
            matched_patterns=matched_patterns,
            sanitized_input=self._sanitize(text),
            reason="",
        )

    def _sanitize(self, text: str) -> str:
        """
        通过转义潜在危险内容对文本进行净化处理
        该方法采用轻量级净化策略，在保留原始语义的同时，
        降低 Prompt 注入攻击的有效性
        """
        # 移除潜在的分隔符注入
        text = re.sub(r'\[/?system\]', '[FILTERED]', text, flags=re.IGNORECASE)
        text = re.sub(r'\[/?assistant\]', '[FILTERED]', text, flags=re.IGNORECASE)
        text = re.sub(r'<\|[^|]+\|>', '[FILTERED]', text)

        return text
    
    def check(self, text: str) -> Tuple[bool, str]:
        """
        检查文本是否安全处理

        Args:
            text: 用户输入文本

        Returns:
            (is_safe, error_message)
        """
        result = self.scan(text)

        if result.threat_level == ThreatLevel.BLOCKED:
            return False, result.reason

        return True, ""

prompt_guard = PromptGuard()