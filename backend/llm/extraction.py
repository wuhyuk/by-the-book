"""자연어 → 헬스장 입력 필드 추출 (MVP_SPEC 6절 /api/analyze, 8.1 VS3).

흐름: (마스킹된 문장) → LLMClient(JSON 스키마 강제, temperature 0, few-shot) → 스키마 검증
→ 근거 구절 확인(grounding.py) → 확인된 값만 fields, 나머지는 unverified/missing으로 돌려 되묻는다.

- 이 모듈은 제공자와 무관하다. 프롬프트는 prompts/ 파일에 둔다.
- 결과는 화면 폼을 미리 채우는 데만 쓴다. 엔진에는 사용자가 폼에서 확인한 값이
  /api/calculate의 GymInput 검증을 통과한 뒤에만 전달된다 (rules/는 llm/을 import하지 않는다).
- 입력 문장과 LLM 응답을 저장·로그하지 않는다.
"""

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from llm.client import LLMClient, LLMError, LLMErrorKind, Turn
from llm.grounding import (
    amounts_in,
    bool_grounded,
    counts_in,
    dates_in,
    evidence_in_text,
    judgment_grounded,
)

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SYSTEM_PROMPT_FILE = PROMPT_DIR / "gym_extract_system.md"
EXAMPLES_FILE = PROMPT_DIR / "gym_extract_examples.json"

ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "industry": ("fitness", "yoga_pilates", "other"),
    "termination_cause": ("consumer", "business", "force_majeure", "unknown"),
    "contract_type": ("period", "session"),
    "refund_basis": ("period", "session", "unknown"),
}
AMOUNT_FIELDS = (
    "total_contract_amount",
    "paid_amount",
    "add_on_value",
    "returned_add_on_value",
    "deposit",
    "list_price",
    "contract_penalty",
    "provider_offer",
)
COUNT_FIELDS = ("total_sessions", "used_sessions")
DATE_FIELDS = ("start_date", "end_date", "notice_date")
BOOL_FIELDS = (
    "academy_law_applies",
    "is_withdrawal",
    "withdrawal_cleared",
    "add_on_returned",
    "has_refund_limit_clause",
    "had_postponement",
    "is_pt_only",
)
FIELD_NAMES: tuple[str, ...] = (
    *ENUM_FIELDS,
    *AMOUNT_FIELDS,
    *COUNT_FIELDS,
    *DATE_FIELDS,
    *BOOL_FIELDS,
)

FieldValue = str | int | bool

# 채택해도 계산을 멈추게 하는(❔) 값 (MVP_SPEC 5.2 순서 2~8). 폼에서 사용자에게 확인을 받는다.
STOP_VALUES: dict[str, tuple[FieldValue, ...]] = {
    "industry": ("other",),
    "termination_cause": ("business", "force_majeure"),
    "is_withdrawal": (True,),
    "academy_law_applies": (True,),
    "has_refund_limit_clause": (False,),
}


# ---- LLM 출력 스키마 ----


class ExtractedFields(BaseModel):
    """LLM이 채우는 값. null = 문장에 없음. 이름은 GymInput과 같다."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    industry: Literal["fitness", "yoga_pilates", "other"] | None
    termination_cause: (
        Literal["consumer", "business", "force_majeure", "unknown"] | None
    )
    contract_type: Literal["period", "session"] | None
    # None(문장에 없음 = 누락)과 "unknown"(사용자가 모른다고 말함)을 구분한다 (MVP_SPEC 5.1).
    refund_basis: Literal["period", "session", "unknown"] | None
    total_contract_amount: int | None
    paid_amount: int | None
    add_on_value: int | None
    returned_add_on_value: int | None
    deposit: int | None
    list_price: int | None
    contract_penalty: int | None
    provider_offer: int | None
    total_sessions: int | None
    used_sessions: int | None
    start_date: date | None
    end_date: date | None
    notice_date: date | None
    academy_law_applies: bool | None
    is_withdrawal: bool | None
    withdrawal_cleared: bool | None
    add_on_returned: bool | None
    has_refund_limit_clause: bool | None
    had_postponement: bool | None
    is_pt_only: bool | None


class Evidence(BaseModel):
    """필드별 근거 구절 (입력 문장에서 그대로 옮긴 부분). 값이 null이면 근거도 null."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    industry: str | None
    termination_cause: str | None
    contract_type: str | None
    refund_basis: str | None
    total_contract_amount: str | None
    paid_amount: str | None
    add_on_value: str | None
    returned_add_on_value: str | None
    deposit: str | None
    list_price: str | None
    contract_penalty: str | None
    provider_offer: str | None
    total_sessions: str | None
    used_sessions: str | None
    start_date: str | None
    end_date: str | None
    notice_date: str | None
    academy_law_applies: str | None
    is_withdrawal: str | None
    withdrawal_cleared: str | None
    add_on_returned: str | None
    has_refund_limit_clause: str | None
    had_postponement: str | None
    is_pt_only: str | None


class RawExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    judgment_requested: bool
    judgment_evidence: str | None
    fields: ExtractedFields
    evidence: Evidence


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _field_schema(name: str) -> dict[str, Any]:
    if name in ENUM_FIELDS:
        return _nullable({"type": "string", "enum": list(ENUM_FIELDS[name])})
    if name in AMOUNT_FIELDS or name in COUNT_FIELDS:
        return {"type": ["integer", "null"], "minimum": 0}
    if name in DATE_FIELDS:
        return {"type": ["string", "null"], "format": "date"}
    return {"type": ["boolean", "null"]}


