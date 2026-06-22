# 결정장애 치료 플랫폼 — 설계서 (DESIGN.md)

> 이 문서는 구현 에이전트(Claude Code)가 직접 읽고 작업하기 위한 스펙이다.
> 코드는 이 문서의 계약(스키마 / API / 플로우)을 단일 소스로 삼는다.
> 추정으로 채우지 말고, 모호한 지점은 `TODO(decision)` 주석으로 남긴다.

---

## 0. 한 줄 요약

질문을 받아 **서로 충돌하는 페르소나 N명**에게 병렬로 던지고, 도착하는 대로 스트리밍한 뒤,
판단 에이전트가 이를 **하나의 결론 + 강제 추천**으로 종합해 사용자의 결정을 끝내주는 플랫폼.
현재 정보가 필요한 질문은 **Perplexity로 1회 검색해 근거를 공유 주입**한 뒤 추론한다.

핵심은 "선택지를 늘리는 것"이 아니라 "선택지를 좁혀 커밋시키는 것"이다.

---

## 1. 제품 원칙 (구현 시 항상 우선)

1. **결정장애의 해법은 선택지 확장이 아니라 제약과 커밋이다.**
   - 답변 N개를 뿌리고 끝내지 않는다. 반드시 종합(synthesis) 단계로 하나의 결론을 강제한다.
2. **제품의 가치는 아키텍처가 아니라 페르소나 품질에서 나온다.**
   - 병렬 호출 구조는 표준 기술. 차별화는 §6 페르소나 설계에 100% 달려 있다.
3. **양비론 금지.** 모든 페르소나는 한 가지 입장을 단정적으로 민다. "한편으로는~ 다른 한편으로는~"는 실패다.
4. **이 제품은 만능 Q&A가 아니다.**
   - 사실 자체(날씨·환율 등)를 답하는 게 목적이 아니다. 그런 질문은 §7.1에서 `out_of_scope`로 거른다.
   - 단, "메이플 직업 추천"처럼 **주관적 결정이지만 현재 정보가 필요한** 질문은 검색으로 근거를 깔아준다(§8). 사실 조회와 그라운딩은 다르다.
5. **복잡도는 규모가 정당화할 때만 도입한다.** 벡터 검색은 처음부터 깔지 않는다(타입 매칭은 인라인부터).

---

## 2. 전체 플로우

```
[사용자 질문]
     │
     ▼
[Judge / Router]  ← 싼 모델(haiku급)
     │   분류 + 페르소나 N명 선택 + needs_fresh_context 판단 + search_query 생성
     │
     ├─ (A) 주관적 결정 질문이 아님(사실조회·잡담)
     │        → "이건 제가 답할 질문이 아니에요" 필터 응답 후 종료
     │
     └─ (B) 주관적 결정 질문
              │
              ├─ needs_fresh_context == true?
              │     ├─ YES → [Perplexity Sonar 1회 호출]  ← 백엔드 오케스트레이션
              │     │            → grounded_context(합성 요약) + sources(인용 URL)
              │     └─ NO  → grounded_context = null
              │
              ▼
        [DB: persona 조회]  ← 선택된 페르소나의 system_prompt / stance_directive
              │
              ▼
        [병렬 fan-out → LLM]  ← 각 페르소나 = system_prompt + 질문 + grounded_context(공유)
              │   (페르소나는 직접 검색하지 않는다. 근거는 위에서 1회 받은 것을 공유)
              ▼
        [SSE 스트리밍]  ← sources → 도착 순서대로 persona_answer 실시간 전송
              │
              ▼
        [Synthesis / Judge 재종합]  ← N개 답변(+grounded_context) → 단일 결론 + 강제 추천
              │
              ▼
        [사용자: 선택 / 재질문]
              │
              ▼
        [재질문 시 반복, 단 이전 컨텍스트 포함(윈도우/요약)]
              │
              ▼
        [재질문 N회 초과 → 재수없는 말투로 종료 + 리셋 경로 제공]
```

원본 구상 대비 바뀐 점:
- **종합(synthesis) 단계 추가**: 답변을 뿌리고 끝내지 않는다.
- **타입 단일 선택 → 다중 페르소나 선택**: 타입은 풀을 좁히는 약한 필터로 강등(§7.1).
- **"답 정해진 질문 직접 답변" → 필터링**: 직접 답하지 않는다.
- **그라운딩 단계 추가**: 현재 정보가 필요한 질문은 Perplexity로 1회 검색해 전 페르소나에 공유(§8).

