"""Judge/Router — §7.1

질문을 분류(subjective / out_of_scope)하고,
충돌하는 페르소나 N명을 선택하며,
현재 정보 필요 여부(needs_fresh_context)와 검색 쿼리를 판단한다.

- 모델: settings.JUDGE_MODEL (gpt-4o-mini급 저렴 모델)
- DB의 타입/페르소나 목록을 프롬프트에 인라인 주입 (MVP 인라인 매칭)
- JSON 파싱 실패 시 1회 재시도
"""
import json
import logging

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Persona, QuestionType

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


# ── 출력 스키마 ───────────────────────────────────────────────

class JudgeOutput(BaseModel):
    verdict: str                      # "subjective" | "out_of_scope"
    reason: str
    type_hints: list[str] = []
    selected_personas: list[str] = []
    needs_fresh_context: bool = False
    search_query: str | None = None


# ── 프롬프트 빌더 ─────────────────────────────────────────────

def _build_system_prompt(
    types: list[QuestionType],
    personas: list[Persona],
    persona_count: int,
) -> str:
    types_block = "\n".join(
        f"- {t.name}: {t.description} (키워드: {', '.join(t.keywords)})"
        for t in types
    )
    personas_block = "\n".join(
        f"- {p.name}: {p.stance_directive}" for p in personas
    )
    return f"""너는 결정장애 치료 플랫폼의 Judge/Router다.
사용자 질문을 분류하고, 적절한 페르소나를 선택하고, 현재 정보 필요 여부를 판단한다.
반드시 JSON만 출력한다. 프리앰블·백틱·부연 설명 금지.

[질문 타입 목록]
{types_block}

[페르소나 풀]
{personas_block}

[출력 스키마]
{{
  "verdict": "subjective 또는 out_of_scope",
  "reason": "분류 이유 한 줄",
  "type_hints": ["해당 타입명"],
  "selected_personas": ["페르소나명"],
  "needs_fresh_context": true 또는 false,
  "search_query": "검색 쿼리 (needs_fresh_context=true일 때만, 아니면 null)"
}}

[분류 규칙]
- 날씨·환율·사실 조회·잡담 → verdict: "out_of_scope", selected_personas: []
- 주관적 결정·선택 → verdict: "subjective"
  - 질문에 가장 잘 충돌하는 페르소나 정확히 {persona_count}명을 selected_personas에 포함
  - type_hints는 페르소나 풀을 좁히는 보조 신호일 뿐, 단일 타입으로 단정하지 않는다
- needs_fresh_context: 학습 데이터만으로 답하면 위험한 시점 의존 질문이면 true
  - 예) 현재 게임 메타/패치, 최신 제품 가격, 현재 금리·시장 상황
  - 순수 가치판단("헤어질까?", "이직해야 할까?")은 false
- search_query는 needs_fresh_context=true일 때만 채운다"""


# ── OpenAI 호출 ───────────────────────────────────────────────

async def _call(messages: list[dict]) -> str:
    response = await _client.chat.completions.create(
        model=settings.JUDGE_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0,
    )
    return response.choices[0].message.content or ""


# ── 메인 진입점 ───────────────────────────────────────────────

async def run_judge(question: str, db: AsyncSession) -> JudgeOutput:
    """질문을 분류하고 JudgeOutput을 반환한다."""
    types = list(
        (await db.execute(select(QuestionType).where(QuestionType.is_active.is_(True)))).scalars()
    )
    personas = list(
        (await db.execute(select(Persona).where(Persona.is_active.is_(True)))).scalars()
    )
    valid_names = {p.name for p in personas}

    system_prompt = _build_system_prompt(types, personas, settings.JUDGE_PERSONA_COUNT)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    for attempt in range(2):
        raw = await _call(messages)
        try:
            output = JudgeOutput(**json.loads(raw))
            # 풀에 없는 페르소나 이름 제거 (환각 방어)
            output.selected_personas = [n for n in output.selected_personas if n in valid_names]
            if output.verdict == "out_of_scope":
                output.selected_personas = []
                output.needs_fresh_context = False
                output.search_query = None
            return output
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            if attempt == 0:
                logger.warning("Judge parse failed (attempt 1): %s — retrying", exc)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "JSON 파싱에 실패했다. 스키마에 맞는 JSON만 다시 출력해라.",
                })
            else:
                logger.error("Judge parse failed (attempt 2): %s", exc)
                raise ValueError(f"Judge did not return valid JSON after 2 attempts") from exc
