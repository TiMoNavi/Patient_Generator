import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)  # prefer backend/.env
load_dotenv()  # fallback to defaults/parent

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _client() -> AsyncOpenAI:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    return AsyncOpenAI(api_key=OPENAI_API_KEY)


async def chat_once(system_prompt: str, user_prompt: str, max_tokens: int = 200, temperature: float = 0.6) -> str:
    """Generic helper to get a single completion text."""
    client = _client()
    resp = await client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = (resp.choices[0].message.content or "").strip()
    return text


async def generate_user_query(raw_prompt: str) -> str:
    """Generate a short user-like query (<=60 chars) for proactive trigger."""
    system = (
        "你输出的内容必须是一句中文问题，<=60字，只含一个问号，"
        "不能包含系统/指令/格式/模拟等字眼，不能命令医生，只能像用户自然发问。"
    )
    return (await chat_once(system_prompt=system, user_prompt=raw_prompt, max_tokens=80, temperature=0.5))[:120]
