import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import settings
from app.context import build_history_messages
from app.db import AsyncSessionLocal
from app.grounding import ground
from app.judge import run_judge
from app.persona_fanout import load_personas, run_fanout
from app.redis_client import get_redis
from app.session_store import (
    append_history,
    get_session,
    create_session,
    increment_requestion,
    reset_session,
    save_last_grounding,
)
from app.synthesizer import synthesize
from app.termination import (
    check_and_auto_unlock,
    cooldown_remaining,
    lock_with_cooldown,
    pick_termination_message,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


# ── 요청/응답 스키마 ─────────────────────────────────────────

class AskRequest(BaseModel):
    question: str


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


# ── SSE 헬퍼 ─────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── /ask — 전체 파이프라인 SSE 스트리밍 §5.2 ─────────────────

@router.post("/{session_id}/ask")
async def ask(session_id: str, body: AskRequest):
    """질문 제출 → judge → (grounding) → persona fan-out → synthesis. §5.2

    브라우저 EventSource는 GET 전용이므로, 클라이언트는
    fetch + ReadableStream으로 직접 파싱해야 한다.
    """
    redis = get_redis()

    # 스트리밍 시작 전 동기 검사 (HTTP 에러는 여기서만 가능)
    session = await get_session(redis, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    if session.get("locked"):
        # 쿨다운 자동 해제 체크
        auto_unlocked = await check_and_auto_unlock(redis, session_id)
        if not auto_unlocked:
            remaining = cooldown_remaining(session.get("locked_at"))
            detail = "Session is locked. POST /sessions/{id}/reset to recover."
            if remaining > 0:
                detail = f"Session is locked. Auto-unlocks in {remaining}s."
            raise HTTPException(status_code=423, detail=detail)

    async def stream():
        try:
            # ── 재질문 카운터 증가 ────────────────────────────
            count = await increment_requestion(redis, session_id)

            if count > settings.MAX_REQUESTION_COUNT:
                await lock_with_cooldown(redis, session_id)
                remaining = settings.COOLDOWN_SEC if settings.COOLDOWN_SEC > 0 else -1
                yield _sse("locked", {
                    "message": pick_termination_message(),
                    "reset_path": f"/sessions/{session_id}/reset",
                    "cooldown_sec": remaining,
                })
                yield _sse("done", {"requestion_count": count})
                return

            async with AsyncSessionLocal() as db:
                # ── Judge ─────────────────────────────────────
                judge_out = await run_judge(body.question, db)

                grounded_flag = judge_out.needs_fresh_context and judge_out.verdict == "subjective"
                yield _sse("judge", {
                    "verdict": judge_out.verdict,
                    "selected_personas": judge_out.selected_personas,
                    "grounded": grounded_flag,
                })

                if judge_out.verdict == "out_of_scope":
                    await append_history(redis, session_id, "user", body.question)
                    await append_history(redis, session_id, "assistant", judge_out.reason)
                    yield _sse("done", {"requestion_count": count})
                    return

                # ── Grounding ─────────────────────────────────
                grounding = None
                if judge_out.needs_fresh_context and judge_out.search_query:
                    grounding = await ground(judge_out.search_query)
                    if grounding:
                        yield _sse("sources", {
                            "sources": [
                                {"title": s.title, "url": s.url}
                                for s in grounding.sources
                            ],
                            "summary": grounding.summary,
                        })

                # ── 컨텍스트 윈도우 빌드 (§9.1) ──────────────────
                current_session = await get_session(redis, session_id)
                history = await build_history_messages(
                    history=current_session.get("history", []),
                    last_grounded_summary=current_session.get("last_grounded_summary"),
                )

                # ── Grounding 저장 (중복 검색 방지) ──────────────
                if grounding:
                    await save_last_grounding(redis, session_id, grounding.summary)

                # ── Persona fan-out ───────────────────────────
                personas = await load_personas(judge_out.selected_personas, db)
                answers = []
                order = 0

                async for answer in run_fanout(personas, body.question, grounding, history):
                    order += 1
                    answers.append(answer)
                    yield _sse("persona_answer", {
                        "persona_name": answer.persona_name,
                        "answer": answer.answer,
                        "order": order,
                    })

                # ── Synthesis ─────────────────────────────────
                synthesis = await synthesize(body.question, answers, grounding, history)
                yield _sse("synthesis", {
                    "conclusion": synthesis.conclusion,
                    "forced_pick": synthesis.forced_pick,
                    "key_reasons": synthesis.key_reasons,
                })

                # ── 히스토리 저장 ─────────────────────────────
                await append_history(redis, session_id, "user", body.question)
                await append_history(redis, session_id, "assistant", synthesis.conclusion)

                yield _sse("done", {"requestion_count": count})

        except Exception as exc:
            logger.exception("Pipeline error for session %s", session_id)
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 버퍼링 비활성화
        },
    )