---

## 3. 컴포넌트 정의

| 컴포넌트 | 역할 | 모델 / 서비스 | 비고 |
|---|---|---|---|
| **Judge/Router** | 분류(A/B), 페르소나 선택, 그라운딩 필요 판단 | 싼 모델(haiku급) | 타입 풀이 작으면 1회 호출로 |
| **Grounding** | 현재 정보 1회 검색 → 근거 합성 | Perplexity Sonar(`sonar`) | 백엔드에서 호출, 결과를 전 페르소나에 공유 |
| **Persona Agents** | 충돌하는 입장으로 답변 생성 | 좋은 모델 | DB의 system_prompt로 동작, 직접 검색 X |
| **Synthesizer** | N개 답변 → 단일 결론 + 강제 추천 | 좋은 모델 | Judge와 모델 공유 가능, 프롬프트 분리 |
| **Session Store** | 재질문 카운터 + 대화 히스토리 | Redis | TTL 기반 만료 |

> Judge / Synthesizer는 역할이 다르므로 **프롬프트를 분리**한다(모델은 공유 가능).
> 그라운딩은 페르소나마다 하지 않는다. **반드시 fan-out 전 1회**만 수행해 공유한다.

---

## 4. 데이터 모델

PostgreSQL. 스키마명: `decidoctor` (TODO(decision): 최종 스키마명 확정).
페르소나 프롬프트가 곧 제품이므로 **버저닝**을 1급으로 둔다.

### 4.1 `question_type` — 타입(약한 필터)

