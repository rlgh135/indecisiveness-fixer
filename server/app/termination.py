"""재질문 한도 초과 — §10

시그니처 기능: 한도 초과 시 재수없는 말투로 종료 + 리셋 경로 제공.
영구 비활성화 금지 — COOLDOWN_SEC > 0 이면 자동 해제, 0 이면 수동 리셋.
"""
import random
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.config import settings
from app.session_store import get_session, _save  # noqa: PLC2701

# ── 재수없는 말투 메시지 풀 ───────────────────────────────────

_MESSAGES = [
    "결정을 못 하는 게 특기냐? 이미 답 다 나왔다. 그냥 해라.",
    "또 물어봐? 처음부터 다 말해줬잖아. 귀가 없냐, 눈이 없냐.",
    "이 플랫폼은 결정장애 치료소지 네 일기장이 아니다. 그만 묻고 움직여라.",
    "질문 횟수 다 썼다. 인생도 쿨타임 있다는 거 알아? 좀 쉬고 와라.",
    "같은 고민을 이렇게 많이 하는 걸 보니 진짜 문제는 질문이 아닌 것 같다.",
    "이 정도면 결정장애가 아니라 결정 거부다. 세션 리셋하고 새 마음으로 와라.",
    "더 물어봐도 대답은 달라지지 않는다. 우주의 진리처럼.",
    "야, 진짜로. 그냥 해. 뭐든 해. 아무것도 안 하는 게 제일 나쁜 선택이야.",
    "이 질문을 몇 번째 하는 건지 알아? 그 에너지로 그냥 하면 됐잖아.",
    "결정을 대신 내려줬는데 또 물어보면 뭐가 달라지냐. 나도 모르겠다, 이제.",
]


def pick_termination_message() -> str:
    return random.choice(_MESSAGES)


# ── 쿨다운 자동 해제 ─────────────────────────────────────────

def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


async def lock_with_cooldown(redis: aioredis.Redis, session_id: str) -> None:
    """세션을 잠그고 locked_at 타임스탬프를 기록한다."""
    from app.session_store import get_session
    data = await get_session(redis, session_id)
    if data is None:
        raise KeyError(session_id)
    data["locked"] = True
    data["locked_at"] = _now_ts()
    await _save(redis, session_id, data)


async def check_and_auto_unlock(redis: aioredis.Redis, session_id: str) -> bool:
    """쿨다운이 지났으면 자동 해제하고 True 반환. 설정값이 0이면 항상 False."""
    if settings.COOLDOWN_SEC <= 0:
        return False

    data = await get_session(redis, session_id)
    if data is None or not data.get("locked"):
        return False

    locked_at = data.get("locked_at")
    if locked_at is None:
        return False

    elapsed = _now_ts() - locked_at
    if elapsed >= settings.COOLDOWN_SEC:
        data["locked"] = False
        data["requestion_count"] = 0
        data["locked_at"] = None
        await _save(redis, session_id, data)
        return True

    return False


def cooldown_remaining(locked_at: float | None) -> int:
    """잠금 해제까지 남은 초 (COOLDOWN_SEC=0 이면 -1)."""
    if settings.COOLDOWN_SEC <= 0 or locked_at is None:
        return -1
    remaining = settings.COOLDOWN_SEC - (_now_ts() - locked_at)
    return max(0, int(remaining))
