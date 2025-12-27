"""Coze client helper providing SSE streaming compatible with specified payload."""
import json
import os
from pathlib import Path
from typing import Any, AsyncIterator, Tuple

import httpx
from dotenv import load_dotenv

ENV_PATH = Path(__file__).resolve().parent / ".env"
CONFIG_PATH = Path(__file__).resolve().parent / "config.json"
TOKEN_PATH = Path(__file__).resolve().parent.parent / "token.txt"

# Coze streaming endpoint defaults (can be overridden by env/config).
DEFAULT_COZE_ENDPOINT = "https://xphk5ks65m.coze.site/stream_run"
DEFAULT_COZE_PROJECT_ID = "7588430537056862242"

# Load .env from the backend folder first, then fall back to default lookup.
load_dotenv(dotenv_path=ENV_PATH)
load_dotenv()

def _load_config_json() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        # Ignore config parse errors; fall back to other sources.
        return {}


def _read_token_file() -> str:
    if not TOKEN_PATH.exists():
        return ""
    try:
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


_CONFIG = _load_config_json()
_FILE_TOKEN = _read_token_file()

COZE_ENDPOINT = os.getenv("COZE_ENDPOINT") or _CONFIG.get("COZE_ENDPOINT") or DEFAULT_COZE_ENDPOINT
COZE_TOKEN = os.getenv("COZE_TOKEN") or _CONFIG.get("COZE_TOKEN") or _FILE_TOKEN
COZE_PROJECT_ID = str(os.getenv("COZE_PROJECT_ID") or _CONFIG.get("COZE_PROJECT_ID") or DEFAULT_COZE_PROJECT_ID).strip()
COZE_DEBUG = os.getenv("COZE_DEBUG", "false").lower() == "true"


def _auth_header() -> str:
    """Return Authorization header value with Bearer prefix."""
    if not COZE_TOKEN:
        return ""
    token = COZE_TOKEN.strip()
    if not token:
        return ""
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def _env_ready() -> bool:
    return bool(COZE_ENDPOINT and _auth_header() and COZE_PROJECT_ID)


def _payload(user_text: str) -> dict:
    return {
        "content": {
            "query": {
                "prompt": [
                    {
                        "type": "text",
                        "content": {
                            "text": user_text,
                        },
                    }
                ]
            }
        },
        "type": "query",
        "project_id": COZE_PROJECT_ID,
    }


def _parse_data(data_str: str) -> Any:
    if not data_str:
        return ""
    try:
        return json.loads(data_str)
    except ValueError:
        return data_str


def _extract_message_text(data: Any) -> str:
    if isinstance(data, dict):
        # Common fields
        for k in ("answer", "text", "output_text", "response", "result", "message"):
            v = data.get(k)
            if isinstance(v, str) and v:
                return v
        content = data.get("content")
        if isinstance(content, dict):
            for k in ("answer", "text", "output_text", "response", "result", "message"):
                v = content.get(k)
                if isinstance(v, str) and v:
                    return v
            # Some providers wrap a single message in list
            msgs = content.get("messages")
            if isinstance(msgs, list) and msgs:
                first = msgs[0]
                if isinstance(first, dict):
                    for k in ("text", "content", "answer", "output_text"):
                        v = first.get(k)
                        if isinstance(v, str) and v:
                            return v
        # For structured dicts without text/answer, do not emit noise.
        return ""
    if data is not None:
        return str(data)
    return ""


async def coze_stream(user_text: str) -> AsyncIterator[Tuple[str, Any]]:
    """Yield (event, data) tuples parsed from Coze SSE stream."""
    if not _env_ready():
        yield "Message", f"[mock stream] Echo: {user_text}"
        yield "Done", None
        return

    headers = {
        "Content-Type": "application/json",
        "Authorization": _auth_header(),
    }
    timeout = httpx.Timeout(60.0, connect=30.0)
    payload = _payload(user_text)
    if COZE_DEBUG:
        masked_auth = (_auth_header()[:12] + "...") if _auth_header() else "<missing>"
        print(f"[coze] POST {COZE_ENDPOINT} project={COZE_PROJECT_ID} auth={masked_auth} text={user_text}")

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", COZE_ENDPOINT, headers=headers, json=payload
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                snippet = body.decode("utf-8", errors="ignore")[:300]
                raise RuntimeError(
                    f"Upstream error {response.status_code}: {snippet}"
                )
            else:
                print(f"[coze] upstream 200, streaming...")

            event_name = "message"
            data_lines = []

            async for raw_line in response.aiter_lines():
                line = raw_line.strip()
                if line and COZE_DEBUG:
                    print(f"[coze][raw] {line}")
                if not line:
                    if not data_lines:
                        event_name = "message"
                        continue

                    data_str = "\n".join(data_lines)
                    parsed = _parse_data(data_str)
                    canonical = (event_name or "message").strip().lower()

                    if canonical in ("message", "answer"):
                        text = _extract_message_text(parsed)
                        if not text:
                            event_name = "message"
                            data_lines = []
                            continue
                        yield "Message", text
                    elif canonical == "message_end":
                        text = _extract_message_text(parsed)
                        if text:
                            yield "Message", text
                        yield "Done", parsed
                        return
                    elif canonical == "interrupt":
                        yield "Interrupt", parsed
                    elif canonical == "done":
                        yield "Done", parsed
                        return
                    else:
                        yield event_name or "message", parsed

                    event_name = "message"
                    data_lines = []
                    continue

                if line.startswith("event:"):
                    event_name = line[len("event:") :].strip() or event_name
                elif line.startswith("data:"):
                    data_lines.append(line[len("data:") :].strip())

            if data_lines:
                data_str = "\n".join(data_lines)
                parsed = _parse_data(data_str)
                canonical = (event_name or "message").strip().lower()
                if canonical in ("message", "answer"):
                    text = _extract_message_text(parsed)
                    if text:
                        yield "Message", text
                elif canonical == "message_end":
                    text = _extract_message_text(parsed)
                    if text:
                        yield "Message", text
                    yield "Done", parsed
                    return
                elif canonical == "interrupt":
                    yield "Interrupt", parsed
                elif canonical == "done":
                    yield "Done", parsed
                else:
                    yield event_name or "message", parsed
