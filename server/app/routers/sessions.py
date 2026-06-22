from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.redis_client import get_redis
from app.session_store import create_session, get_session, reset_session

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── 응답 스키마 ──────────────────────────────────────────────

class SessionCreated(BaseModel):
    session_id: str


class SessionState(BaseModel):
    session_id: str
    requestion_count: int
    locked: bool
    created_at: str


# ── 헬퍼 ─────────────────────────────────────────────────────

async def _get_or_404(session_id: str) -> dict:
    data = await get_session(get_redis(), session_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return data


# ── 엔드포인트 ───────────────────────────────────────────────

@router.post("", status_code=201, response_model=SessionCreated)
async def create():
    """새 세션 생성. §5.1"""
    session_id = await create_session(get_redis())
    return SessionCreated(session_id=session_id)


@router.get("/{session_id}", response_model=SessionState)
async def get(session_id: str):
    """세션 상태 조회 (디버그용)."""
    data = await _get_or_404(session_id)
    return SessionState(
        session_id=session_id,
        requestion_count=data["requestion_count"],
        locked=data["locked"],
        created_at=data["created_at"],
    )


@router.post("/{session_id}/reset", response_model=SessionState)
async def reset(session_id: str):
    """잠긴 세션 복구 — 카운터·lock 초기화. §5.3"""
    data = await _get_or_404(session_id)
    await reset_session(get_redis(), session_id)
    return SessionState(
        session_id=session_id,
        requestion_count=0,
        locked=False,
        created_at=data["created_at"],
    )
