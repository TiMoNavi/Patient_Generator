import json
from pathlib import Path
from typing import Dict

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SCHEDULE_DIR = DATA_DIR / "schedules"


def load_schedule(user_id: str) -> Dict:
    path = SCHEDULE_DIR / f"{user_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"schedule not found for user_id={user_id}")
    return json.loads(path.read_text(encoding="utf-8"))
