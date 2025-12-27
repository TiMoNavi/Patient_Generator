import asyncio
import json
import os
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List

from .agents import ProfileUpdateAgent, ResponseGeneratorAgent, chat_store
from .trigger_agent import ScheduleTriggerAgent
from .agents import EventSelectorAgent
from .app.profile_store import load_profile
from .schedule_store import load_schedule
from .state_stream import state_stream_manager

STATE_PATH = Path(__file__).resolve().parent / "data" / "state" / "proactive_state.json"
TEST_MODE = os.getenv("PROACTIVE_TEST_MODE", "false").lower() == "true"
EVENT_MIN_OVERRIDE = os.getenv("PROACTIVE_EVENT_MIN_SECONDS")
IGNORE_HISTORY = os.getenv("PROACTIVE_IGNORE_HISTORY", "false").lower() == "true"
FALLBACK_ENABLED = os.getenv("PROACTIVE_FALLBACK_ENABLED", "true").lower() == "true"
INJECT_RATE = float(os.getenv("PROACTIVE_INJECT_RATE", "0.7"))
ASSISTANT_RANDOM_RATE = float(os.getenv("PROACTIVE_ASSISTANT_RANDOM_RATE", "0.5"))


def _load_state() -> Dict[str, Any]:
    if not STATE_PATH.exists():
        return {"enabled": True, "cooldown_until": None, "last_proactive_at": None}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"enabled": True, "cooldown_until": None, "last_proactive_at": None}


