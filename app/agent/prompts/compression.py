"""对话压缩提示词."""

COMPRESS_SYSTEM_PROMPT = """你是 CookAgent 的对话摘要助手。
目标：保留用户目标、关键信息、已确认结论与未解决问题，方便后续继续完成任务。"""

COMPRESS_USER_PROMPT_TEMPLATE = """请将以下对话内容压缩为简洁摘要：

{messages_text}

{previous_summary}

要求：
1. 保留任务目标、关键事实、结论与待办事项。
2. 删除闲聊和重复内容。
3. 不要添加未出现的信息。"""
