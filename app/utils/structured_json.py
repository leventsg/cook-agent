import json
import re
from typing import Any, Dict

# 正则表达式匹配 ```json ... ``` 代码块
JSON_BLOCK_RE = re.compile(
    r"```json\s*([\s\S]*?)\s*```",
    re.IGNORECASE
)


def _decode_first_json_object(content: str) -> Dict[str, Any]:
    """逐字符扫描，找到第一个完整的 {} 对象"""
    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(content[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value

    raise ValueError("No valid JSON found in response")


def extract_first_valid_json(content: str) -> Dict[str, Any]:
    """Extract the first valid JSON object from LLM output."""
    # 优先从代码块提取json
    for match in JSON_BLOCK_RE.findall(content):
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    # 如果没有代码块，尝试直接解析整个内容
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    
    # 最后逐字符扫描寻找第一个完整的{}对象
    return _decode_first_json_object(content)
