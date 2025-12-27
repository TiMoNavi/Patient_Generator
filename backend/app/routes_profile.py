from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .profile_store import load_profile, patch_profile, revoke_field
from ..state_stream import state_stream_manager

router = APIRouter()


class ProfilePatch(BaseModel):
    user_id: str
    path: str
    value: object
    layer: Optional[str] = "confirmed"
    source: Optional[str] = "user_edit"
    confidence: Optional[float] = 1.0


class ProfileRevoke(BaseModel):
    user_id: str
    path: str
    reason: Optional[str] = "user_revoked"


@router.get("/profile")
def get_profile(user_id: str):
    try:
        return load_profile(user_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/profile")
def patch_profile_route(body: ProfilePatch):
    try:
        updated = patch_profile(
            user_id=body.user_id,
            path=body.path,
            value=body.value,
            layer=body.layer or "confirmed",
            source=body.source or "user_edit",
            confidence=body.confidence if body.confidence is not None else 1.0,
        )
        # broadcast update
        try:
            import asyncio

            asyncio.create_task(state_stream_manager.broadcast_profile(body.user_id))
        except RuntimeError:
            # no running loop, ignore
            pass
        return {"ok": True, "profile": updated}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profile/revoke")
def revoke_profile_route(body: ProfileRevoke):
    try:
        updated = revoke_field(
            user_id=body.user_id,
            path=body.path,
            reason=body.reason or "revoked",
        )
        try:
            import asyncio

            asyncio.create_task(state_stream_manager.broadcast_profile(body.user_id))
        except RuntimeError:
            pass
        return {"ok": True, "profile": updated}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
