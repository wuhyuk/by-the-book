"""조항 후보를 추출 호출 한 번에 넣고 LLM이 고른 조항 ID를 검증한다 (기능 플래그 rag, MVP_SPEC 15.2, 2026-11-16).

- 프롬프트에는 후보의 ID·제목·저장된 본문 앞부분만 넣는다 (마스킹한 사용자 문장은 기존대로 turns에 있다).
- 스키마에 clause_ids(문자열 목록, 후보 ID만 허용)를 더한다. 자유 서술 이유는 받지 않는다.
- 응답 검증: 후보에 없는 ID는 버리고 중복은 처음 것만 남긴다. 모두 버려지면 빈 목록.
- 호출 횟수는 늘리지 않는다 (기존 추출 호출 한 번에 함께 받는다). LLM이 쓴 문장은 어디에도 내보내지 않는다.
"""

import copy
import json
from collections.abc import Sequence
from typing import Any

from llm.client import LLMClient, LLMError, LLMErrorKind, Turn
from rag.search import Candidate

CLAUSE_IDS_KEY = "clause_ids"

CLAUSE_PROMPT_HEADER = """
## 관련 조항 후보 (자동 검색)

아래는 입력 문장으로 자동 검색한 조항 후보입니다. 입력 문장의 상황과 직접 관련된 조항의 ID만 clause_ids에 넣으세요.
- 후보 목록에 있는 ID만 쓸 수 있습니다. 새 ID를 만들지 마세요.
- 관련된 조항이 없으면 빈 목록 []을 넣으세요.
- 이유나 설명은 쓰지 마세요.
- 조항 본문의 숫자·날짜를 fields 값으로 옮기지 마세요. fields는 입력 문장에서만 채웁니다.

후보:
""".strip()


def clause_prompt(candidates: Sequence[Candidate]) -> str:
    lines = [f"- {c.clause_id}: {c.title} — {c.excerpt}" for c in candidates]
    return CLAUSE_PROMPT_HEADER + "\n" + "\n".join(lines)


def with_clause_ids(
    schema: dict[str, Any], candidates: Sequence[Candidate]
) -> dict[str, Any]:
    """기존 응답 스키마에 clause_ids를 더한 사본 (원본은 바꾸지 않는다)."""
    out = copy.deepcopy(schema)
    out["properties"][CLAUSE_IDS_KEY] = {
        "type": "array",
        "items": {"type": "string", "enum": [c.clause_id for c in candidates]},
    }
    out["required"] = [*out["required"], CLAUSE_IDS_KEY]
    return out


def split_clause_ids(out: str) -> tuple[str, list[str]]:
    """LLM 응답 JSON에서 clause_ids를 떼어 낸다 → (기존 스키마 JSON 문자열, ID 목록).

    clause_ids가 없거나 문자열 목록이 아니면 빈 목록으로 본다 (추출 결과는 그대로 쓴다).
    JSON이 아니면 기존과 같이 BAD_RESPONSE.
    """
    try:
        data = json.loads(out)
    except ValueError:
        raise LLMError(LLMErrorKind.BAD_RESPONSE) from None
    if not isinstance(data, dict):
        raise LLMError(LLMErrorKind.BAD_RESPONSE)
    raw = data.pop(CLAUSE_IDS_KEY, [])
    ids = [x for x in raw if isinstance(x, str)] if isinstance(raw, list) else []
    return json.dumps(data, ensure_ascii=False), ids


def select_valid(ids: Sequence[str], candidates: Sequence[Candidate]) -> list[str]:
    """후보에 있는 ID만, 처음 나온 순서대로 한 번씩."""
    allowed = {c.clause_id for c in candidates}
    return [i for i in dict.fromkeys(ids) if i in allowed]


def generate_with_clauses(
    client: LLMClient,
    *,
    system: str,
    turns: list[Turn],
    schema: dict[str, Any],
    candidates: Sequence[Candidate] | None,
) -> tuple[str, list[str] | None]:
    """후보가 없으면(None·빈 목록) 기존 호출 그대로 → (응답, None).

    후보가 있으면 같은 호출 한 번에 후보와 clause_ids 스키마를 더한다 → (clause_ids를 뗀 응답, 검증한 ID 목록).
    """
    if not candidates:
        return client.generate_json(
            system=system, turns=turns, response_schema=schema
        ), None
    out = client.generate_json(
        system=f"{system}\n\n{clause_prompt(candidates)}",
        turns=turns,
        response_schema=with_clause_ids(schema, candidates),
    )
    body, ids = split_clause_ids(out)
    return body, select_valid(ids, candidates)
