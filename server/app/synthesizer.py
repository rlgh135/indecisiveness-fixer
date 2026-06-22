"""Synthesizer — §7.2

N개 페르소나 답변 + grounded_context → 단일 결론 + 강제 추천.

규칙:
- 반드시 하나를 고른다. "사람마다 다르다"로 끝내면 실패.
- 모델: settings.SYNTHESIZER_MODEL (gpt-4o급)
- JSON 파싱 실패 시 1회 재시도 (Judge와 동일 패턴)
"""
import json
import logging
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.grounding import GroundingResult
from app.persona_fanout import PersonaAnswer

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

_SYSTEM_PROMPT = """너는 결정장애 치료 플랫폼의 Synthesizer다.
여러 페르소나의 충돌하는 답변을 종합해 사용자의 결정을 끝내주는 단 하나의 결론을 내린다.
반드시 JSON만 출력한다. 프리앰블·백틱·부연 설명 금지.

[출력 스키마]
{
  "conclusion": "결국 핵심은 이거다 (2~3문장, 핵심만 압축)",
  "forced_pick": "그래도 굳이 하나만 고르면: [선택지]. 이유: [한 줄]",
  "key_reasons": ["결정을 가른 핵심 근거 1", "핵심 근거 2", "핵심 근거 3"]
}

[규칙]
- 반드시 하나의 선택지를 고른다. "사람마다 다르다", "상황에 따라 다르다"로 끝내면 실패다.
- 페르소나들의 충돌 중 이 질문에 가장 설득력 있는 논거를 채택해 판단한다.
- conclusion은 2~3문장으로 핵심을 압축한다. 장황하게 늘어놓지 않는다.
- forced_pick은 반드시 "그래도 굳이 하나만 고르면: ___. 이유: ___" 형식을 지킨다.
- key_reasons는 2~3개, 각 항목은 한 줄 이내."""


# ── 출력 타입 ─────────────────────────────────────────────────

@dataclass
class SynthesisOutput:
    conclusion: str
    forced_pick: str
    key_reasons: list[str] = field(default_factory=list)


class _SynthesisSchema(BaseModel):
    conclusion: str
    forced_pick: str
    key_reasons: list[str] = []


# ── 프롬프트 빌더 ─────────────────────────────────────────────

def _build_user_message(
    question: str,
    answers: list[PersonaAnswer],
    grounding: GroundingResult | None,
) -> str:
    parts: list[str] = [f"[원본 질문]\n{question}"]

    answers_block = "\n\n".join(
        f"### {a.persona_name}\n{a.answer}" for a in answers
    )
    parts.append(f"[페르소나 답변]\n{answers_block}")

    if grounding:
        parts.append(f"[grounded_context — 사실 기반 참고]\n{grounding.summary}")

    return "\n\n".join(parts)


# ── OpenAI 호출 ───────────────────────────────────────────────

async def _call(messages: list[dict]) -> str:
    response = await _client.chat.completions.create(
        model=settings.SYNTHESIZER_MODEL,
        messages=messages,
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    return response.choices[0].message.content or ""


# ── 메인 진입점 ───────────────────────────────────────────────

async def synthesize(
    question: str,
    answers: list[PersonaAnswer],
    grounding: GroundingResult | None,
    history: list[dict],
) -> SynthesisOutput:
    """N개 페르소나 답변을 종합해 SynthesisOutput을 반환한다.

    answers가 비어 있으면 (전원 실패) fallback 메시지를 반환한다.
    """
    if not answers:
        logger.warning("Synthesizer received no answers — returning fallback")
        return SynthesisOutput(
            conclusion="페르소나 답변을 받지 못했다. 다시 시도해라.",
            forced_pick="그래도 굳이 하나만 고르면: 재시도. 이유: 데이터 없음.",
            key_reasons=[],
        )

    user_msg = _build_user_message(question, answers, grounding)
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        *history,
        {"role": "user", "content": user_msg},
    ]

    for attempt in range(2):
        raw = await _call(messages)
        try:
            parsed = _SynthesisSchema(**json.loads(raw))
            return SynthesisOutput(
                conclusion=parsed.conclusion,
                forced_pick=parsed.forced_pick,
                key_reasons=parsed.key_reasons,
            )
        except (json.JSONDecodeError, ValidationError, TypeError) as exc:
            if attempt == 0:
                logger.warning("Synthesizer parse failed (attempt 1): %s — retrying", exc)
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "JSON 파싱에 실패했다. 스키마에 맞는 JSON만 다시 출력해라.",
                })
            else:
                logger.error("Synthesizer parse failed (attempt 2): %s", exc)
                raise ValueError("Synthesizer did not return valid JSON after 2 attempts") from exc
