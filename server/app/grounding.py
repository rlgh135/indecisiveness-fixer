"""Grounding — §8

Perplexity Sonar를 fan-out 전 정확히 1회 호출해 근거를 확보한다.
타임아웃·실패 시 None을 반환하고, 호출자가 grounded=false 폴백을 처리한다.

설정값(모두 .env에서 주입):
  PERPLEXITY_MODEL          기본 "sonar"
  PERPLEXITY_SEARCH_CONTEXT 기본 "low"
  GROUNDING_TIMEOUT_SEC     기본 6
  GROUNDING_MAX_TOKENS      트리밍 기준 (문자 수 근사값 — 토크나이저 미사용)
"""
import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"


# ── 결과 타입 ─────────────────────────────────────────────────

@dataclass
class Source:
    title: str
    url: str


@dataclass
class GroundingResult:
    summary: str              # 트리밍된 합성 답변 — 페르소나 프롬프트에 주입
    sources: list[Source] = field(default_factory=list)


# ── 내부 헬퍼 ─────────────────────────────────────────────────

def _extract_domain(url: str) -> str:
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _trim(text: str) -> str:
    """GROUNDING_MAX_TOKENS 문자 수 기준으로 트리밍."""
    limit = settings.GROUNDING_MAX_TOKENS
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + " …"


# ── 메인 진입점 ───────────────────────────────────────────────

async def ground(search_query: str) -> GroundingResult | None:
    """Perplexity Sonar 1회 호출.

    성공 → GroundingResult
    타임아웃·HTTP 오류·파싱 실패 → None (호출자가 폴백 처리)
    """
    try:
        async with httpx.AsyncClient(timeout=settings.GROUNDING_TIMEOUT_SEC) as client:
            resp = await client.post(
                _PERPLEXITY_URL,
                headers={
                    "Authorization": f"Bearer {settings.PERPLEXITY_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.PERPLEXITY_MODEL,
                    "messages": [{"role": "user", "content": search_query}],
                    "search_context_size": settings.PERPLEXITY_SEARCH_CONTEXT,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException:
        logger.warning("Grounding timed out (query=%r)", search_query)
        return None
    except Exception as exc:
        logger.warning("Grounding failed: %s", exc)
        return None

    content: str = (
        data.get("choices", [{}])[0].get("message", {}).get("content", "")
    )
    citation_urls: list[str] = data.get("citations", [])

    return GroundingResult(
        summary=_trim(content),
        sources=[Source(title=_extract_domain(url), url=url) for url in citation_urls],
    )


# ── 페르소나 프롬프트 주입용 포맷터 ──────────────────────────

def format_for_persona(result: GroundingResult | None) -> str:
    """grounded_context 블록을 반환한다. None이면 미확보 안내 문자열."""
    if result is None:
        return "[최신 정보 미확보: 검색에 실패했거나 타임아웃이 발생했다. 학습 데이터 기반으로만 판단하라.]"
    return f"[grounded_context — 아래 내용을 사실 기반으로만 사용하고, 그 위에 네 입장을 세워라]\n{result.summary}"
