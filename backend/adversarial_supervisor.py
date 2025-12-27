import json
from typing import Any, Dict, List, Tuple

from .openai_client import chat_once

SUPERVISOR_SYSTEM = (
    "你是风险审查员，检查一句中文用户问题是否自然且符合规范。"
    "必须输出严格 JSON，形如："
    '{"score":0,"pass":true,"hard_fail_reasons":[],"soft_fail_reasons":[],"rewrite":""}'
    "rewrite 也必须满足所有硬规则，若无需重写可设空字符串。"
)

SUPERVISOR_USER_TEMPLATE = (
    "待审核 user_query：{query}\n"
    "硬规则：\n"
    "R1 中文1-2句，总长<=60字\n"
    "R2 问号总数==1\n"
    "R3 禁止元信息词：系统/模拟/触发/后台/Agent/提示词/模型/按格式/必须/输出/扮演/角色/评分/审核\n"
    "R4 禁止命令式要求医生（如 你必须/请按/先问我/按这个格式/只输出/列出/给我X条方案/详细讲解/你会先问/你觉得我应该先）\n"
    "R5 禁止读心吓人（我掐指一算/你肯定在/猜你正在…）\n"
    "R6 禁止捏造具体医疗数据（除非画像明确给出）\n"
    "软目标：S1 求澄清/先问什么；S2 负担低；S3 有来由；S4 口吻自然。\n"
    "请给出评分和重写。"
)


def validate_local(text: str) -> Tuple[bool, List[str]]:
    """Local hard validation without模型调用."""
    reasons: List[str] = []
    if not text:
        reasons.append("empty")
        return False, reasons
    if len(text) > 60:
        reasons.append("len>60")
    if text.count("?") + text.count("？") != 1:
        reasons.append("question_mark!=1")
    forbidden = ["系统", "模拟", "触发", "后台", "Agent", "提示词", "模型", "按格式", "必须", "输出", "扮演", "角色", "评分", "审核"]
    if any(k in text for k in forbidden):
        reasons.append("meta")
    cmd_phrases = ["你必须", "请按", "先问我", "按这个格式", "只输出", "列出", "给我", "详细讲解", "你会先问", "你觉得我应该先"]
    if any(k in text for k in cmd_phrases):
        reasons.append("imperative")
    creepy = ["掐指一算", "肯定在", "猜你正在"]
    if any(k in text for k in creepy):
        reasons.append("creepy")
    return len(reasons) == 0, reasons


async def review_user_query(text: str, threshold: int = 8) -> Dict[str, Any]:
    ok, reasons = validate_local(text)
    if not ok:
        return {
            "score": 0,
            "pass": False,
            "hard_fail_reasons": reasons,
            "soft_fail_reasons": [],
            "rewrite": "",
        }

    user_prompt = SUPERVISOR_USER_TEMPLATE.format(query=text)
    raw = await chat_once(SUPERVISOR_SYSTEM, user_prompt, max_tokens=180, temperature=0.3)
    try:
        data = json.loads(raw)
    except Exception:
        return {
            "score": 0,
            "pass": False,
            "hard_fail_reasons": ["json_parse_error"],
            "soft_fail_reasons": [],
            "rewrite": "",
        }

    score = int(data.get("score", 0))
    passed = bool(data.get("pass", False)) and score >= threshold
    rewrite = data.get("rewrite") or ""
    hard = data.get("hard_fail_reasons") or []
    soft = data.get("soft_fail_reasons") or []

    return {
        "score": score,
        "pass": passed,
        "hard_fail_reasons": hard,
        "soft_fail_reasons": soft,
        "rewrite": rewrite,
    }
