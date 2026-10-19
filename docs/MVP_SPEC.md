# MVP_SPEC — 기준대로

> 상태: **초안**. 현재 단계에 필요한 결정이 끝나기 전에는 그 단계를 구현하지 않는다. 결정이 나면 이 문서를 먼저 갱신한다.
> **현재 단계: 0 (고시 원문 확인)**

## 1. MVP 한 줄

헬스장 중도 해지 상황을 입력하면, 고시 기준의 환급액을 코드로 계산해 계산 과정·근거·상태 배지와 함께 보여 준다. (세탁·가전은 같은 구조에 규칙만 추가)

## 2. 왜 헬스장 하나로 시작하는가

- 계산식이 가장 단순해 "추출 → 규칙 엔진 → 근거 표시" 전체 흐름을 먼저 끝까지 연결할 수 있다.
- 세탁(배상비율표)·가전(내용연수·부품보유기간 표)은 원문 표 정리에 시간이 더 든다. 구조가 검증된 뒤에 얹는다.
- 이 순서는 결정 사항이며 바꾸려면 아래 9절에서 변경한다.

## 3. 범위

**포함**: 자유 문장 입력, 정보 추출(LLM, JSON 스키마), 헬스장 환급 계산(규칙 엔진), 근거 카드(조항 원문·출처·기준일), 상태 배지 4종, 판단 가드레일, 업체용 요약 문안, 결과 화면.
**제외**: 로그인, 사진·영수증 입력, 법률 문서 생성, 세탁·가전(MVP 이후), 데이터 저장.

## 4. 규칙 데이터 형식 (`backend/data/rules/gym_refund.json`)

```json
{
  "id": "gym_refund",
  "title": "체육시설업 중도 해지 환급",
  "source": { "name": "TODO", "url": "TODO", "retrieved_at": "TODO" },
  "verified": false,
  "params": { "penalty_cap_ratio": null },
  "clause_text": "TODO: 고시 원문 그대로"
}
```

값은 모두 원문 확인 후 채운다. `retrieved_at`은 `source` 안에 둔다. `verified=false`이면 계산은 하되 결과 배지는 `✅ 기준 확인`이 될 수 없다 (아래 배지 결정 순서 2번).

MVP(품목 1개)에서는 조항 검색 없이 품목 ID(`gym_refund`)로 이 파일을 직접 조회한다. 업종 필터 + 키워드 → 임베딩 검색은 품목이 2개 이상이 되는 단계 7에서 도입한다.

### 배지 결정 순서

위에서부터 판정하며 먼저 걸리는 것이 이긴다.

1. 판단 불가 조건(승패·법적 효력 질문 등)이면 `❔ 판단 불가`
2. `verified=false`이거나 필수 정보가 누락되었으면 `🔍 추가 확인 필요`
3. 주의 신호가 있으면 `⚠️ 주의 신호`
4. 그 외에는 `✅ 기준 확인`

## 5. 규칙 엔진 계약 (`backend/rules/gym.py`)

> 아래 필드명은 **임시**다. 단계 0의 원문 확인 결과에 따라 바뀔 수 있다.

입력(임시): `contract_amount: int`, `contract_days: int`, `used_days: int`, `penalty_cap_ratio: Decimal`, (선택) `provider_offer: int`
출력(임시): `refund: int`, `steps: list[Step]`(항목명·계산식·금액), `flags: list[str]`, `badge`
예시(검증 전 가상 수치, 흐름 설명용): 1,200,000원 / 12개월 / 3개월 이용 / 위약금 10% → 1,200,000 − 300,000 − 120,000 = **780,000원**. **이 수치는 테스트 기대값으로 쓰지 않는다.**

**단계 0 확인 후 확정** (그 전에는 단계 2 구현·테스트 값을 정하지 않는다):

- 입력 단위: 일 / 월 / 횟수
- 이용분 계산 방식: 일할 / 월할
- 이용분 기준 금액: 정상가 / 할인가
- 반올림 규칙 (단위·방식, 규칙 파일에 명시)

## 6. API (MVP)

| 엔드포인트 | 역할 |
|---|---|
| `POST /api/analyze` | 문장 → 추출 결과(`item`, `fields`, `missing`, `evidence`) |
| `POST /api/calculate` | 확정된 필드 → 계산 결과(`refund`, `steps`, `badge`, `source`) |
| `POST /api/guide` | 계산 결과 → 설명·업체용 문안·다음 행동 (인용 검증 포함) |

`/api/ask`(자유 질의)는 MVP 범위 밖이다.

## 7. 완료 기준 (MVP)

- [ ] 규칙 파일의 모든 값에 원문 출처가 있고 `verified=true`
- [ ] 규칙 엔진 pytest 케이스 10건 이상 전부 통과 (정답은 손계산)
- [ ] 입력 → 결과 화면이 끝까지 동작 (가상 사례 5건)
- [ ] 승패·법적 효력 질문 5건이 모두 `❔ 판단 불가`로 처리
- [ ] 결과 화면에 기준일·출처·"권고 기준" 고지 표시

## 8. 구현 순서

| 단계 | 내용 | 산출물 |
|---|---|---|
| 0 | 헬스장 관련 고시·위약금 산정기준 원문 확인 (사람이 확인, Claude Code는 정리 보조) | 규칙 JSON 초안, 출처 목록 |
| 1 | 저장소 뼈대: 폴더, `backend/pyproject.toml`, FastAPI health, Vite react-ts 앱, `.env.example`(`LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`), CI 없이 pytest 1건 | 실행 확인 |
| 2 | 규칙 엔진 + 테스트 (LLM 없음) | `rules/gym.py`, tests |
| 3 | 정보 추출 (LLM 어댑터, JSON 스키마, few-shot, temperature 0) | `/api/analyze` |
| 4 | 계산 API + 상태 배지 + 가드레일 | `/api/calculate` |
| 5 | 근거 카드·설명·업체용 문안 + 인용 검증 | `/api/guide` |
| 6 | 화면 3개 연결 (UI 예시 v0.1 기준) | 동작하는 MVP |
| 7 | 세탁·가전 규칙 추가, 조항 검색 도입(업종 필터 + 키워드 → 임베딩), 평가 30건, 범용 LLM 비교 | 평가 결과 |

단계 0이 끝나기 전에는 단계 2의 숫자를 확정하지 않는다. 단계 1은 0과 병행 가능.

## 9. 결정 사항과 남은 결정

**확정 (2026-10-19)**

1. MVP 첫 품목: 헬스장(체육시설업)
2. 프론트: TypeScript (`strict`, Vite react-ts 기본 템플릿, 라우터·UI·상태관리 라이브러리 없음)
3. 백엔드 배치: `backend/pyproject.toml`, `backend/.venv`, `backend/.env`. 실행은 `backend`에서 `uvicorn main:app --reload`
4. 단계 1 의존성: `fastapi`, `uvicorn`, `pydantic`, `pytest`, `httpx`, `ruff`(lint·format, black 미사용)

**남은 결정**

1. 사용할 무료 LLM API (키 발급 가능한 것) — 단계 3 전에 결정
2. 배포 대상 — 미정이면 6주차에 결정
