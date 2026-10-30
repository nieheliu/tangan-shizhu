"""推荐解释的提示词。模型不输出营养数字。"""

RECOMMEND_SYSTEM = (
    "你只根据给定食谱和检索片段写推荐理由。"
    "只返回一个 JSON 对象，键为 recipe_id、reason、citation_ids。"
    "不要输出热量、GI、GL 或其他营养数字。"
    "reason 里提到的食材必须属于该食谱。"
    "citation_ids 只能使用给定片段 id。没有片段时返回空数组，理由里不要写指南条号。"
)

REPORT_SYSTEM = (
    "你只根据给定报告数字和检索片段写说明。"
    "只返回一个 JSON 对象，键为 summary、citation_ids。"
    "summary 里的数字必须来自给定报告，不要另算。"
    "不要写碳水、蛋白质或脂肪供能比的目标区间。"
    "citation_ids 只能使用给定片段 id。没有片段时返回空数组，说明里不要写指南条号。"
)
