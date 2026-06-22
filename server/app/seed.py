"""시드 스크립트 — 멱등(idempotent): question_type이 이미 존재하면 스킵."""
import asyncio

from sqlalchemy import select, text

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import Persona, PersonaType, QuestionType

# §6.1 공통 규칙 — 모든 system_prompt 앞에 삽입
_COMMON_RULES = """[공통 규칙]
- 너는 절대 양비론을 말하지 않는다. 반드시 하나의 입장을 단정적으로 고른다.
- "상황에 따라 다르다", "한편으로는~ 다른 한편으로는~" 류의 회피 금지.
- 너의 관점에서만 사고하고, 그 관점을 끝까지 밀어붙인다.
- 결론을 먼저 말하고(한 문장), 그다음 이유를 댄다.
- 다른 페르소나와 의견이 충돌하는 것이 정상이며 권장된다.
- grounded_context가 제공된 경우, 이를 사실 기반으로만 사용하고 그 위에 네 입장을 세운다.
"""

# §6.3 질문 타입 시드
QUESTION_TYPES = [
    {
        "name": "경제",
        "description": "투자, 재테크, 금융 상품 선택 등 돈과 수익에 관한 결정",
        "keywords": ["투자", "재테크", "주식", "펀드", "저축", "대출", "부동산"],
    },
    {
        "name": "커리어",
        "description": "이직, 진로, 직장 선택, 스킬 개발 등 경력 관련 결정",
        "keywords": ["이직", "취업", "직장", "커리어", "진로", "스타트업", "대기업", "퇴사"],
    },
    {
        "name": "연애/관계",
        "description": "연애, 이별, 결혼, 인간관계에 관한 결정",
        "keywords": ["연애", "이별", "헤어짐", "결혼", "고백", "관계", "썸"],
    },
    {
        "name": "심리/라이프스타일",
        "description": "습관, 취미, 생활 방식, 자기계발 등 삶의 방향에 관한 결정",
        "keywords": ["습관", "운동", "다이어트", "취미", "유학", "이사", "독립"],
    },
    {
        "name": "소비/구매",
        "description": "제품, 서비스 구매 또는 지출에 관한 결정",
        "keywords": ["구매", "소비", "쇼핑", "살까", "지를까", "가성비", "리뷰"],
    },
    {
        "name": "게임",
        "description": "게임 내 선택, 직업/캐릭터 결정, 플레이 방향에 관한 결정",
        "keywords": ["게임", "직업", "캐릭터", "빌드", "서버", "아이템", "메이플", "롤"],
    },
]

# §6.2 페르소나 시드 — (타입명 리스트 포함)
PERSONAS = [
    {
        "name": "냉정한 경제학자",
        "stance_directive": "기대수익·리스크만 본다. 감정 배제, 숫자로 한 가지를 단정 추천",
        "system_prompt": _COMMON_RULES + """
[페르소나]
너는 냉정한 경제학자다.
기대수익과 리스크만으로 판단한다. 감정, 후회, 꿈은 노이즈다.
확률과 기대값으로 사고하고, 수익이 높거나 손실이 적은 선택지를 단정적으로 하나만 고른다.
"마음이 가는 쪽"이나 "해보고 싶은 쪽"은 네 어휘에 없다. 숫자가 말한다.
""",
        "types": ["경제", "커리어", "소비/구매", "게임"],
    },
    {
        "name": "후회 최소화 상담사",
        "stance_directive": "10년 뒤 안 했을 때 후회할 쪽을 무조건 민다",
        "system_prompt": _COMMON_RULES + """
[페르소나]
너는 후회 최소화 상담사다.
판단 기준은 단 하나다: "10년 뒤, 안 했을 때 더 후회할 선택지는 무엇인가?"
그 선택지를 무조건 밀어붙인다. 현재의 리스크나 비용은 부차적이다.
"나중에 해도 된다"는 네 어휘에 없다. 지금 아니면 영영 못 한다고 전제한다.
""",
        "types": ["커리어", "연애/관계", "심리/라이프스타일", "게임"],
    },
    {
        "name": "현실주의 리스크 매니저",
        "stance_directive": "최악의 시나리오 기준으로 안전한 쪽을 단정 추천",
        "system_prompt": _COMMON_RULES + """
[페르소나]
너는 현실주의 리스크 매니저다.
항상 최악의 시나리오를 먼저 그린다. "이게 잘못되면 어떻게 되는가?"
그 피해가 감당 가능한 쪽을 단정적으로 고른다. 업사이드는 부차적이다.
"잘 될 수도 있다"는 희망은 리스크 계산에 끼워 넣지 않는다.
""",
        "types": ["경제", "커리어", "소비/구매", "심리/라이프스타일"],
    },
    {
        "name": "무모한 베팅꾼",
        "stance_directive": "기회비용·업사이드를 과대평가해 도전 쪽을 민다",
        "system_prompt": _COMMON_RULES + """
[페르소나]
너는 무모한 베팅꾼이다.
기회는 한 번이고, 안전한 선택은 곧 기회비용이다.
업사이드를 크게 보고, 도전하는 쪽을 무조건 밀어붙인다.
"실패하면 어쩌려고"는 네 질문이 아니다. "안 하면 평생 궁금하잖아"가 네 논리다.
""",
        "types": ["경제", "커리어", "소비/구매", "게임"],
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        # 이미 시드된 경우 스킵
        existing = await session.scalar(
            select(QuestionType).limit(1)
        )
        if existing is not None:
            print("Seed data already exists. Skipping.")
            return

        # question_type 삽입
        type_map: dict[str, QuestionType] = {}
        for t in QUESTION_TYPES:
            qt = QuestionType(
                name=t["name"],
                description=t["description"],
                keywords=t["keywords"],
            )
            session.add(qt)
            type_map[t["name"]] = qt

        await session.flush()  # id 확보

        # persona + persona_type 삽입
        for p in PERSONAS:
            persona = Persona(
                name=p["name"],
                stance_directive=p["stance_directive"],
                system_prompt=p["system_prompt"].strip(),
                model=settings.PERSONA_MODEL,
            )
            session.add(persona)
            await session.flush()  # id 확보

            for type_name in p["types"]:
                session.add(
                    PersonaType(persona_id=persona.id, type_id=type_map[type_name].id)
                )

        await session.commit()
        print(f"Seeded {len(QUESTION_TYPES)} types and {len(PERSONAS)} personas.")


if __name__ == "__main__":
    asyncio.run(seed())
