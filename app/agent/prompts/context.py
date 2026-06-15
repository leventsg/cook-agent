"""上下文追加提示词."""

USER_ID_PROMPT_TEMPLATE = """

## 用户 ID
{user_id}
请勿在回答中提及用户 ID。
涉及日期或时间推断时，必须先调用 datetime 工具获取当前时间。"""
