import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR.parent.parent / "data"
PROFILE_DIR = DATA_DIR / "profiles"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _field_value(
    value: Any,
    layer: str = "confirmed",
    source: str = "api",
    confidence: float = 1.0,
    revoked: bool = False,
) -> Dict[str, Any]:
    return {
        "value": value,
        "layer": layer,
        "confidence": confidence,
        "source": source,
        "updated_at": _now_iso(),
        "revoked": revoked,
    }


def _walk_to_parent(profile: Dict[str, Any], path: str) -> Tuple[Dict[str, Any], str]:
    parts = path.split(".")
    if not parts:
        raise ValueError("path is empty")
    *parents, leaf = parts
    node = profile
    for part in parents:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    return node, leaf


def load_profile(user_id: str) -> Dict[str, Any]:
    profile_path = PROFILE_DIR / f"{user_id}.json"
    if not profile_path.exists():
        # Bootstrap a minimal profile to avoid missing-file failures.
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        profile: Dict[str, Any] = {
            "basic": {
                "user_id": _field_value(user_id, source="bootstrap"),
            },
            "medical": {},
            "glucose_preferences": {},
            "diet": {},
            "lifestyle": {},
            "personality": {},
            "interests": {},
            "assistant_prefs": {},
        }
        save_profile(user_id, profile)
        return profile
    return json.loads(profile_path.read_text(encoding="utf-8"))


def save_profile(user_id: str, profile: Dict[str, Any]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    profile_path = PROFILE_DIR / f"{user_id}.json"
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def patch_profile(
    user_id: str,
    path: str,
    value: Any,
    layer: str = "confirmed",
    source: str = "api_patch",
    confidence: float = 1.0,
) -> Dict[str, Any]:
    profile = load_profile(user_id)
    parent, leaf = _walk_to_parent(profile, path)
    parent[leaf] = _field_value(value=value, layer=layer, source=source, confidence=confidence, revoked=False)
    save_profile(user_id, profile)
    return profile


def revoke_field(user_id: str, path: str, reason: str = "revoked") -> Dict[str, Any]:
    profile = load_profile(user_id)
    parent, leaf = _walk_to_parent(profile, path)
    if leaf not in parent or not isinstance(parent[leaf], dict):
        raise KeyError(f"field not found at path '{path}'")
    current = parent[leaf]
    current["revoked"] = True
    current["source"] = reason
    current["updated_at"] = _now_iso()
    parent[leaf] = current
    save_profile(user_id, profile)
    return profile


def ensure_profile_valid(profile: Dict[str, Any]) -> bool:
    # Placeholder for schema validation (jsonschema can be added later if needed).
    return isinstance(profile, dict)
