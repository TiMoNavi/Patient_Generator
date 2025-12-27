"""
Quick pipeline probe for SugarBuddy.

Runs against a live uvicorn instance (default http://127.0.0.1:8000) and checks:
1) /api/chat/history visibility
2) /api/state/stream SSE events for a short window

Usage:
    python debug_sse.py            # use defaults
    BASE_URL=http://localhost:8000 USER_ID=u_demo_young_male python debug_sse.py
"""

import asyncio
import os
from typing import List, Tuple

import httpx


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
USER_ID = os.getenv("USER_ID", "u_demo_young_male")


async def fetch_history(client: httpx.AsyncClient) -> None:
    url = f"{BASE_URL}/api/chat/history"
    r = await client.get(url, params={"user_id": USER_ID})
    r.raise_for_status()
    data = r.json()
    msgs = data.get("messages") or []
    print(f"[history] {len(msgs)} messages")
    for m in msgs[-5:]:
        role = m.get("role")
        text = (m.get("content") or "").replace("\n", " ")
        visible = m.get("visible", True)
        print(f"  - {role:<9} visible={visible} text={text[:80]}")


async def listen_sse(client: httpx.AsyncClient, seconds: int = 15) -> List[Tuple[str, str]]:
    url = f"{BASE_URL}/api/state/stream"
    params = {"user_id": USER_ID}
    events: List[Tuple[str, str]] = []
    print(f"[sse] connecting to {url} for {seconds}s ...")
    async with client.stream("GET", url, params=params, timeout=None) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                events.append((line[6:].strip(), ""))
                print(f"[sse] {events[-1][0]}")
            elif line.startswith("data:"):
                if events:
                    ev, _ = events[-1]
                    events[-1] = (ev, line[5:].strip())
                    print(f"[sse] data ({ev}): {line[5:].strip()[:120]}")
            if len(events) > 0 and (events[-1][0] == "chat_message" or events[-1][0] == "state_error"):
                # stop early if we already saw a chat message or error
                break
    return events


async def main() -> None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        await fetch_history(client)
        await listen_sse(client, seconds=15)


if __name__ == "__main__":
    asyncio.run(main())
