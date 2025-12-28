import json
import os
import random
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from .chat_history import ChatHistoryStore
from .app.profile_store import load_profile, save_profile
from .schedule_store import load_schedule
from .openai_client import chat_once
from .coze_client import coze_stream

# 新版主动触发 Agent 位于 trigger_agent.py，保留此处其他 Agent。

chat_store = ChatHistoryStore()
DEBUG_MODE = os.getenv("PROACTIVE_DEBUG", "true").lower() == "true"
FORCE_EVENT = os.getenv("PROACTIVE_FORCE_EVENT")  # e.g., "post_meal_reminder" for testing
LENIENT_MODE = os.getenv("PROACTIVE_LENIENT", "false").lower() == "true"


class ProfileUpdateAgent:
    """Analyze latest dialog and update user-facing JSON files quietly."""

    prompt_template = (
        "你是 SugarBuddy 的画像同步器。输入：最近对话历史 chat_history（含 user/assistant 内容），现有画像 profile。\n"
        "请总结并输出一个 JSON，对应 data/users/{user_id}/ 下的文件，包含以下键（缺少可省略）：\n"
        "- profile_static: { summary: '一句总结', basic/medical/glucose_preferences/diet/lifestyle/personality/interests/assistant_prefs }\n"
        "- smalltalk: { summary: '一句总结', topics: [{key, text}]，保留前 8 条 }\n"
        "- health_record: { summary: '一句总结', conditions: [...], medications: [...], labs: [...] }\n"
        "- diet_2w: { summary: '一句总结', weeks: 最多近 2 周、每周含 days 列表，每天含 breakfast/lunch/dinner/notes }\n"
        "- recent_events: { summary_keywords: ['3-6 个关键词'], items: [{title, detail}...] 保留前 20 条 }\n"
        "- habits: { summary: '一句总结', routines: [...], rules: [...] }\n"
        "注意：\n"
        "1) 每个模块都加 summary 字段作为首要信息；\n"
        "2) 列表裁剪到小规模（topics<=8, items<=20, weeks<=2, days<=7）；\n"
        "3) 内容需与对话相关，未知就留空或省略该字段；\n"
        "4) 输出严谨 JSON，不要夹杂解释。"
    )

    def _write_user_file(self, user_id: str, name: str, data: Dict[str, Any]) -> None:
        base = Path(__file__).resolve().parent / "data" / "users" / user_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _trim_lists(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Limit list sizes to avoid front-end explosion."""
        def clip(lst, n): return lst[:n] if isinstance(lst, list) else lst
        if "smalltalk" in data and isinstance(data["smalltalk"], dict):
            data["smalltalk"]["topics"] = clip(data["smalltalk"].get("topics"), 8)
        if "recent_events" in data and isinstance(data["recent_events"], dict):
            data["recent_events"]["items"] = clip(data["recent_events"].get("items"), 20)
        if "diet_2w" in data and isinstance(data["diet_2w"], dict):
            weeks = data["diet_2w"].get("weeks")
            if isinstance(weeks, list):
                weeks = weeks[:2]
                for w in weeks:
                    if isinstance(w, dict) and isinstance(w.get("days"), list):
                        w["days"] = w["days"][:7]
                data["diet_2w"]["weeks"] = weeks
        return data

    def _extract_meals_from_text(self, text: str) -> Dict[str, str]:
        """Heuristic meal extraction from plain text."""
        meals: Dict[str, str] = {}
        if not text:
            return meals
        parts = [p.strip() for p in re.split(r"[，,。；;]+", text) if p.strip()]
        for seg in parts:
            lower = seg.lower()
            if any(k in seg for k in ("早餐", "早上", "早饭", "早午")):
                meals["breakfast"] = seg
            elif any(k in seg for k in ("中午", "午餐", "午饭")):
                meals["lunch"] = seg
            elif any(k in seg for k in ("晚餐", "晚饭", "晚上", "夜宵")):
                meals["dinner"] = seg
        return meals

    def _fallback_update_diet(self, user_id: str, latest_user_text: str) -> None:
        meals = self._extract_meals_from_text(latest_user_text)
        if not meals:
            return
        base = Path(__file__).resolve().parent / "data" / "users" / user_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / "diet_2w.json"
        try:
            diet = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            diet = {"schema_version": "1.0", "user_id": user_id, "summary": "", "weeks": []}
        # 使用用户时区（schedule 文件）决定日期，默认 +8
        today = self._local_today(user_id)
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        weeks = diet.get("weeks") or []
        target_week = None
        for w in weeks:
            if w.get("week_start") == week_start:
                target_week = w
                break
        if not target_week:
            target_week = {"week_start": week_start, "days": []}
            weeks.append(target_week)
            diet["weeks"] = weeks
        days = target_week.get("days") or []
        target_day = None
        for d in days:
            if d.get("date") == today.isoformat():
                target_day = d
                break
        if not target_day:
            target_day = {"date": today.isoformat()}
            days.append(target_day)
            target_week["days"] = days
        for meal_key, meal_val in meals.items():
            target_day[meal_key] = meal_val
        path.write_text(json.dumps(diet, ensure_ascii=False, indent=2), encoding="utf-8")

    def _fallback_update_glucose(self, user_id: str, latest_user_text: str) -> None:
        """Heuristic: extract血糖值写入 health_record.labs 最近一条。"""
        if not latest_user_text:
            return
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*mmol/?L", latest_user_text, re.IGNORECASE)
        if not m:
            # also catch “血糖为10” 模式
            m = re.search(r"血糖[^0-9]*([0-9]+(?:\.[0-9]+)?)", latest_user_text)
        if not m:
            return
        val = float(m.group(1))
        base = Path(__file__).resolve().parent / "data" / "users" / user_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / "health_record.json"
        try:
            hr = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            hr = {"schema_version": "1.0", "user_id": user_id}
        labs = hr.get("labs") or []
        today = datetime.now(timezone.utc).date().isoformat()
        # 避免同一天/同值重复写入
        for l in labs:
            if isinstance(l, dict) and str(l.get("name", "")).startswith("血糖") and l.get("date") == today:
                try:
                    if float(l.get("value", -1)) == val:
                        return
                except Exception:
                    return
        labs.insert(0, {
            "name": "血糖",
            "value": val,
            "unit": "mmol/L",
            "date": today,
            "note": "fallback_from_chat",
        })
        hr["labs"] = labs[:20]  # 保留最近 20 条
        if "summary" not in hr:
            hr["summary"] = f"最近血糖记录：{val} mmol/L ({today})"
        path.write_text(json.dumps(hr, ensure_ascii=False, indent=2), encoding="utf-8")

    def _local_today(self, user_id: str):
        try:
            sched = load_schedule(user_id)
            tz_name = sched.get("timezone")
            tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("Asia/Shanghai")
        except Exception:
            tz = timezone(timedelta(hours=8))
        return datetime.now(tz).date()

    def _has_today_meal(self, diet: Dict[str, Any], today_str: str) -> bool:
        weeks = diet.get("weeks") or []
        for w in weeks:
            days = w.get("days") or []
            for d in days:
                if d.get("date") == today_str:
                    return True
        return False

    def _has_today_glucose(self, hr: Dict[str, Any], today_str: str) -> bool:
        labs = hr.get("labs") or []
        for l in labs:
            if isinstance(l, dict) and l.get("date") == today_str and str(l.get("name")).startswith("血糖"):
                return True
        return False

    async def run(self, user_id: str) -> Optional[Dict[str, Any]]:
        if not self.prompt_template:
            return None

        history = chat_store.load(user_id)
        profile = load_profile(user_id)
        latest_user = next((m for m in reversed(history) if m.get("role") == "user" and isinstance(m.get("content"), str)), None)
        latest_user_text = latest_user.get("content", "") if latest_user else ""
        today_str = self._local_today(user_id).isoformat()
        payload = {"chat_history": history, "profile": profile}
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            text = await chat_once(
                system_prompt=self.prompt_template,
                user_prompt=user_prompt,
                max_tokens=800,
                temperature=0.2,
            )
        except Exception as exc:
            if DEBUG_MODE:
                print(f"[ProfileUpdate] call failed: {exc}")
            if latest_user_text:
                self._fallback_update_diet(user_id, latest_user_text)
                self._fallback_update_glucose(user_id, latest_user_text)
            return None
        if not (text or "").strip():
            if latest_user_text:
                self._fallback_update_diet(user_id, latest_user_text)
                self._fallback_update_glucose(user_id, latest_user_text)
            return None
        try:
            updated = json.loads(text)
        except Exception:
            if DEBUG_MODE:
                print(f"[ProfileUpdate] JSON parse error. raw='{(text or '')[:200]}'")
            if latest_user_text:
                self._fallback_update_diet(user_id, latest_user_text)
                self._fallback_update_glucose(user_id, latest_user_text)
            return None
        updated = self._trim_lists(updated)
        if DEBUG_MODE:
            try:
                print(f"[ProfileUpdate] updated keys: {list(updated.keys())}")
            except Exception:
                pass

        # profile_static -> also sync legacy profiles dir for backward compat
        if isinstance(updated.get("profile_static"), dict):
            self._write_user_file(user_id, "profile_static", updated["profile_static"])
            # legacy profile.json
            save_profile(user_id, updated.get("profile_static", {}))
        if isinstance(updated.get("smalltalk"), dict):
            self._write_user_file(user_id, "smalltalk", updated["smalltalk"])
        if isinstance(updated.get("health_record"), dict):
            self._write_user_file(user_id, "health_record", updated["health_record"])
        if isinstance(updated.get("diet_2w"), dict):
            self._write_user_file(user_id, "diet_2w", updated["diet_2w"])
        if isinstance(updated.get("recent_events"), dict):
            self._write_user_file(user_id, "recent_events", updated["recent_events"])
        if isinstance(updated.get("habits"), dict):
            self._write_user_file(user_id, "habits", updated["habits"])

        # Fallback: if diet未更新或未包含今日数据且最近用户消息包含饮食描述，补写到 diet_2w
        if latest_user_text:
            diet_obj = updated.get("diet_2w") if isinstance(updated.get("diet_2w"), dict) else None
            if (diet_obj is None) or (not self._has_today_meal(diet_obj, today_str)):
                self._fallback_update_diet(user_id, latest_user_text)
        # Fallback: 如果 labs 未更新或未包含今日血糖且最近用户消息包含血糖值，补写到 health_record.labs
        if latest_user_text:
            hr_obj = updated.get("health_record") if isinstance(updated.get("health_record"), dict) else None
            need_glucose = False
            if hr_obj is None:
                need_glucose = True
            elif not self._has_today_glucose(hr_obj, today_str):
                need_glucose = True
            if need_glucose:
                self._fallback_update_glucose(user_id, latest_user_text)

        return updated

class ScheduleTriggerAgent:
    """
    让 AI 从筛选后的列表中自主选择，同时强制去重，弱化时间偏置，不鼓励熬夜。
    """

    # 候选话题：健康关联的闲聊/互动/提醒，去除夜宵/熬夜导向
    CANDIDATES = [
        # 闲聊（健康关联）
        "闲聊-家庭与健康", "闲聊-工作放松", "闲聊-经济压力解压", "闲聊-运动兴趣",
        "闲聊-饮食小窍门", "闲聊-血糖小知识", "闲聊-健康小玩笑", "闲聊-周末规划",
        "闲聊-影视安利", "闲聊-音乐分享", "闲聊-厨房健康装备", "闲聊-低GI零食",
        # 游戏/互动
        "游戏-热量猜猜猜", "游戏-喝水打卡", "小游戏-问答", "小游戏-轻量挑战", "互动-话题",
        # 提醒/规划（温和）
        "提醒-补水", "提醒-轻微拉伸", "提醒-测血糖", "提醒-步行放松",
        "规划-轻食", "规划-零食", "规划-日程", "规划-血糖", "规划-用药",
        # 三餐/食材（不强调夜宵）
        "三餐-早餐建议", "三餐-午餐建议", "三餐-晚餐建议", "三餐-零食规划",
        "食材-推荐", "食物-建议",
        # 关怀/问候
        "关怀-压力", "关怀-久坐", "关怀-情绪低落",
        "问候-早安", "问候-晚安", "问候-周末", "里程碑", "复诊提醒",
    ]

    prompt_template = (
        "你是 SugarBuddy 的智能话题发起者。当前时间：{current_time}。\n"
        "用户画像概要：{user_summary}\n\n"
        "【任务目标】\n"
        "从下方【可选话题列表】中随机挑选一个健康相关的轻松话题发起对话。\n"
        "**可选话题列表**：{valid_options_json}\n\n"
        "【约束与风格】\n"
        "1) 只能从列表里选，不要捏造新话题；避免与最近 3 次触发重复。\n"
        "2) 口吻轻松像老友；可以带一句健康/血糖/饮食小提醒，但不要鼓励熬夜或夜宵，不要催睡。\n"
        "3) 主题可包含家庭/经济压力/工作作息/运动/饮食/血糖小知识/小玩笑/互动游戏等，保持健康关联。\n"
        "4) 输出严格为 JSON：{{'trigger': true, 'reason': '简短理由', 'trigger_context': '[TRIGGER:话题]\\n...内容'}}，不输出其他文本。"
    )

    def _get_recent_triggers(self, user_id: str, limit: int = 3) -> List[str]:
        """从历史记录中解析最近触发过的 [TRIGGER:xxx]"""
        try:
            history = chat_store.load(user_id)
            triggers = []
            # 倒序查找最近的 N 个触发词
            for msg in reversed(history):
                content = msg.get("content", "")
                if "[TRIGGER:" in content:
                    # 简单提取：[TRIGGER: xxx]
                    start = content.find("[TRIGGER:") + 9
                    end = content.find("]", start)
                    if start > 8 and end > start:
                        t_type = content[start:end].strip()
                        if t_type not in triggers:
                            triggers.append(t_type)
                if len(triggers) >= limit:
                    break
            return triggers
        except Exception:
            return []

    async def evaluate(self, user_id: str, now_iso: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
        # 1. 环境与时间准备
        profile = load_profile(user_id)
        now_dt = datetime.fromisoformat(now_iso) if now_iso else datetime.now(timezone.utc)
        # 简单固定 +8 时区，仅用于展示，不要据此偏向夜宵/熬夜话题
        local_dt = now_dt.astimezone(timezone(timedelta(hours=8)))
        current_time_str = local_dt.strftime("%H:%M")

        # 2. 【核心逻辑】Python端执行去重
        # 先获取最近用过的 3 个
        recent_triggers = self._get_recent_triggers(user_id, limit=3)
        
        # 计算剩下的可用列表
        valid_options = [t for t in self.CANDIDATES if t not in recent_triggers]
        
        # 兜底：如果全部都被排除了（极端情况），重置为全集，避免无话可说
        if not valid_options:
            valid_options = self.CANDIDATES[:]
            
        # 3. 乱序随机 (Shuffle) 
        # 虽然让 AI 选，但打乱顺序传给 AI 可以防止 AI 总是选列表第一个
        random.shuffle(valid_options)

        # 4. 组装 AI 输入
        # 提取一点用户画像供 AI 参考（如名字、偏好）
        user_summary = f"昵称：{profile.get('basic', {}).get('name', '朋友')}"
        if "diet" in profile:
            user_summary += f", 饮食偏好：{str(profile['diet'].get('preferences', ''))}"

        payload = {
            "current_time": current_time_str,
            "user_summary": user_summary,
            "valid_options_json": json.dumps(valid_options, ensure_ascii=False)
        }

        # 5. 调用 AI 进行决策和生成
        decision_raw = ""
        decision = None

        if self.prompt_template:
            # 渲染 Prompt
            system_prompt_filled = self.prompt_template.format(**payload)

            try:
                decision_raw = await chat_once(
                    system_prompt=system_prompt_filled,
                    user_prompt="请开始分析并输出 JSON",  # 简单触发即可
                    max_tokens=350,
                    temperature=0.5,  # 降低重复度和时间偏置
                )
            except Exception as exc:
                print(f"[ScheduleTrigger] call failed: {exc}")
                decision_raw = ""
                decision = None
            else:

                try:
                    decision = json.loads(decision_raw)
                except Exception:
                    # 宽松解析单引号 JSON
                    try:
                        import ast
                        decision = ast.literal_eval(decision_raw)
                    except Exception as e:
                        print(f"[ScheduleTrigger] JSON Parse Error: {e}")
                        decision = None
                try:
                    # 安全检查：确保 AI 真的选了列表里的词，并且格式正确
                    if decision and decision.get("trigger"):
                        ctx = decision.get("trigger_context", "")
                        # 如果 AI 忘了加 [TRIGGER:xxx] 头，或者加错了，这里可以做最后一次校验（可选）
                        # 但依赖 Prompt 强约束通常足够
                        pass
                except Exception as e:
                    print(f"[ScheduleTrigger] JSON Parse Error: {e}")
                    decision = None

        # Debug 信息
        if DEBUG_MODE:
            print(f"[proactive][debug] Time={current_time_str} Excluded={recent_triggers} ValidPoolSize={len(valid_options)}")
            print(f"[proactive][debug] AI Decision: {decision_raw[:100]}...")

        # 6. 错误兜底
        if not decision or not decision.get("trigger"):
            fallback_topic = random.choice(valid_options)
            return self._force_event(fallback_topic, local_dt, profile, reason="fallback_error"), decision_raw or ""

        return decision, decision_raw or ""

    def _force_event(self, event_type: str, local_dt: datetime, profile: Dict[str, Any], reason: str) -> Dict[str, Any]:
        """兜底生成函数"""
        uname = profile.get("basic", {}).get("name", "老友")
        ctx = f"[TRIGGER:{event_type}]\n时间：{local_dt.strftime('%H:%M')}\n（系统兜底发起）\n嘿 {uname}，聊聊这个话题放松一下？"
        return {
            "trigger": True,
            "reason": reason,
            "trigger_context": ctx,
            "trigger_id": f"{reason}-{local_dt.isoformat()}",
        }
    
    def _pick_event(self, local_dt: datetime, profile: Dict[str, Any], avoid: Optional[List[str]] = None) -> Dict[str, Any]:
        """在 Python 侧进行兜底随机选取，支持避开最近 N 个话题。"""
        avoid = avoid or []
        pool = [c for c in self.CANDIDATES if c not in avoid] or self.CANDIDATES[:]
        random.shuffle(pool)
        topic = random.choice(pool)
        return self._force_event(topic, local_dt, profile, reason="forced_pick")


class EventSelectorAgent:
    """Optional second-stage selector to confirm/adjust trigger event."""

    prompt_template = "[TODO: 在此填入事件选择/过滤指令]"

    async def select(self, user_id: str, proposed: Dict[str, Any], history: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        if not proposed or not proposed.get("trigger"):
            return None
        if not self.prompt_template or "[TODO" in self.prompt_template:
            return proposed

        payload = {
            "proposed": proposed,
            "recent_history": history[-10:] if history else [],
            "user_id": user_id,
        }
        try:
            text = await chat_once(
                system_prompt=self.prompt_template,
                user_prompt=json.dumps(payload, ensure_ascii=False),
                max_tokens=200,
                temperature=0.2,
            )
            decision = json.loads(text)
        except Exception:
            return proposed  # fail-open
        if not decision.get("trigger"):
            return None
        for k in ("trigger_context", "reason", "trigger_id"):
            if k in decision:
                proposed[k] = decision[k]
        return proposed


class FlexibleEventAgent:
    """Compose arbitrary trigger_context given event_type and slots."""

    prompt_template = "[TODO: 在此填入自由事件拼装/润色指令]"

    async def compose(self, event_type: str, slots: Dict[str, Any]) -> str:
        if not self.prompt_template or "[TODO" in self.prompt_template:
            lines = [f"[TRIGGER:{event_type}]"]
            time_val = slots.get("time") or datetime.now(timezone.utc).isoformat()  # type: ignore[name-defined]
            lines.append(f"时间：{time_val}")
            for k, v in slots.items():
                if k == "time":
                    continue
                lines.append(f"{k}：{v}")
            return "\n".join(lines)

        payload = {"event_type": event_type, "slots": slots}
        text = await chat_once(
            system_prompt=self.prompt_template,
            user_prompt=json.dumps(payload, ensure_ascii=False),
            max_tokens=200,
            temperature=0.4,
        )
        return (text or "").strip()


class PassiveContextAgent:
    """Load user JSON (profiles, records) and build a compact context snippet."""

    def __init__(self, max_topics: int = 6, max_events: int = 10) -> None:
        self.max_topics = max_topics
        self.max_events = max_events
        self.base = Path(__file__).resolve().parent / "data" / "users"

    def _load(self, user_id: str, name: str) -> Dict[str, Any]:
        """
        Load a user data file. Prefer JSON, but doctor Agent may emit markdown
        or plain text; in that case wrap the text into {"summary": "..."} so the
        downstream prompt仍能使用。
        """
        base_path = self.base / user_id / f"{name}.json"
        candidates = [base_path, base_path.with_suffix(".md"), base_path.with_suffix(".txt")]
        for path in candidates:
            if not path.exists():
                continue
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                try:
                    text = path.read_text(encoding="utf-8").strip()
                    if text:
                        return {"summary": text[:2000]}
                except Exception:
                    continue
        return {}

    def build(self, user_id: str) -> str:
        ps = self._load(user_id, "profile_static")
        hr = self._load(user_id, "health_record")
        diet = self._load(user_id, "diet_2w")
        events = self._load(user_id, "recent_events")
        habits = self._load(user_id, "habits")
        st = self._load(user_id, "smalltalk")

        lines: List[str] = ["[USER_DATA]"]
        if ps.get("summary"):
            lines.append(f"画像总结：{ps.get('summary')}")
        if hr.get("summary"):
            lines.append(f"病症总结：{hr.get('summary')}")
        meds = (hr.get("medications") or [])[:3] if isinstance(hr, dict) else []
        if meds:
            lines.append("用药：" + "；".join([str(m.get('name') or '') for m in meds if isinstance(m, dict)]))
        if diet.get("summary"):
            lines.append(f"饮食总结：{diet.get('summary')}")
        kws = (events.get("summary_keywords") or [])[:self.max_events] if isinstance(events, dict) else []
        if kws:
            lines.append("事件关键词：" + "、".join(map(str, kws)))
        routines = (habits.get("routines") or [])[:3] if isinstance(habits, dict) else []
        if routines:
            lines.append("习惯：" + "；".join([str(r.get('name') or '') for r in routines if isinstance(r, dict)]))
        topics = (st.get("topics") or [])[:self.max_topics] if isinstance(st, dict) else []
        if topics:
            lines.append("杂谈：" + "；".join([str(t.get('key') or '') for t in topics if isinstance(t, dict)]))

        return "\n".join([l for l in lines if l.strip()])


class ResponseGeneratorAgent:
    """Generate assistant replies for passive or proactive flows."""

    prompt_template = "[TODO: 在此填入老友/医生双模式人设指令]"

    def _serialize(self, messages: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content") or ""
            if not content:
                continue
            lines.append(f"{role.upper()}: {content}")
        return "\n".join(lines)

    async def generate(
        self,
        user_id: str,
        *,
        extra_system: Optional[str] = None,
        mode: str = "passive",
        stream: bool = True,
        profile: Optional[Dict[str, Any]] = None,
        include_user_data: bool = False,
        context_agent: Optional[PassiveContextAgent] = None,
    ):
        history = chat_store.load(user_id)
        profile_block = None
        if profile:
            profile_block = "[PROFILE_JSON]\n" + json.dumps(profile, ensure_ascii=False)
        user_data_block = None
        if include_user_data:
            try:
                agent = context_agent or PassiveContextAgent()
                user_data_block = agent.build(user_id)
            except Exception:
                user_data_block = None
        merged_extra = None
        blocks = [b for b in [extra_system, profile_block, user_data_block] if b]
        if blocks:
            merged_extra = "\n\n".join(blocks)

        messages = chat_store.to_messages(history, system_prompt=self.prompt_template, extra_system=merged_extra)
        prompt_text = self._serialize(messages)
        if stream:
            async for event, data in coze_stream(prompt_text):
                yield event, data
        else:
            text = await chat_once(
                system_prompt=self.prompt_template,
                user_prompt=prompt_text,
                max_tokens=400,
                temperature=0.6,
            )
            yield "done", (text or "").strip()