def _save_state(state: Dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


class ProactiveLoop:
    """Periodic proactive trigger loop."""

    def __init__(
        self,
        user_id: str,
        interval_seconds: int = 30,
        cooldown_seconds: int = 1800,
        jitter_seconds: int = 0,
    ) -> None:
        self.user_id = user_id
        self.interval = interval_seconds
        self.cooldown_seconds = cooldown_seconds
        self.jitter_seconds = jitter_seconds
        self.task: Optional[asyncio.Task] = None
        self.trigger_agent = ScheduleTriggerAgent()
        self.selector_agent = EventSelectorAgent()
        self.response_agent = ResponseGeneratorAgent()
        self.profile_agent = ProfileUpdateAgent()
        self.inject_rate = max(0.0, min(1.0, INJECT_RATE))
        self.assistant_random_rate = max(0.0, min(1.0, ASSISTANT_RANDOM_RATE))
        # Minimum per-event intervals (seconds) to avoid spam even if model keeps triggering.
        # TEMP_SHORT_INTERVAL: to aid debugging, default to 10s min interval. Restore after testing.
        default_min = 10
        if TEST_MODE:
            default_min = 5
        self.event_min_intervals = {
            "missed_reminder": default_min,
            "morning_greeting": default_min,
            "meal_reminder": default_min,
            "post_meal_reminder": default_min,
            "evening_checkin": default_min,
            "weekend_checkin": default_min,
            "stress_check": default_min,
            "health_alert": default_min,
            "weather_care": default_min,
            "fallback_chat": default_min,
            "三餐规划建议": default_min,
            "夜宵规划建议": default_min,
            "规划-餐单": default_min,
            "规划-零食": default_min,
            "规划-日程": default_min,
            "规划-血糖": default_min,
            "规划-用药": default_min,
            "用药-提醒": default_min,
            "三餐-早餐建议": default_min,
            "三餐-午餐建议": default_min,
            "三餐-晚餐建议": default_min,
            "三餐-零食规划": default_min,
        }
        if EVENT_MIN_OVERRIDE:
            try:
                val = int(EVENT_MIN_OVERRIDE)
                for k in list(self.event_min_intervals.keys()):
                    self.event_min_intervals[k] = val
                print(f"[proactive] EVENT_MIN_OVERRIDE applied: {val}s for all events")
            except Exception:
                print(f"[proactive] invalid EVENT_MIN_OVERRIDE={EVENT_MIN_OVERRIDE}, using defaults")

    async def start(self) -> None:
        if self.task:
            return
        self.task = asyncio.create_task(self._run(), name=f"proactive-loop-{self.user_id}")

    async def stop(self) -> None:
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None

    async def _run(self) -> None:
        while True:
            sleep_for = self.interval + (random.randint(0, self.jitter_seconds) if self.jitter_seconds > 0 else 0)
            await asyncio.sleep(sleep_for)
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                import traceback
                print("[proactive] error", exc)
                traceback.print_exc()

    async def _tick(self) -> None:
        state = _load_state()
        if not state.get("enabled", True):
            return

        now = datetime.now(timezone.utc)
        cooldown_until = state.get("cooldown_until")
        if cooldown_until:
            try:
                if now < datetime.fromisoformat(cooldown_until):
                    return
            except Exception:
                pass

        # Prepare local time for variety/forcing decisions.
        try:
            schedule = load_schedule(self.user_id)
            tz_name = schedule.get("timezone") if isinstance(schedule, dict) else None
            try:
                tz = ZoneInfo(tz_name) if tz_name else ZoneInfo("Asia/Shanghai")  # type: ignore[name-defined]
            except Exception:
                tz = timezone(timedelta(hours=8))
        except Exception:
            schedule = {}
            tz = timezone(timedelta(hours=8))
        local_dt = now.astimezone(tz)
        profile = load_profile(self.user_id)

        decision, decision_raw = await self.trigger_agent.evaluate(self.user_id, now_iso=now.isoformat())
        if not decision or not isinstance(decision, dict) or not decision.get("trigger") or not decision.get("trigger_context"):
            # 强制兜底，避免后续缺少 trigger 导致报错
            decision = self.trigger_agent._pick_event(local_dt, profile, avoid=self._recent_trigger_types(max_count=3))

        # Optional second-stage selection to filter/adjust event choice.
        history = chat_store.load(self.user_id)
        decision = await self.selector_agent.select(self.user_id, decision, history=history)
        if not decision or not isinstance(decision, dict) or not decision.get("trigger") or not decision.get("trigger_context"):
            decision = self.trigger_agent._pick_event(local_dt, profile, avoid=self._recent_trigger_types(max_count=3))
        if not decision or not decision.get("trigger") or not decision.get("trigger_context"):
            print(f"[proactive] invalid decision after selector user={self.user_id} raw='{(decision_raw or '')[:200]}'")
            return

        trigger_meta = {
            "mode": "proactive",
            "trigger_reason": decision.get("reason"),
            "trigger_id": decision.get("trigger_id") or str(uuid.uuid4()),
        }
        trigger_ctx = decision.get("trigger_context") or ""
        trigger_type = self._parse_trigger_type(trigger_ctx)

        # 如果上下文与最近的系统注入重复，尝试换一个话题再试一次
        if self._recent_same_context(trigger_ctx):
            alt = self.trigger_agent._pick_event(local_dt, profile, avoid=recent_types + ([trigger_type] if trigger_type else []))
            trigger_ctx = alt.get("trigger_context") or trigger_ctx
            decision = alt
            trigger_type = self._parse_trigger_type(trigger_ctx)
            trigger_meta["trigger_reason"] = alt.get("reason") or trigger_meta.get("trigger_reason")
            trigger_meta["trigger_id"] = alt.get("trigger_id") or trigger_meta["trigger_id"]

        recent_types = self._recent_trigger_types(max_count=3)
        if trigger_type and trigger_type in recent_types:
            alt = self.trigger_agent._pick_event(local_dt, profile, avoid=recent_types)
            trigger_ctx = alt.get("trigger_context") or trigger_ctx
            decision = alt
            trigger_type = self._parse_trigger_type(trigger_ctx)
            trigger_meta["reason"] = alt.get("reason") or trigger_meta["reason"]
        if trigger_type and self._recent_trigger_count(trigger_type, max_count=8) >= 2:
            alt = self.trigger_agent._pick_event(local_dt, profile, avoid=recent_types + [trigger_type])
            trigger_ctx = alt.get("trigger_context") or trigger_ctx
            decision = alt
            trigger_type = self._parse_trigger_type(trigger_ctx)
            trigger_meta["reason"] = alt.get("reason") or trigger_meta.get("trigger_reason")
        if trigger_type:
            min_interval = self.event_min_intervals.get(trigger_type, self.event_min_intervals.get("fallback_chat", 10))
            if self._recent_triggered(self.user_id, trigger_type, min_interval):
                # Instead of skipping, force a different event to increase diversity.
                alt = self.trigger_agent._pick_event(local_dt, profile, avoid=[trigger_type] + recent_types)
                trigger_ctx = alt.get("trigger_context") or trigger_ctx
                decision = alt
                trigger_type = self._parse_trigger_type(trigger_ctx)
                trigger_meta["reason"] = alt.get("reason") or trigger_meta["reason"]
        print(f"[proactive] firing type={trigger_type or '<unknown>'} reason={trigger_meta['trigger_reason']} id={trigger_meta['trigger_id']} user={self.user_id}")

        # 按概率决定是否写入 system_inject；避免过多重复注入
        do_inject = random.random() < self.inject_rate
        if do_inject:
            chat_store.append(
                self.user_id,
                role="system_inject",
                content=trigger_ctx,
                visible=False,
                source="ScheduleTriggerAgent",
                meta=trigger_meta,
            )
        else:
            trigger_meta["inject_skipped"] = True

        profile = load_profile(self.user_id)
        text_parts = []
        # 决定 assistant 是否使用触发上下文（提高随机性）
        extra_for_assistant = trigger_ctx if do_inject else None
        if random.random() < self.assistant_random_rate:
            extra_for_assistant = None
        async for event, data in self.response_agent.generate(
            self.user_id,
            extra_system=extra_for_assistant,
            mode="proactive",
            stream=True,
            profile=profile,
        ):
            name = (event or "").lower()
            if name in ("message", "answer"):
                text_parts.append(str(data))
        reply_text = "".join(text_parts).strip()

        if reply_text:
            # 如果与最近助手回复重复，则替换为轻量陪聊句，避免重复血糖长文
            if self._recent_same_reply(reply_text, lookback=6):
                alt_replies = [
                    "刚刚的血糖提醒已经收到，这会儿想聊点轻松的吗？比如最近在看什么剧？",
                    "记录一下刚才的血糖情况，顺便放松下：最近有去散步或做拉伸吗？",
                    "健康提醒已记下～要不要换个话题，聊聊你的饮食或运动计划？",
                    "好的，血糖情况关注中。如果想转换心情，可以分享下今天的趣事。",
                ]
                reply_text = random.choice(alt_replies)

            chat_store.append(
                self.user_id,
                role="assistant",
                content=reply_text,
                visible=True,
                source="ResponseGeneratorAgent",
                meta=trigger_meta,
            )
            try:
                await state_stream_manager.broadcast_chat(
                    user_id=self.user_id, role="assistant", text=reply_text, meta=trigger_meta
                )
                print(f"[proactive] broadcast_chat len={len(reply_text)} meta={trigger_meta}")
            except Exception:
                pass
            try:
                asyncio.create_task(self.profile_agent.run(self.user_id))
            except RuntimeError:
                pass
        else:
            # 调试兜底：模型无响应也输出一条可见消息，便于前端观察链路。
            debug_text = "[调试] 主动触发后模型未返回内容，请检查上游日志。"
            chat_store.append(
                self.user_id,
                role="assistant",
                content=debug_text,
                visible=True,
                source="ResponseGeneratorAgent",
                meta=trigger_meta,
            )
            try:
                await state_stream_manager.broadcast_chat(
                    user_id=self.user_id, role="assistant", text=debug_text, meta=trigger_meta
                )
                print(f"[proactive] broadcast_chat (debug placeholder) meta={trigger_meta}")
            except Exception:
                pass

        state["last_proactive_at"] = now.isoformat()
        state["cooldown_until"] = (now + timedelta(seconds=self.cooldown_seconds)).isoformat()
        _save_state(state)

    def _parse_trigger_type(self, ctx: str) -> Optional[str]:
        if not ctx:
            return None
        # 兼容 [TRIGGER:xxx] 和 [xxx] 形式
        m = re.search(r"\[TRIGGER:([^\]\s]+)\]", ctx)
        if m:
            return m.group(1).strip()
        m2 = re.search(r"\[([^\]\s]+)\]", ctx)
        if m2:
            return m2.group(1).strip()
        return None

    def _recent_triggered(self, user_id: str, trigger: str, within_seconds: int) -> bool:
        if IGNORE_HISTORY:
            return False
        history = chat_store.load(user_id)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
        for rec in reversed(history):
            ts = rec.get("ts")
            if not ts:
                continue
            try:
                t = datetime.fromisoformat(ts)
            except Exception:
                continue
            if t < cutoff:
                break
            content = rec.get("content") or ""
            if isinstance(content, str) and f"[TRIGGER:{trigger}]" in content:
                return True
        return False

    def _recent_trigger_types(self, max_count: int = 5) -> List[str]:
        history = chat_store.load(self.user_id)
        types: List[str] = []
        for rec in reversed(history):
            content = rec.get("content") or ""
            if not isinstance(content, str):
                continue
            m = re.search(r"\[TRIGGER:([^\]\s]+)\]", content)
            if not m:
                continue
            t = m.group(1).strip()
            if t:
                types.append(t)
            if len(types) >= max_count:
                break
        return types

    def _recent_trigger_count(self, trigger: str, max_count: int = 10) -> int:
        """Count how many times the same trigger type appeared recently."""
        if not trigger:
            return 0
        history = chat_store.load(self.user_id)
        count = 0
        seen = 0
        for rec in reversed(history):
            content = rec.get("content") or ""
            if not isinstance(content, str):
                continue
            if f"[{trigger}]" in content or f"[TRIGGER:{trigger}]" in content:
                count += 1
            seen += 1
            if seen >= max_count:
                break
        return count

    def _recent_same_context(self, ctx: str, lookback: int = 5) -> bool:
        """Return True if the same system_inject content appeared recently."""
        if not ctx:
            return False
        history = chat_store.load(self.user_id, limit=lookback * 5)
        count = 0
        for rec in reversed(history):
            if rec.get("role") != "system_inject":
                continue
            if rec.get("content") == ctx:
                return True
            count += 1
            if count >= lookback:
                break
        return False

    def _recent_same_reply(self, reply: str, lookback: int = 5) -> bool:
        """Return True if identical assistant reply appeared recently."""
        if not reply:
            return False
        history = chat_store.load(self.user_id, limit=lookback * 5)
        count = 0
        for rec in reversed(history):
            if rec.get("role") != "assistant":
                continue
            if rec.get("content") == reply:
                return True
            count += 1
            if count >= lookback:
                break
        return False

    async def _send_fallback_chat(self, now: datetime) -> None:
        """Send a friendly proactive nudge without TRIGGER tag as last-resort fallback."""
        # Avoid spamming fallback_chat if fired very recently.
        if self._recent_triggered(self.user_id, "fallback_chat", self.event_min_intervals.get("fallback_chat", 10)):
            return
        messages = [
            "最近还好吗？有新的血糖记录、饮食或运动情况想聊聊吗？我随时在～",
            "好久没听你分享近况了，如果有血糖/饮食/睡眠的问题，可以告诉我，一起看看怎么调。",
            "想关心一下你的状态：今天感觉如何？需要我帮忙整理一下控糖小建议吗？",
        ]
        text = random.choice(messages)
        meta = {"mode": "proactive", "trigger_reason": "fallback_chat", "trigger_id": f"fallback-{now.isoformat()}"}
        chat_store.append(self.user_id, role="assistant", content=text, visible=True, source="FallbackAgent", meta=meta)
        try:
            await state_stream_manager.broadcast_chat(
                user_id=self.user_id, role="assistant", text=text, meta=meta
            )
        except Exception:
            pass
        try:
            asyncio.create_task(self.profile_agent.run(self.user_id))
        except RuntimeError:
            pass
