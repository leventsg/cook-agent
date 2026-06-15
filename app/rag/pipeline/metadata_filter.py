"""
基于 LLM 的元数据表达式生成器
结合用户查询、可用元数据取值以及 Milvus 参考文档，
生成可直接用于向量存储 expr 字段的布尔过滤表达式字符串
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional
from urllib import response

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.config import settings, LLMType
from app.llm import LLMProvider, llm_context
from app.utils.structured_json import extract_first_valid_json

logger = logging.getLogger(__name__)


FILTER_EXPRESSION_PROMPT = ChatPromptTemplate.from_template(
    """
你是 CookAgent 的「Milvus 元数据过滤表达式生成器」。

你的任务是：**根据用户查询，判断是否可以生成一个可直接用于 Milvus `expr` 参数的布尔过滤表达式**。
**只有在条件明确、无歧义、不会明显损害召回的情况下，才允许生成过滤表达式；否则必须放弃过滤。**

【最高优先级原则】

- 元数据过滤是**精确约束**，不是语义理解或推理
- 只有当用户**明确表达**了可直接映射到元数据字段的条件时，才生成过滤
- 任何不确定、模糊、需要推断的情况，**一律不生成过滤**

【允许使用的字段（严格限制）】

你 **只能** 使用以下 metadata 字段：
- `category`
- `dish_name`
- `difficulty`

禁止使用任何未列出的字段。
**字段值必须严格来自【可用元数据取值】，禁止猜测、扩展或改写。**

【字段使用规则】

1. category  
- 仅在用户明确指定菜系或菜品大类时使用  
- 示例：川菜、家常菜、凉菜  
- 不得从口味、场景、食材等信息中推断 category  

2. dish_name  
- 仅在用户明确提及具体菜名时使用  
- 允许使用 `LIKE` / `ILIKE` 进行模糊匹配  
- 不得从食材或描述中推断菜名  

3. difficulty（高风险字段）  
- 仅在用户**明确提到难度要求**时使用  
  - 如：简单 / 新手 / 困难 / 复杂  
- 未明确提及难度，一律禁止使用该字段  

【逻辑组合规则】

- 仅在**所有条件都高度确定**时才使用 `AND`
- 若多个条件存在确定性差异，只保留**最确定的条件**
- 可使用 `OR / NOT`，但需确保不会扩大歧义
- 必要时使用括号明确优先级

禁止输出任何解释、注释、Markdown、换行或多余文本。

【Milvus 过滤表达式参考】
{reference_material}

【可用元数据取值】
{metadata_schema}

当前查询：
{query}

【输出格式（强约束）】

你 **必须且只能** 输出以下 JSON，对象结构固定：

- 当可以生成过滤表达式时：

{{
  "expr": "<可直接用于 Milvus 的过滤表达式>"
}}

- 当无法确定任何可靠过滤条件时：

{{
  "expr": "NONE"
}}
"""
)


REFERENCE_DIR = Path(__file__).resolve().parent / "reference"
REFERENCE_FILES = ("operators.md",)


class MetadataFilterExtractor:
    """基于 LLM 的 Milvus 元数据过滤表达式生成器"""

    MODULE_NAME = "rag_metadata_filter"

    def __init__(
        self,
        llm_type: LLMType | str = LLMType.FAST,
        provider: LLMProvider | None = None,
    ):
        self._llm_type = llm_type
        self._provider = provider or LLMProvider(settings.llm)
        # 创建带 usage tracking 的 invoker（推荐）
        self._llm = self._provider.create_invoker(llm_type, temperature=0.0)

        self.reference_material = self._load_reference_material()

    async def build_filter_expression(
        self,
        query: str,
        metadata_catalog: Dict[str, Dict[str, List[str]]],
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> str | None:
        if not metadata_catalog:
            return None

        debugc = ""

        metadata_schema = self._summarize_metadata(metadata_catalog)
        try:
            template = FILTER_EXPRESSION_PROMPT.format_prompt(
                query=query,
                reference_material=self.reference_material,
                metadata_schema=metadata_schema,
            )
            # 创建上下带 context 的调用，使用带 usage tracking 的 invoker（推荐）
            with llm_context(self.MODULE_NAME, user_id, conversation_id):
                response = await self._llm.ainvoke(list(template.messages))
            content = response.content.strip()
            debugc = content

            result = extract_first_valid_json(content)
            raw = result.get("expr", "")

            expression = self._clean_expression(raw)
            logger.info("Generated metadata expression: %s", expression or "NONE")
            return expression
        except Exception as exc:
            logger.warning("Metadata expression generation failed: %s", exc)
            logger.info("Metadata filter debug content: %s", debugc)
            return None

    def _load_reference_material(self) -> str:
        sections: List[str] = []
        for filename in REFERENCE_FILES:
            path = REFERENCE_DIR / filename
            try:
                sections.append(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                logger.warning("Reference file not found: %s", path)
            except Exception as exc:
                logger.warning("Failed to read reference file %s: %s", path, exc)
        return "\n\n".join(sections)

    @staticmethod
    def _summarize_metadata(metadata_catalog: Dict[str, Dict[str, List[str]]]) -> str:
        lines = []
        for source, metadata in metadata_catalog.items():
            lines.append(f"来源: {source}")
            for key, values in metadata.items():
                sample = "、".join(values)
                lines.append(f"- {key} (共{len(values)}个): {sample}")
        return "\n".join(lines)

    @staticmethod
    def _clean_expression(raw_text: str) -> str | None:
        text = raw_text.strip()
        fence_pattern = r"```(?:[a-zA-Z0-9_+-]+)?\s*([\s\S]*?)```"
        match = re.search(fence_pattern, text)
        if match:
            text = match.group(1).strip()

        if text.startswith('"') and text.endswith('"') and len(text) >= 2:
            text = text[1:-1].strip()

        if text.upper() == "NONE" or not text:
            return None

        return text
