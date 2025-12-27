import asyncio
import json
import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .app.profile_store import load_profile
from .schedule_store import load_schedule

DEFAULT_USER_ID = os.getenv("PROACTIVE_USER_ID", "u_demo_young_male")


class StateStreamManager:
    """Minimal SSE manager for profile/schedule updates."""

    def __init__(self) -> None:
        self._connections: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
        async with self._lock:
            queues = [q for lst in self._connections.values() for q in lst]
            self._connections.clear()
        for q in queues:
            try:
                q.put_nowait((None, None))
            except Exception:
                pass

    async def subscribe(self, user_id: str) -> AsyncGenerator[str, None]:
        """Yield SSE event blocks for a given user."""
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._connections.setdefault(user_id, []).append(queue)
        print(f"[state_stream] subscribe user={user_id} total={len(self._connections.get(user_id, []))}")
        try:
            await self._enqueue_snapshot(queue, user_id)
            while True:
                event, payload = await queue.get()
                if event is None:
                    break
                data = json.dumps(payload, ensure_ascii=False)
                yield f"event: {event}\ndata: {data}\n\n"
        finally:
            async with self._lock:
                if user_id in self._connections and queue in self._connections[user_id]:
                    self._connections[user_id].remove(queue)
                if user_id in self._connections and not self._connections[user_id]:
                    self._connections.pop(user_id, None)
            print(f"[state_stream] unsubscribe user={user_id}")

    async def _enqueue_snapshot(self, queue: asyncio.Queue, user_id: str) -> None:
        try:
            profile = load_profile(user_id)
            await queue.put(("profile_update", {"user_id": user_id, "profile": profile}))
        except Exception as exc:
            await queue.put(("state_error", {"message": f"profile load failed: {exc}"}))
        try:
            schedule = load_schedule(user_id)
            await queue.put(("schedule_update", {"user_id": user_id, "schedule": schedule}))
        except FileNotFoundError:
            await queue.put(("schedule_update", {"user_id": user_id, "schedule": None}))
        except Exception as exc:
            await queue.put(("state_error", {"message": f"schedule load failed: {exc}"}))

    async def _broadcast(self, event: str, payload: Dict[str, Any], *, user_id: Optional[str] = None) -> None:
        async with self._lock:
            if user_id:
                targets = list(self._connections.get(user_id, []))
            else:
                targets = [q for lst in self._connections.values() for q in lst]
            # fallback: if specific user has no listeners, broadcast to all listeners
            if not targets:
                targets = [q for lst in self._connections.values() for q in lst]
        if not targets:
            print(f"[state_stream] broadcast dropped event={event} user={user_id} (no listeners)")
            return
        else:
            print(f"[state_stream] broadcast event={event} user={user_id} listeners={len(targets)}")
        for q in targets:
            await q.put((event, payload))

    async def broadcast_profile(self, user_id: str) -> None:
        """Push profile update to all listeners for this user."""
        try:
            profile = load_profile(user_id)
        except Exception as exc:
            await self._broadcast("state_error", {"message": f"profile load failed: {exc}"}, user_id=user_id)
            return
        await self._broadcast("profile_update", {"user_id": user_id, "profile": profile}, user_id=user_id)

    async def broadcast_schedule(self, user_id: str) -> None:
        """Push schedule update to all listeners for this user."""
        try:
            schedule = load_schedule(user_id)
        except FileNotFoundError:
            await self._broadcast("schedule_update", {"user_id": user_id, "schedule": None}, user_id=user_id)
            return
        except Exception as exc:
            await self._broadcast("state_error", {"message": f"schedule load failed: {exc}"}, user_id=user_id)
            return
        await self._broadcast("schedule_update", {"user_id": user_id, "schedule": schedule}, user_id=user_id)

    async def broadcast_chat(self, *, user_id: str, role: str, text: str, meta: Optional[Dict[str, Any]] = None) -> None:
        """Push chat message (typically proactive assistant) to UI listeners."""
        await self._broadcast(
            "chat_message",
            {"user_id": user_id, "role": role, "text": text, "meta": meta or {}},
            user_id=user_id,
        )


state_stream_manager = StateStreamManager()
state_stream_router = APIRouter()


@state_stream_router.get("/state/stream")
async def state_stream(user_id: str = DEFAULT_USER_ID):
    async def event_source() -> AsyncGenerator[str, None]:
        async for block in state_stream_manager.subscribe(user_id):
            yield block

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_source(), media_type="text/event-stream", headers=headers)


@state_stream_router.get("/proactive/stream")
async def proactive_stream(user_id: str = DEFAULT_USER_ID):
    """Compatible SSE for new frontend; forwards proactive chat_message as proactive_delta/done."""
    queue: asyncio.Queue = asyncio.Queue()
    async with state_stream_manager._lock:
        state_stream_manager._connections.setdefault(user_id, []).append(queue)

    async def event_source() -> AsyncGenerator[str, None]:
        try:
            while True:
                event, payload = await queue.get()
                if event is None:
                    break
                if event != "chat_message":
                    continue
                if not isinstance(payload, dict):
                    continue
                meta = payload.get("meta") or {}
                if meta.get("mode") != "proactive":
                    continue
                text = payload.get("text") or ""
                if not text:
                    continue
                data = json.dumps({"delta": text}, ensure_ascii=False)
                yield f"event: proactive_delta\ndata: {data}\n\n"
                yield "event: proactive_done\n\n"
        finally:
            async with state_stream_manager._lock:
                lst = state_stream_manager._connections.get(user_id, [])
                if queue in lst:
                    lst.remove(queue)
                if not lst and user_id in state_stream_manager._connections:
                    state_stream_manager._connections.pop(user_id, None)

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_source(), media_type="text/event-stream", headers=headers)
