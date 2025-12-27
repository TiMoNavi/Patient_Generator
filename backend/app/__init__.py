import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..agents import ProfileUpdateAgent, ResponseGeneratorAgent, PassiveContextAgent
from ..chat_history import ChatHistoryStore
from .routes_profile import router as profile_router
from ..routes_schedule import router as schedule_router
from ..state_stream import state_stream_manager, state_stream_router
from .profile_store import load_profile
from ..proactive_loop import ProactiveLoop

load_dotenv()

BACKEND_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BACKEND_DIR / "static"
STATIC_INDEX = FRONTEND_DIR / "index.html"
DEFAULT_USER_ID = os.getenv("PROACTIVE_USER_ID", "u_demo_young_male")
PROACTIVE_ENABLED = os.getenv("PROACTIVE_ENABLED", "true").lower() == "true"
PROACTIVE_TICK_SECONDS = int(os.getenv("PROACTIVE_TICK_SECONDS", "30"))
PROACTIVE_COOLDOWN_SECONDS = int(os.getenv("PROACTIVE_COOLDOWN_SECONDS", "1800"))
PROACTIVE_JITTER_SECONDS = int(os.getenv("PROACTIVE_JITTER_SECONDS", "0"))

chat_store = ChatHistoryStore()
response_agent = ResponseGeneratorAgent()
user_data_agent = PassiveContextAgent()
profile_agent = ProfileUpdateAgent()
proactive_loop: Optional[ProactiveLoop] = None

app = FastAPI(title="Glucose Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(profile_router, prefix="/api")
app.include_router(schedule_router, prefix="/api")
app.include_router(state_stream_router, prefix="/api")
# Serve frontend assets from backend/static
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
app.mount("/bundles", StaticFiles(directory=FRONTEND_DIR / "bundles"), name="bundles")
app.mount("/app", StaticFiles(directory=FRONTEND_DIR / "app"), name="app")
app.mount("/data", StaticFiles(directory=BACKEND_DIR / "data"), name="data")

# Backward-compat placeholder endpoints for new frontend optional data
@app.get("/api/local/manifest/{user_id}")
async def local_manifest(user_id: str):
    return {"files": {}, "base_path": f"/data/users/{user_id}/"}


@app.get("/api/local/{name}/{user_id}")
async def local_generic(name: str, user_id: str):
    return {}


class ChatRequest(BaseModel):
    text: str


@app.on_event("startup")
async def _startup():
    await state_stream_manager.start()
    global proactive_loop
    if PROACTIVE_ENABLED:
        proactive_loop = ProactiveLoop(
            user_id=DEFAULT_USER_ID,
            interval_seconds=PROACTIVE_TICK_SECONDS,
            cooldown_seconds=PROACTIVE_COOLDOWN_SECONDS,
            jitter_seconds=PROACTIVE_JITTER_SECONDS,
        )
        await proactive_loop.start()


@app.on_event("shutdown")
async def _shutdown():
    if proactive_loop:
        await proactive_loop.stop()
    await state_stream_manager.stop()


@app.get("/")
async def read_index():
    if not STATIC_INDEX.exists():
        raise HTTPException(status_code=500, detail="index.html not found")
    return FileResponse(STATIC_INDEX)


@app.post("/api/chat")
async def chat(body: ChatRequest, user_id: str = DEFAULT_USER_ID):
    """Non-streaming chat; primarily for debugging."""
    try:
        chat_store.append(user_id, "user", body.text, visible=True, source="user")
        try:
            await state_stream_manager.broadcast_chat(user_id=user_id, role="user", text=body.text, meta={"mode": "passive"})
        except Exception:
            pass
        profile = load_profile(user_id)
        text_parts = []
        async for event, data in response_agent.generate(
            user_id,
            mode="passive",
            stream=True,
            profile=profile,
            include_user_data=True,
            context_agent=user_data_agent,
        ):
            name = (event or "").lower()
            if name in ("message", "answer"):
                if data is not None:
                    text_parts.append(str(data))
            elif name in ("done", "interrupt"):
                break
        reply = "".join(text_parts).strip()
        if reply:
            chat_store.append(
                user_id,
                "assistant",
                reply,
                visible=True,
                source="ResponseGeneratorAgent",
                meta={"mode": "passive"},
            )
            try:
                await state_stream_manager.broadcast_chat(
                    user_id=user_id, role="assistant", text=reply, meta={"mode": "passive"}
                )
            except Exception:
                pass
        try:
            asyncio.create_task(profile_agent.run(user_id))
        except RuntimeError:
            pass
        return {"reply": reply}
    except Exception as exc:  # surfaced as gateway error
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest, user_id: str = DEFAULT_USER_ID):
    chat_store.append(user_id, "user", body.text, visible=True, source="user")
    profile = load_profile(user_id)

    async def event_source() -> AsyncGenerator[str, None]:
        assistant_text = ""
        try:
            async for event, data in response_agent.generate(
                user_id,
                mode="passive",
                stream=True,
                profile=profile,
                include_user_data=True,
                context_agent=user_data_agent,
            ):
                name = (event or "").lower()
                if name in ("message", "answer"):
                    if data is None:
                        continue
                    delta = str(data)
                    assistant_text += delta
                    payload = {"text": delta}
                    yield f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif name == "interrupt":
                    yield f"event: interrupt\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"
                    break
                elif name == "done":
                    yield "event: done\ndata: [DONE]\n\n"
                    break
                else:
                    yield f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if assistant_text:
                chat_store.append(
                    user_id,
                    "assistant",
                    assistant_text,
                    visible=True,
                    source="ResponseGeneratorAgent",
                    meta={"mode": "passive"},
                )
                try:
                    await state_stream_manager.broadcast_chat(
                        user_id=user_id, role="assistant", text=assistant_text, meta={"mode": "passive"}
                    )
                except Exception:
                    pass
                try:
                    asyncio.create_task(profile_agent.run(user_id))
                except RuntimeError:
                    pass

    headers = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
    return StreamingResponse(event_source(), media_type="text/event-stream", headers=headers)


@app.get("/api/chat/history")
async def chat_history(user_id: str = DEFAULT_USER_ID, limit: int = 100):
    """Return recent visible chat messages for UI hydration."""
    try:
        records = chat_store.load(user_id, limit=limit)
        visible = [r for r in records if r.get("visible", True)]
        return {"messages": visible}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
