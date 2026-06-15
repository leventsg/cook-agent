"""多模态识别提示词."""

VISION_ANALYSIS_PROMPT_TEMPLATE = """你是多模态助手，需要根据对话判断用户意图。

近期对话：
{recent_text}

当前用户消息：
{current_message}

如果用户在记录饮食或识别食物，请输出严格 JSON：
{{
  "meal_type": "breakfast/lunch/dinner/snack 或 null",
  "items": [
    {{
      "food_name": "食物名称（中文）",
      "weight_g": 数值,
      "unit": "份/个/碗等单位或 null",
      "calories": 数值,
      "protein": 数值,
      "fat": 数值,
      "carbs": 数值
    }}
  ]
}}

规则：
1. 能区分多个食物时必须拆分为多个 items。
2. 数值无法判断时给一个合理的估计值。
3. 只输出 JSON，不要解释。

如果不是饮食相关，请输出 JSON：
{{
  "description": "对图片的简短描述",
  "is_food_related": false,
  "confidence": 0.0
}}"""