```sql
CREATE TABLE decidoctor.question_type (
    id          BIGSERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,        -- 예: '경제', '커리어', '게임', '심리'
    description TEXT NOT NULL,               -- Judge가 매칭에 쓰는 설명
    keywords    TEXT[] NOT NULL DEFAULT '{}',-- 인라인 매칭 보조용
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 4.2 `persona` — 페르소나(에이전트)

```sql
CREATE TABLE decidoctor.persona (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT NOT NULL,          -- 사용자에게 노출될 이름, 예: '냉정한 경제학자'
    stance_directive TEXT NOT NULL,          -- 이 페르소나가 무조건 미는 한 줄 입장(핵심)
    system_prompt    TEXT NOT NULL,          -- 전체 페르소나 프롬프트
    model            TEXT NOT NULL,          -- 호출 모델명
    version          INT  NOT NULL DEFAULT 1,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- (name, version) 유니크. 활성 버전은 is_active로 1개만 유지.
CREATE UNIQUE INDEX uq_persona_name_version
    ON decidoctor.persona (name, version);
```

### 4.3 `persona_type` — 페르소나 ↔ 타입 다대다

타입은 단일 매핑이 아니라 **풀을 좁히는 필터**이므로 N:M.

```sql
CREATE TABLE decidoctor.persona_type (
    persona_id BIGINT NOT NULL REFERENCES decidoctor.persona(id),
    type_id    BIGINT NOT NULL REFERENCES decidoctor.question_type(id),
    weight     REAL   NOT NULL DEFAULT 1.0,  -- 타입 적합도(선택적)
    PRIMARY KEY (persona_id, type_id)
);
```

### 4.4 세션 상태 (Redis)

DB 테이블 아님. 키 설계:

```
session:{session_id} = {
  "history": [ {role, content, persona_name?, ts}, ... ],
  "requestion_count": int,
  "locked": bool,            // 한도 초과로 잠겼는지
  "created_at": iso8601
}
TTL: 기본 1시간 (설정값)
```

---

## 5. API 설계 (FastAPI)

### 5.1 `POST /sessions`
새 세션 생성. **응답**: `{ "session_id": "uuid" }`

### 5.2 `POST /sessions/{session_id}/ask` (SSE)
질문 제출 → 전체 파이프라인 실행 → 이벤트 스트림 반환.

- **요청 바디**: `{ "question": "string" }`
- **응답**: `text/event-stream` (SSE)
- **사전 검사**: `locked == true`면 `423 Locked` + 리셋 안내.

> 주의: 브라우저 기본 `EventSource`는 GET만 지원한다. 이 엔드포인트는 POST + SSE이므로
> **클라이언트는 `fetch` + `ReadableStream`으로 직접 파싱**한다(§12 참고).

#### SSE 이벤트 계약

이벤트는 도착 순서대로 전송된다. `event:` 필드로 타입 구분.

```
event: judge
data: {"verdict": "subjective", "selected_personas": ["냉정한 경제학자","후회 최소화 상담사"], "grounded": true}

event: judge
data: {"verdict": "out_of_scope", "message": "이건 제가 답할 질문이 아니에요."}   # (A) 분기면 여기서 종료

event: sources                # 그라운딩 수행 시 1회 (needs_fresh_context == true)
data: {"sources": [{"title":"...", "url":"..."}], "summary": "검색으로 확보한 근거 요약(축약본)"}

event: persona_answer         # 페르소나 1명 완료 시마다 1개씩 (as_completed 순서)
data: {"persona_name": "냉정한 경제학자", "answer": "...", "order": 1}

event: synthesis              # 모든 페르소나 종료 후 1개
data: {"conclusion": "...", "forced_pick": "...", "key_reasons": ["...","..."]}

event: done
data: {"requestion_count": 1}

event: error
data: {"message": "..."}
```

> 토큰 단위 인터리빙(타자기 효과)까지 가려면 WebSocket으로 승격. **MVP는 SSE + 페르소나 단위 청크로 충분.**

### 5.3 `POST /sessions/{session_id}/reset`
잠긴 세션을 푸는 리셋 경로(§10). 카운터·lock 초기화.

---

## 6. 페르소나 설계 가이드 (제품의 핵심)

> 여기에 시간을 가장 많이 쏟는다. 아키텍처는 이미 표준이고, 차별화는 전부 여기서 나온다.

### 6.1 절대 규칙 (모든 `system_prompt`에 공통 삽입)

```
- 너는 절대 양비론을 말하지 않는다. 반드시 하나의 입장을 단정적으로 고른다.
- "상황에 따라 다르다", "한편으로는~ 다른 한편으로는~" 류의 회피 금지.
- 너의 관점(stance_directive)에서만 사고하고, 그 관점을 끝까지 밀어붙인다.
- 결론을 먼저 말하고(한 문장), 그다음 이유를 댄다.
- 다른 페르소나와 의견이 충돌하는 것이 정상이며 권장된다.
- (근거가 주어진 경우) 제공된 grounded_context를 사실 기반으로만 사용하고, 그 위에 네 입장을 세운다.
```

### 6.2 페르소나는 "충돌"하도록 설계한다

같은 질문에 정반대 압력을 주는 짝으로 구성. 예시 시드 데이터:

| name | stance_directive (무조건 미는 입장) |
|---|---|
| 냉정한 경제학자 | 기대수익·리스크만 본다. 감정 배제, 숫자로 한 가지를 단정 추천 |
| 후회 최소화 상담사 | "10년 뒤 안 했을 때 후회할 쪽"을 무조건 민다 |
| 현실주의 리스크 매니저 | 최악의 시나리오 기준으로 안전한 쪽을 단정 |
| 무모한 베팅꾼 | 기회비용·업사이드를 과대평가해 도전 쪽을 민다 |

> 4명이 모두 "잘 모르겠지만 신중하게…"라고 hedge하면 제품은 죽는다. **서로 싸우게 만들어라.**

### 6.3 시드 타입 (초기)

`경제`, `커리어`, `연애/관계`, `심리/라이프스타일`, `소비/구매`, `게임` 정도로 시작.
페르소나는 여러 타입에 걸쳐 매핑(N:M)한다.

---

## 7. Judge & Synthesis 프롬프트 설계

### 7.1 Judge (분류 + 페르소나 선택 + 그라운딩 판단)

타입 리스트가 작으면 **DB 타입 목록을 프롬프트에 인라인**해 1회 호출로 끝낸다.

출력은 JSON 강제(프리앰블·백틱 금지):

```json
{
  "verdict": "subjective | out_of_scope",
  "reason": "왜 이렇게 분류했는지 한 줄",
  "type_hints": ["게임"],
  "selected_personas": ["냉정한 경제학자", "후회 최소화 상담사"],
  "needs_fresh_context": true,
  "search_query": "메이플스토리 현재 패치 직업 티어 추천"
}
```

규칙:
- 날씨/환율/단순 사실/잡담 → `out_of_scope`.
- 주관적 결정 → 질문에 **가장 잘 충돌하는** 페르소나 N명 선택(기본 N=3~4, 설정값).
- 타입은 페르소나 풀을 좁히는 보조 신호일 뿐, 단일 타입으로 단정하지 않는다.
- **`needs_fresh_context`**: 학습 지식만으로 답하면 위험한, 시점 의존(현재 메타/가격/최신 상황) 질문이면 true. 이때 `search_query`를 함께 생성.
- 순수 가치판단(예: "이 사람과 헤어질까")은 보통 false — 검색해도 결정에 도움 안 됨.

> 타입이 수십 개로 커지면 그때 임베딩 검색으로 교체. **MVP는 인라인 매칭.**

### 7.2 Synthesizer (종합 — 결정장애를 끝내는 단계)

입력: 원본 질문 + N개 페르소나 답변 + grounded_context(있으면). 출력 JSON:

```json
{
  "conclusion": "결국 핵심은 이거다 (2~3문장)",
  "forced_pick": "그래도 굳이 하나만 고르면: ___ . 이유: ___",
  "key_reasons": ["결정을 가른 핵심 근거 2~3개"]
}
```

규칙:
- **반드시 하나를 고른다.** "사람마다 다르다"로 끝내면 실패.
- 페르소나 원본 답변은 UI에서 접어두고(펼쳐보기), 종합 결론을 위에 노출.

---

## 8. 검색 / 그라운딩 (Perplexity Sonar)

현재 정보가 필요한 주관적 질문에 **사실 근거를 1회 확보**해 전 페르소나에 공유 주입한다.

### 8.1 왜 Perplexity Sonar인가

- 한 번의 호출로 **검색 + 합성 + 인용(출처 URL)**을 돌려줘서, 그대로 grounded_context로 쓰기 좋다.
- 기본 `sonar` 모델은 입력/출력 100만 토큰당 각 $1 수준이고 검색·인용이 토큰가에 포함된다(별도 검색 인프라 불필요).
- 인용 출처를 사용자에게 노출하면 결정 신뢰도가 올라간다(제품 디테일).
- Anthropic 내장 web_search 대비: (a) 결과 텍스트를 백엔드가 직접 통제 → 트리밍·요약으로 토큰 누적 제어, (b) 검색 1회를 N명이 공유, (c) judge=haiku / persona=좋은 모델 분리 전략과 충돌 없음.

> 합성 없는 raw 결과만 원하면 Perplexity **Search API**($5/1k requests, 토큰 과금 없음)도 선택지지만,
> 이 앱은 "근거 요약을 페르소나에 주입"이 목적이라 합성+인용을 주는 **Sonar(`sonar`)를 기본**으로 한다.

### 8.2 호출 규칙

- **fan-out 전, 백엔드에서 정확히 1회** 호출(`needs_fresh_context == true`일 때만).
- 모델: 기본 `sonar` (그라운딩은 사실 확보용이므로 저렴 티어. `sonar-pro`는 품질이 크게 필요할 때만, 설정값).
- 입력: Judge가 만든 `search_query`. (`search_context_size`는 낮게 — 결정 근거용 요약이면 충분, 요청 수수료/토큰 절약)
- 출력 처리:
  - 합성 답변 → 길면 **요약/트리밍** 후 `grounded_context`로 전 페르소나 프롬프트에 동일 주입.
  - citations(source URL/title) → `sources` SSE 이벤트로 사용자에게 노출.
  - `grounded_context`는 §9.1 컨텍스트 윈도우에 태워 재질문 시 토큰 폭증을 막는다.
- 실패/타임아웃 시: 그라운딩 없이 진행(`grounded` = false)하되, 페르소나에게 "최신 정보 미확보" 사실을 알린다.

### 8.3 설정값

```
PERPLEXITY_MODEL          = "sonar"          # 그라운딩 기본
PERPLEXITY_SEARCH_CONTEXT = "low"            # low | medium | high
GROUNDING_TIMEOUT_SEC     = 6
GROUNDING_MAX_TOKENS      = <주입 상한>       # 트리밍 기준
```

API 키는 환경변수(`PERPLEXITY_API_KEY`), 코드 하드코딩 금지.

---

## 9. 세션 / 컨텍스트 / 비용

### 9.1 재질문 컨텍스트(원본 12번)
- 재질문 시 이전 대화를 포함하되 **전부 싣지 않는다**(토큰·비용 선형 증가).
- 전략: **최근 N턴 윈도우** + 그 이전은 **요약 압축**. 설정값으로 N 노출.
- `grounded_context`도 여기에 포함시켜 관리(중복 검색 방지: 같은 주제 재질문이면 직전 근거 재사용 고려).

### 9.2 모델 비용 분리
- Judge/Router: 싼 모델(haiku급).
- Grounding: Perplexity `sonar`(저렴 티어).
- Persona / Synthesizer: 좋은 모델.
- 모델명은 DB(`persona.model`) / 설정으로 주입, 하드코딩 금지.

### 9.3 프롬프트 버저닝
- `persona.version`으로 A/B·롤백 지원. 활성 버전은 `is_active`로 1개만.
- 프롬프트가 곧 제품이므로 변경 이력을 남긴다.

---

## 10. 재질문 한도 & 종료 (원본 13번 — 시그니처 기능)

- 재질문 카운트가 **임계값 초과**(기본 3, **설정값**)면:
  - Judge가 **재수없는 말투**로 "그만 좀 묻고 나가라"는 응답을 낸다.
  - 세션 `locked = true`, 질문 UI 비활성화.
- **영구 비활성화 금지.** 반드시 리셋 경로 제공:
  - `POST /sessions/{id}/reset` 또는 새 세션 생성으로 복구.
  - 쿨다운(예: N분 후 자동 해제)도 설정값으로 선택 가능.

> 데모에서 기억에 남는 인격 디테일이므로 살리되, 막다른 길은 만들지 않는다.

---

## 11. 기술 스택

| 영역 | 선택 | 이유 |
|---|---|---|
| 백엔드 | FastAPI | async 네이티브, SSE/WebSocket 용이 |
| 병렬 LLM | `asyncio` + `as_completed` | 도착 순서 스트리밍 |
| 실시간 | SSE (MVP) → WebSocket(토큰 인터리빙 시) | 단계적 |
| DB | PostgreSQL | 페르소나/타입 레지스트리 |
| 세션 | Redis | 카운터 + 히스토리 + TTL |
| LLM | Anthropic API | judge=싼 모델, persona=좋은 모델 |
| 검색 | Perplexity Sonar API | 검색+합성+인용 1회, 근거 공유 주입 |
| 프런트 | Vite + React (SPA) | §12 |
| 설정 | pydantic-settings (.env) | 임계값/모델/N/키 등 외부화 |

---

## 12. 프런트엔드

### 12.1 프레임워크: Vite + React (SPA). Next.js 미사용
- 백엔드가 FastAPI이므로 Next의 API Routes/SSR은 죽은 무게. SPA가 빌드 빠르고 구조 단순.
- Vercel AI SDK의 `useChat` 류도 자체 스트림 포맷을 강제해 커스텀 이벤트(judge/sources/persona_answer/synthesis)와 안 맞음 → 직접 파싱.

### 12.2 스트리밍: `fetch` + `ReadableStream` (EventSource 금지)
- `/ask`는 POST + SSE인데 브라우저 `EventSource`는 GET만 지원 → 사용 불가.
- `fetch` 응답 바디를 스트림으로 읽어 `event:` / `data:` 라인을 직접 파싱.
- `AbortController`로 중단 제어. (간편하게 가려면 `@microsoft/fetch-event-source`로 래핑 가능)

### 12.3 레포 구조: 모노레포 + dev 프록시
```
repo/
  backend/    # FastAPI
  frontend/   # Vite + React
```
- 개발 중 Vite `server.proxy`로 `/api` → FastAPI 프록시 → CORS 회피.

### 12.4 상태 관리: 최소
- 화면은 사실상 하나(질문 입력 / 도착 답변 카드 / 종합 패널 / 원본 접기 / 출처).
- `useReducer`로 스트림 이벤트를 상태에 reduce. 페르소나 답변은 `order` 정렬 배열, synthesis는 별도 슬롯, sources는 별도 슬롯.
- `423 Locked` 수신 시 입력 비활성화 + 리셋 버튼 노출.

---

## 13. 핵심 구현 노트

```python
# 그라운딩(1회) → 병렬 fan-out → 도착 순서 SSE → 종합
async def run_pipeline(question, judge_out, ctx):
    grounded = None
    if judge_out.needs_fresh_context:
        grounded = await perplexity_ground(judge_out.search_query)  # Sonar 1회
        yield sse("sources", {"sources": grounded.sources, "summary": grounded.short})

    personas = await load_personas(judge_out.selected_personas)
    tasks = [asyncio.create_task(call_persona(p, question, grounded, ctx)) for p in personas]
    order, results = 0, []
    for fut in asyncio.as_completed(tasks):
        ans = await fut          # 완료되는 것부터
        order += 1
        results.append(ans)
        yield sse("persona_answer", {**ans, "order": order})

    synthesis = await synthesize(question, results, grounded, ctx)
    yield sse("synthesis", synthesis)
```

- JSON을 기대하는 LLM 호출은 **프리앰블/백틱 제거 후 파싱**, 실패 시 1회 재시도.
- 페르소나 호출은 서로 독립 → 한 개 실패해도 나머지는 진행(부분 성공 허용).
- 그라운딩은 **fan-out 전 1회**. 페르소나가 개별 검색하지 않게 강제(비용 N배·결과 불일치 방지).
- 모든 외부 호출(LLM·Perplexity)은 타임아웃·재시도 스코프를 둔다.

---

## 14. 구현 순서 (Claude Code 작업 단위)

> 각 단계는 독립 실행/검증 가능해야 한다. 한 단계 끝나면 멈추고 동작 확인.

1. **모노레포 스캐폴드**: `backend/`(FastAPI, pydantic-settings, DB/Redis 연결, 헬스체크) + `frontend/`(Vite+React, dev 프록시).
2. **DB 스키마 + 마이그레이션 + 시드**(§4, §6.2/6.3 시드 데이터 포함).
3. **세션 API**: 생성/조회/리셋, Redis 상태(카운터·lock·히스토리).
4. **Judge**: 분류(A/B) + 페르소나 선택 + needs_fresh_context/search_query, 타입 인라인 매칭, JSON 파싱(§7.1).
5. **Grounding**: Perplexity Sonar 1회 호출 래퍼 + 트리밍 + 실패 폴백(§8).
6. **Persona fan-out**: 병렬 호출 + `as_completed` + 부분 성공 + grounded_context 공유 주입(§13).
7. **SSE 엔드포인트**: §5.2 이벤트 계약(judge/sources/persona_answer/synthesis)대로 스트리밍.
8. **Synthesizer**: 종합 + 강제 추천(§7.2).
9. **재질문 컨텍스트**: 윈도우 + 요약 압축, 근거 재사용(§9.1).
10. **한도/종료/리셋**: 재수없는 응답 + lock + 복구 경로(§10).
11. **프런트 통합**: fetch 스트리밍 파서, 답변 카드(도착순), 종합 패널, 원본 접기/펼치기, 출처 표시, 423 처리(§12).

---

## 15. 비범위 (지금은 안 한다)

- 벡터/임베딩 기반 타입 매칭 (타입 수십 개 넘어가면 그때).
- 외부 사실조회 전용 툴(날씨/환율 API) — `out_of_scope`로 거른다. (현재 정보 그라운딩은 Perplexity로 충분)
- 페르소나별 개별 검색 — 비용·일관성 문제로 금지. 그라운딩은 1회 공유.
- 토큰 단위 인터리빙(WebSocket) — SSE로 시작.
- 만능 Q&A 기능 일체.

---

## 16. 완료 정의 (DoD)

- 주관적 질문 1건 → 페르소나 N명 답변이 **도착 순서대로** 스트리밍되고, **단일 종합 결론 + 강제 추천**이 마지막에 나온다.
- 현재 정보가 필요한 질문 → Perplexity로 **1회** 검색해 근거를 전 페르소나에 공유하고, **출처가 사용자에게 노출**된다. (개별 검색이 일어나지 않는다)
- 사실조회 질문 → 답하지 않고 필터 메시지로 종료된다.
- 재질문 시 이전 맥락이 반영되되 토큰이 무한 증가하지 않는다.
- 재질문 한도 초과 → 재수없는 종료 + 리셋으로 복구 가능.
- 페르소나/모델/임계값/N/검색설정이 전부 DB 또는 설정으로 주입되며 코드 변경 없이 바뀐다.
- 프런트는 fetch 스트리밍으로 SSE를 파싱하며, `423 Locked` 시 입력이 비활성화되고 리셋 경로가 보인다.
