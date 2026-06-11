import json
import re
from typing import Any, Dict

# JSON extraction regex
JSON_BLOCK_RE = re.compile(
    r"```json\s*([\s\S]*?)\s*```",
    re.IGNORECASE
)


def _decode_first_json_object(content: str) -> Dict[str, Any]:
    """Scan text and decode the first complete JSON object."""
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
    # Try to extract from code block first
    for match in JSON_BLOCK_RE.findall(content):
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    # Try to extract direct JSON object
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    return _decode_first_json_object(content)
