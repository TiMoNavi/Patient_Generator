import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .openai_client import chat_once
from .chat_history import ChatHistoryStore
from .app.profile_store import load_profile
from .schedule_store import load_schedule

chat_store = ChatHistoryStore()


def _safe_load(path: Path) -> Dict[str, Any]:
    """
    Load JSON if present; fall back to .md/.txt or raw text as {"summary": text}.
    The doctor Agent sometimes writes markdown notes instead of JSON, so we
    normalize to a dict with a summary field when JSON parsing fails.
    """
    candidates = [path]
    if path.suffix == ".json":
        candidates += [path.with_suffix(".md"), path.with_suffix(".txt")]
    for p in candidates:
        if not p.exists():
            continue
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            try:
                text = p.read_text(encoding="utf-8").strip()
                if text:
                    return {"summary": text[:2000]}
            except Exception:
                pass
    return {}


class ScheduleTriggerAgent:
    """
    主动触发调度员：结合用户画像/档案 JSON，选择更契合的主动话题。
    """

    BASE_CANDIDATES = [
        # 基础健康/提醒
        "提醒-补水", "提醒-轻微拉伸", "提醒-测血糖", "提醒-步行放松",
        "用药-提醒", "规划-日程", "规划-血糖", "规划-用药",
        "三餐-早餐建议", "三餐-午餐建议", "三餐-晚餐建议", "三餐-零食规划",
        "食材-推荐", "食物-建议",
        # 闲聊/互动
        "闲聊-家庭与健康", "闲聊-工作放松", "闲聊-经济压力解压", "闲聊-运动兴趣",
        "闲聊-饮食小窍门", "闲聊-血糖小知识", "闲聊-健康小玩笑",
        "互动-话题", "小游戏-问答", "小游戏-轻量挑战",
        # 关怀/问候
        "关怀-压力", "关怀-情绪低落", "问候-早安", "问候-晚安", "问候-周末",
    ]

    prompt_template = (
        "你是 SugarBuddy 主动触发调度员。\n"
        "输入：当前时间 {current_time}，可选话题列表 options（已打乱），最近 3 次触发 recent_triggers，"
        "以及用户画像摘要 data_brief（健康档案、用药、饮食记录、近期事件、习惯）。\n"
        "任务：从 options 中选择 1 个话题（严格只选列表内），输出 JSON：\n"
        "{{'trigger': true, 'reason': '简短理由', 'event_type': '话题名', 'trigger_context': '按示例的 Markdown', 'trigger_id': '可选'}}。\n"
        "trigger_context 必须符合 SugarBuddy 事件格式：\n"
        "[事件类型]\n时间：YYYY-MM-DD HH:MM\n天气：<可选>\n用户位置：<可选>\n用户状态：<可选>\n其他上下文：<可选>\n"
        "示例：[提醒（测血糖）]\\n时间：2024-01-15 12:00\\n用户位置：公司\\n血糖目标：控制在7以下\n"
        "规则：\n"
        "1) 不要重复 recent_triggers；\n"
        "2) 结合 data_brief 里的线索（病症/用药/饮食/近期事件/习惯）填入上下文；\n"
        "3) 口吻友好，不鼓励熬夜或夜宵；不要催促睡觉；\n"
        "4) 如果数据不足，可随机选择任意健康/闲聊话题，但仍需在 options 中。"
    )

    def _load_user_data(self, user_id: str) -> Dict[str, Any]:
        base = Path(__file__).resolve().parent / "data" / "users" / user_id
        return {
            "profile_static": _safe_load(base / "profile_static.json"),
            "health_record": _safe_load(base / "health_record.json"),
            "diet_2w": _safe_load(base / "diet_2w.json"),
            "recent_events": _safe_load(base / "recent_events.json"),
            "habits": _safe_load(base / "habits.json"),
            "smalltalk": _safe_load(base / "smalltalk.json"),
        }

    def _recent_triggers(self, user_id: str, limit: int = 3) -> List[str]:
        history = chat_store.load(user_id)
        triggers: List[str] = []
        for msg in reversed(history):
            content = msg.get("content", "")
            if "[TRIGGER:" in content:
                start = content.find("[TRIGGER:") + 9
                end = content.find("]", start)
                if start > 8 and end > start:
                    t = content[start:end].strip()
                    if t and t not in triggers:
                        triggers.append(t)
            if len(triggers) >= limit:
                break
        return triggers

    def _data_options(self, data: Dict[str, Any]) -> Tuple[List[str], Dict[str, str]]:
        """Return dynamic candidates and hint map."""
        opts: List[str] = []
        hints: Dict[str, str] = {}

        # 健康档案
        hr = data.get("health_record") or {}
        conds = hr.get("conditions") or []
        for c in conds[:3]:
            if not isinstance(c, dict):
                continue
            name = str(c.get("name") or "健康关怀")[:12]
            topic = f"关怀-{name}"
            opts.append(topic)
            hints[topic] = f"病情：{name}；状态：{c.get('status') or ''}"
        meds = hr.get("medications") or []
        for m in meds[:2]:
            if not isinstance(m, dict):
                continue
            name = str(m.get("name") or "用药")[:12]
            topic = f"用药-{name}提醒"
            opts.append(topic)
            hints[topic] = f"用药：{name}；剂量：{m.get('dose') or ''}"

        # 饮食记录
        diet = data.get("diet_2w") or {}
        if diet.get("summary"):
            topic = "饮食-近餐回顾"
            opts.append(topic)
            hints[topic] = str(diet.get("summary"))[:100]

        # 近期事件关键词
        revents = data.get("recent_events") or {}
        kws = revents.get("summary_keywords") or []
        for kw in kws[:4]:
            topic = f"闲聊-{str(kw)[:12]}"
            opts.append(topic)
            hints[topic] = f"近期事件关键词：{kw}"

        # 习惯
        habits = data.get("habits") or {}
        routines = habits.get("routines") or []
        for r in routines[:3]:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "习惯")[:12]
            topic = f"习惯-{name}"
            opts.append(topic)
            hints[topic] = f"习惯：{name}"

        # 杂谈
        st = data.get("smalltalk") or {}
        if st.get("summary"):
            topic = "闲聊-近期八卦"
            opts.append(topic)
            hints[topic] = str(st.get("summary"))[:100]

        return opts, hints

    def _build_brief(self, data: Dict[str, Any]) -> str:
        pieces = []
        hr = data.get("health_record") or {}
        if hr.get("summary"):
            pieces.append(f"健康：{hr.get('summary')}")
        diet = data.get("diet_2w") or {}
        if diet.get("summary"):
            pieces.append(f"饮食：{diet.get('summary')}")
        revents = data.get("recent_events") or {}
        if revents.get("summary_keywords"):
            pieces.append(f"事件关键词：{', '.join(map(str, revents.get('summary_keywords')[:4]))}")
        habits = data.get("habits") or {}
        if habits.get("summary"):
            pieces.append(f"习惯：{habits.get('summary')}")
        st = data.get("smalltalk") or {}
        if st.get("summary"):
            pieces.append(f"杂谈：{st.get('summary')}")
        return "；".join(pieces)[:300]

    def _force_event(self, event_type: str, local_dt: datetime, profile: Dict[str, Any], hint: Optional[str]) -> Dict[str, Any]:
        uname = profile.get("basic", {}).get("name", "老友")
        ctx = [f"[{event_type}]", f"时间：{local_dt.strftime('%Y-%m-%d %H:%M')}"]
        if hint:
            ctx.append(f"线索：{hint}")
        ctx.append(f"嗨 {uname}，聊聊这个话题？")
        return {
            "trigger": True,
            "reason": "forced_pick",
            "trigger_context": "\n".join(ctx),
            "trigger_id": f"forced-{local_dt.isoformat()}",
        }

    def _pick_event(self, local_dt: datetime, profile: Dict[str, Any], avoid: Optional[List[str]] = None) -> Dict[str, Any]:
        """Python 侧兜底随机选择，避开 avoid 列表。"""
        avoid = avoid or []
        user_data = self._load_user_data(profile.get("basic", {}).get("user_id", {}).get("value", "") or "")
        data_opts, hints = self._data_options(user_data)
        pool = list(set(self.BASE_CANDIDATES + data_opts))
        pool = [p for p in pool if p not in avoid] or pool or ["闲聊-工作放松"]
        topic = random.choice(pool)
        hint = hints.get(topic)
        return self._force_event(topic, local_dt, profile, hint)

    async def evaluate(self, user_id: str, now_iso: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
        profile = load_profile(user_id)
        user_data = self._load_user_data(user_id)

        now_dt = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
        # 简单固定 +8 时区
        local_dt = now_dt.astimezone(timezone(timedelta(hours=8)))
        current_time_str = local_dt.strftime("%H:%M")

        recent_triggers = self._recent_triggers(user_id, limit=3)
        data_options, hint_map = self._data_options(user_data)

        options = list(set(self.BASE_CANDIDATES + data_options))
        options = [o for o in options if o not in recent_triggers] or options
        random.shuffle(options)

        payload = {
            "current_time": current_time_str,
            "valid_options_json": json.dumps(options, ensure_ascii=False),
            "recent_triggers": recent_triggers,
            "data_brief": self._build_brief(user_data),
        }

        decision_raw = ""
        decision = None
        if self.prompt_template:
            system_prompt_filled = self.prompt_template.format(**payload)
            try:
                decision_raw = await chat_once(
                    system_prompt=system_prompt_filled,
                    user_prompt="请严格输出 JSON，不要解释。",
                    max_tokens=300,
                    temperature=0.5,
                )
            except Exception as exc:
                print(f"[ScheduleTrigger] call failed: {exc}")
                decision_raw = ""
                decision = None
            else:
                try:
                    decision = json.loads(decision_raw)
                except Exception:
                    try:
                        import ast
                        decision = ast.literal_eval(decision_raw)
                    except Exception as e:
                        print(f"[ScheduleTrigger] JSON Parse Error: {e}")
                        decision = None

        if decision and decision.get("trigger"):
            ctx = decision.get("trigger_context") or ""
            t = decision.get("trigger_id") or ""
            # 如果 AI 未利用 hint，则补一行线索
            event_type = None
            # 兼容 [TRIGGER:] 或 [xxx]
            if "[TRIGGER:" in ctx:
                try:
                    start = ctx.index("[TRIGGER:") + 9
                    end = ctx.index("]", start)
                    event_type = ctx[start:end].strip()
                except Exception:
                    event_type = None
            elif "[" in ctx and "]" in ctx:
                try:
                    start = ctx.index("[") + 1
                    end = ctx.index("]", start)
                    event_type = ctx[start:end].strip()
                except Exception:
                    event_type = None
            if event_type and hint_map.get(event_type) and hint_map[event_type] not in ctx:
                decision["trigger_context"] = ctx.strip() + f"\n线索：{hint_map[event_type]}"
            if not t:
                decision["trigger_id"] = f"{local_dt.isoformat()}"
            if event_type and not decision.get("event_type"):
                decision["event_type"] = event_type
            return decision, decision_raw or ""

        # 兜底随机
        pick = random.choice(options)
        hint = hint_map.get(pick)
        return self._force_event(pick, local_dt, profile, hint), decision_raw or ""
