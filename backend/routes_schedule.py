from fastapi import APIRouter, HTTPException

from .schedule_store import load_schedule
from .state_stream import state_stream_manager

router = APIRouter()


@router.get("/schedule")
def get_schedule(user_id: str):
    try:
        sched = load_schedule(user_id)
        return sched
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
