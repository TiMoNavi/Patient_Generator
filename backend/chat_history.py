import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

# Simple append-only chat history store.
DATA_DIR = Path(__file__).resolve().parent / "data" / "state"
CHAT_DIR = DATA_DIR / "chat_history"


class ChatHistoryStore:
    def load(self, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        path = CHAT_DIR / f"{user_id}.jsonl"
        if not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        records: List[Dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except Exception:
                continue
        return records

    def append(
        self,
        user_id: str,
        role: str,
        content: str,
        *,
        visible: bool = True,
        source: str = "user",
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        CHAT_DIR.mkdir(parents=True, exist_ok=True)
        record: Dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "content": content,
            "visible": visible,
            "source": source,
            "meta": meta or {},
        }
        path = CHAT_DIR / f"{user_id}.jsonl"
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def to_messages(
        self,
        history: List[Dict[str, Any]],
        *,
        system_prompt: str = "",
        extra_system: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        if extra_system:
            msgs.append({"role": "system", "content": extra_system})
        for rec in history:
            content = rec.get("content")
            role = rec.get("role") or "user"
            if content is None:
                continue
            msgs.append({"role": role, "content": str(content)})
        return msgs