def response_schema() -> dict[str, Any]:
    """LLM에 강제할 JSON 스키마 (Gemini responseJsonSchema). 모든 키를 required로 둬 null을 명시하게 한다."""
    names = list(FIELD_NAMES)
    return {
        "type": "object",
        "properties": {
            "judgment_requested": {"type": "boolean"},
            "judgment_evidence": {"type": ["string", "null"]},
            "fields": {
                "type": "object",
                "properties": {n: _field_schema(n) for n in names},
                "required": names,
            },
            "evidence": {
                "type": "object",
                "properties": {n: {"type": ["string", "null"]} for n in names},
                "required": names,
            },
        },
        "required": ["judgment_requested", "judgment_evidence", "fields", "evidence"],
    }


# ---- 프롬프트 ----


@cache
def system_prompt() -> str:
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")


@cache
def few_shot_turns() -> tuple[Turn, ...]:
    """few-shot 예시. 입력은 가상 문장, 출력 값은 승인 케이스 입력에서 가져왔다 (파일의 case 키)."""
    examples = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    turns: list[Turn] = []
    for ex in examples:
        RawExtraction.model_validate(ex["output"])  # 예시도 스키마를 지킨다
        turns.append(Turn(role="user", text=ex["input"]))
        turns.append(
            Turn(role="model", text=json.dumps(ex["output"], ensure_ascii=False))
        )
    return tuple(turns)


# ---- 확인과 되묻기 ----


class AnalyzeResult(BaseModel):
    """추출 결과. fields에는 근거 확인을 통과한 값만 있다."""

    model_config = ConfigDict(frozen=True)

    fields: dict[str, FieldValue]
    evidence: dict[str, str]
    unverified: list[str]
    missing: list[str]
    confirm: list[str]  # 채택했지만 계산을 멈추게 하는 값 → 폼에서 확인 안내
    judgment_requested: bool


def _grounded(name: str, value: Any, evidence: str | None, text: str) -> bool:
    """근거 구절이 입력에 있고, 숫자·날짜는 그 구절에서 코드가 읽은 값과 같아야 한다.

    구절에 같은 종류의 후보가 여럿이면(예: "2026-01-01부터 다녔고 2026-03-31에 해지") 어느 값이
    이 필드인지 코드가 확인할 수 없으므로 받지 않는다. 후보가 정확히 그 값 하나일 때만 받는다.
    """
    if not evidence_in_text(evidence, text):
        return False
    assert evidence is not None
    if name in AMOUNT_FIELDS:
        return amounts_in(evidence) == {value}
    if name in COUNT_FIELDS:
        return counts_in(evidence) == {value}
    if name in DATE_FIELDS:
        return dates_in(evidence) == {value}
    if name in BOOL_FIELDS:
        return bool_grounded(name, value, evidence)
    return True


def questions(fields: dict[str, FieldValue]) -> list[str]:
    """되물을 필수 항목 (MVP_SPEC 5.1 '필수' 열). 질문 목록용이고, 최종 판정은 엔진의 MISSING_REQUIRED다."""
    need = ["industry", "contract_type", "termination_cause"]
    need += ["total_contract_amount", "paid_amount"]
    industry = fields.get("industry")
    if industry == "yoga_pilates":
        need.append("refund_basis")
        basis = fields.get("refund_basis")
    else:
        basis = fields.get("contract_type")
    if basis in (None, "unknown", "period"):
        need += ["start_date", "end_date", "notice_date"]
    if basis in (None, "unknown", "session"):
        need += ["total_sessions", "used_sessions"]
        if "end_date" in fields:
            need.append("notice_date")
    if fields.get("add_on_returned") is True:
        need.append("returned_add_on_value")
    seen: list[str] = []
    for n in need:
        if n not in fields and n not in seen:
            seen.append(n)
    return seen


def check_extraction(raw: RawExtraction, text: str) -> AnalyzeResult:
    """LLM 출력에서 근거가 확인된 값만 남긴다. text는 LLM에 보낸 마스킹된 문장이다."""
    values = raw.fields.model_dump()
    evidences = raw.evidence.model_dump()
    fields: dict[str, FieldValue] = {}
    evidence: dict[str, str] = {}
    unverified: list[str] = []
    for name in FIELD_NAMES:
        value = values[name]
        if value is None:
            continue
        ev = evidences[name]
        if _grounded(name, value, ev, text):
            fields[name] = value.isoformat() if isinstance(value, date) else value
            evidence[name] = ev
        else:
            unverified.append(name)
    judgment = raw.judgment_requested and judgment_grounded(raw.judgment_evidence, text)
    confirm = [
        n for n, stop in STOP_VALUES.items() if n in fields and fields[n] in stop
    ]
    return AnalyzeResult(
        fields=fields,
        evidence=evidence,
        unverified=unverified,
        missing=questions(fields),
        confirm=confirm,
        judgment_requested=judgment,
    )


def analyze_text(masked_text: str, client: LLMClient) -> AnalyzeResult:
    """마스킹된 문장을 LLM으로 추출하고 확인한다. 마스킹은 호출하는 쪽(api)이 먼저 한다."""
    turns = [*few_shot_turns(), Turn(role="user", text=masked_text)]
    out = client.generate_json(
        system=system_prompt(), turns=turns, response_schema=response_schema()
    )
    try:
        raw = RawExtraction.model_validate_json(out)
    except ValidationError:
        raise LLMError(LLMErrorKind.BAD_RESPONSE) from None
    return check_extraction(raw, masked_text)
