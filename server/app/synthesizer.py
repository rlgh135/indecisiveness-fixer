"""Synthesizer — §7.2  (Step 8에서 구현 예정)

이 파일은 Step 7 SSE 엔드포인트가 import할 수 있도록
타입과 스텁만 정의한다. Step 8에서 실제 LLM 호출로 교체된다.
"""
from dataclasses import dataclass, field

from app.grounding import GroundingResult
from app.persona_fanout import PersonaAnswer


@dataclass
class SynthesisOutput:
    conclusion: str
    forced_pick: str
    key_reasons: list[str] = field(default_factory=list)


async def synthesize(
    question: str,
    answers: list[PersonaAnswer],
    grounding: GroundingResult | None,
    history: list[dict],
) -> SynthesisOutput:
    """TODO: Step 8 — 현재는 스텁."""
    names = ", ".join(a.persona_name for a in answers)
    return SynthesisOutput(
        conclusion=f"[Step 8 미구현] {len(answers)}명({names})의 답변을 받았다.",
        forced_pick="[Step 8 미구현]",
        key_reasons=[],
    )
