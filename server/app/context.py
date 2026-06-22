"""컨텍스트 윈도우 — §9.1

재질문 시 이전 대화를 포함하되 토큰이 선형 증가하지 않도록 관리한다.

전략:
  - 최근 CONTEXT_WINDOW_TURNS 턴: 원문 그대로 포함
  - 초과분(오래된 턴): LLM(judge급 저렴 모델)으로 요약 압축 후 1개 블록으로 삽입
  - 직전 grounded_context: 재질문 시 별도 블록으로 주입 (중복 검색 방지)

"턴(turn)" = 사용자 메시지 1개 + 어시스턴트 응답 1개 쌍
"""
import logging

from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

# ── 내부 타입 ─────────────────────────────────────────────────

type _Turn = tuple[dict, dict]   # (user_entry, assistant_entry)


# ── 턴 파싱 ──────────────────────────────────────────────────

def _parse_turns(history: list[dict]) -> list[_Turn]:
    """flat history → (user, assistant) 쌍 리스트. 불완전한 항목은 스킵."""
    turns: list[_Turn] = []
    i = 0
    while i < len(history) - 1:
        u, a = history[i], history[i + 1]
        if u.get("role") == "user" and a.get("role") == "assistant":
            turns.append((u, a))
            i += 2
        else:
            i += 1
    return turns


def _turns_to_messages(turns: list[_Turn]) -> list[dict]:
    msgs: list[dict] = []
    for u, a in turns:
        msgs.append({"role": "user", "content": u["content"]})
        msgs.append({"role": "assistant", "content": a["content"]})
    return msgs


# ── 요약 압축 ─────────────────────────────────────────────────

async def _summarize_turns(turns: list[_Turn]) -> str:
    """오래된 턴들을 3~5문장으로 압축한다."""
    text = "\n\n".join(
        f"사용자: {u['content']}\n어시스턴트: {a['content']}"
        for u, a in turns
    )
    try:
        response = await _client.chat.completions.create(
            model=settings.JUDGE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "아래 대화를 3~5문장으로 요약해라. "
                        "결정된 내용, 핵심 맥락, 주요 논거만 남긴다. "
                        "불필요한 서론 없이 바로 요약문만 출력한다."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=300,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Context summarization failed: %s", exc)
        # 실패 시 최신 1턴만 원문으로 돌려줌
        u, a = turns[-1]
        return f"(요약 실패 — 마지막 대화만 포함)\n사용자: {u['content']}\n어시스턴트: {a['content']}"


# ── 메인 진입점 ───────────────────────────────────────────────

async def build_history_messages(
    history: list[dict],
    last_grounded_summary: str | None = None,
) -> list[dict]:
    """session history → OpenAI messages 형식.

    최근 CONTEXT_WINDOW_TURNS 턴은 원문 포함,
    초과분은 LLM 요약으로 압축해 첫 블록에 삽입.
    last_grounded_summary가 있으면 재질문 시 맥락으로 주입한다.
    """
    turns = _parse_turns(history)
    if not turns:
        return []

    window = settings.CONTEXT_WINDOW_TURNS
    messages: list[dict] = []

    if len(turns) > window:
        old_turns = turns[:-window]
        recent_turns = turns[-window:]
        summary = await _summarize_turns(old_turns)
        # 요약을 pseudo-turn으로 삽입
        messages.append({"role": "user", "content": f"[이전 대화 요약]\n{summary}"})
        messages.append({"role": "assistant", "content": "이전 맥락을 이해했다. 계속 진행한다."})
        messages.extend(_turns_to_messages(recent_turns))
    else:
        messages.extend(_turns_to_messages(turns))

    # 직전 그라운딩 결과 주입 (중복 검색 방지용 참고 맥락)
    if last_grounded_summary:
        messages.append({
            "role": "user",
            "content": (
                "[직전 질문의 검색 근거 — 같은 주제라면 이 맥락을 참고해라]\n"
                + last_grounded_summary
            ),
        })
        messages.append({
            "role": "assistant",
            "content": "직전 검색 근거를 확인했다.",
        })

    return messages
