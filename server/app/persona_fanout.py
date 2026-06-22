"""Persona fan-out — §13

선택된 페르소나들을 asyncio.create_task로 병렬 실행하고,
as_completed 순서대로 PersonaAnswer를 yield한다.

규칙:
- grounded_context는 fan-out 전 1회 확보한 것을 전 페르소나에 공유 주입 (개별 검색 금지)
- 한 페르소나 실패 → 로그 후 스킵, 나머지 계속 진행 (부분 성공)
- history는 Step 9(컨텍스트 윈도우)에서 포맷된 OpenAI messages 형식으로 전달받는다
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncGenerator

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.grounding import GroundingResult, format_for_persona
from app.models import Persona

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# ── 결과 타입 ─────────────────────────────────────────────────

@dataclass
class PersonaAnswer:
    persona_name: str
    answer: str


# ── DB 조회 ───────────────────────────────────────────────────

async def load_personas(names: list[str], db: AsyncSession) -> list[Persona]:
    """Judge가 선택한 이름 목록으로 활성 페르소나를 조회한다."""
    result = await db.execute(
        select(Persona).where(
            Persona.name.in_(names),
            Persona.is_active.is_(True),
        )
    )
    personas = list(result.scalars())

    # Judge가 선택한 순서 유지
    order_map = {name: i for i, name in enumerate(names)}
    return sorted(personas, key=lambda p: order_map.get(p.name, 999))


# ── 단일 페르소나 호출 ────────────────────────────────────────

async def _call_persona(
    persona: Persona,
    question: str,
    grounding: GroundingResult | None,
    history: list[dict],
) -> PersonaAnswer | None:
    """실패 시 None 반환 — 부분 성공 허용."""
    system = persona.system_prompt + "\n\n" + format_for_persona(grounding)
    messages: list[dict] = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": question})

    try:
        response = await _client.chat.completions.create(
            model=persona.model,
            messages=messages,
            temperature=0.8,
        )
        answer = response.choices[0].message.content or ""
        return PersonaAnswer(persona_name=persona.name, answer=answer)
    except Exception as exc:
        logger.warning("Persona %r failed: %s", persona.name, exc)
        return None


# ── 병렬 fan-out ──────────────────────────────────────────────

async def run_fanout(
    personas: list[Persona],
    question: str,
    grounding: GroundingResult | None,
    history: list[dict],
) -> AsyncGenerator[PersonaAnswer, None]:
    """페르소나를 병렬 실행하고 완료되는 순서대로 PersonaAnswer를 yield한다."""
    tasks = [
        asyncio.create_task(_call_persona(p, question, grounding, history))
        for p in personas
    ]

    for fut in asyncio.as_completed(tasks):
        result = await fut
        if result is not None:
            yield result
