"""자연어 → 세탁 입력 필드 추출 (MVP_SPEC 12.9, VS4).

헬스장 추출(llm/extraction.py)과 같은 흐름이다: (마스킹된 문장) → LLMClient(JSON 스키마, few-shot)
→ 스키마 검증 → 근거 구절 확인(grounding.py) → 확인된 값만 fields, 나머지는 unverified/missing.

- 품목 행(item_key·variant_key·item_unlisted)은 LLM의 표 행 선택이다. 근거 구절이 문장에 있으면 채택하되
  항상 confirm에 넣어 폼에서 확인받는다 (코드가 구절과 표 행의 대응을 확인할 수 없으므로).
- 사용일수·배상비율·금액은 추출하지 않는다 (엔진만 계산, CLAUDE.md 절대 규칙 1).
- 결과는 화면 폼을 미리 채우는 데만 쓴다. 엔진에는 /api/calculate?item=laundry의 LaundryInput 검증을
  통과한 값만 전달된다 (rules/는 llm/을 import하지 않는다). 입력 문장과 LLM 응답은 저장·로그하지 않는다.
"""

import json
from datetime import date
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from llm.client import LLMClient, LLMError, LLMErrorKind, Turn
from llm.extraction import PROMPT_DIR, AnalyzeResult, FieldValue
from llm.grounding import (
    amounts_in,
    bool_grounded,
    dates_in,
    evidence_in_text,
    judgment_grounded,
)

SYSTEM_PROMPT_FILE = PROMPT_DIR / "laundry_extract_system.md"
EXAMPLES_FILE = PROMPT_DIR / "laundry_extract_examples.json"

# 규칙 JSON lifespan_table의 행 ID·소재/용도 키 (tests/test_llm_laundry_extraction.py가 JSON과 같은지 확인)
ITEM_KEYS: tuple[str, ...] = (
    "mens_suit",
    "coat",
    "womens_suit",
    "skirt_pants_jacket_jumper",
    "sportswear",
    "shirts",
    "blouse",
    "sweater",
    "jeans",
    "uniform",
    "hanbok",
    "carpet",
    "leather_bag",
    "fabric_bag",
    "scarf",
    "muffler",
    "necktie",
    "underwear",
    "leather_outer",
    "leather_other",
    "synthetic_leather",
    "blanket",
    "sofa",
    "curtain",
    "bedding",
    "shoes_leather_special",
    "shoes_general",
    "hat",
    "fur_outer",
    "fur_other",
)
VARIANT_KEYS: tuple[str, ...] = (
    "summer",
    "spring_fall",
    "winter",
    "silk",
    "other",
    "regular",
    "special_wash",
    "work",
    "office",
    "school",
    "wool",
    "silk_wool",
    "pigskin_reptile",
    "natural_leather",
    "spring_summer",
    "fall_winter",
    "rabbit",
)

ENUM_FIELDS: dict[str, tuple[str, ...]] = {
    "service_type": ("laundry_shop", "self_laundromat", "other"),
    "damage_type": ("defect", "loss", "other"),
    "item_key": ITEM_KEYS,
    "variant_key": VARIANT_KEYS,
    "set_type": ("none", "top_bottom", "top_mid_bottom", "hanbok"),
    "set_part": ("top", "mid", "bottom", "whole"),
}
AMOUNT_FIELDS = ("purchase_price", "laundry_fee", "provider_offer")
DATE_FIELDS = ("purchase_date", "request_date")
BOOL_FIELDS = (
    "item_unlisted",
    "proof_available",
    "manufacturing_cause_claimed",
    "attachment_only",
    "special_agreement",
    "customer_partial_fault",
    "wants_damaged_item",
    "no_issue_confirmation",
    "uncollected",
    "receipt_issued",
)
FIELD_NAMES: tuple[str, ...] = (
    *ENUM_FIELDS,
    *AMOUNT_FIELDS,
    *DATE_FIELDS,
    *BOOL_FIELDS,
)

# 표 행 선택: 단서 낱말로 확인할 수 없어 근거 구절만 확인하고 폼에서 확인받는다.
SELECTION_FIELDS = ("item_key", "variant_key", "item_unlisted")

# 채택해도 계산을 멈추게 하는(❔) 값 (12.2 순서 2~7). 폼에서 확인을 받는다.
STOP_VALUES: dict[str, tuple[FieldValue, ...]] = {
    "service_type": ("self_laundromat", "other"),
    "damage_type": ("other",),
    "manufacturing_cause_claimed": (True,),
    "set_part": ("top", "mid", "bottom"),
    "attachment_only": (True,),
}

# 채택하면 계산식이 바뀌는 값 (입증 불가 → 세탁요금 20배). 폼에서 확인을 받는다 [기본값 2026-11-10 B13].
ROUTE_VALUES: dict[str, tuple[FieldValue, ...]] = {"proof_available": (False,)}


def _py_type(name: str) -> Any:
    if name in ENUM_FIELDS:
        return Literal[ENUM_FIELDS[name]] | None  # type: ignore[valid-type]
    if name in AMOUNT_FIELDS:
        return int | None
    if name in DATE_FIELDS:
        return date | None
    return bool | None


_CONFIG = ConfigDict(extra="forbid", frozen=True)
ExtractedLaundryFields = create_model(  # type: ignore[call-overload]
    "ExtractedLaundryFields",
    __config__=_CONFIG,
    **{n: (_py_type(n), ...) for n in FIELD_NAMES},
)
LaundryEvidence = create_model(  # type: ignore[call-overload]
    "LaundryEvidence",
    __config__=_CONFIG,
    **{n: (str | None, ...) for n in FIELD_NAMES},
)


class RawLaundryExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    judgment_requested: bool
    judgment_evidence: str | None
    fields: ExtractedLaundryFields  # type: ignore[valid-type]
    evidence: LaundryEvidence  # type: ignore[valid-type]


def _field_schema(name: str) -> dict[str, Any]:
    if name in ENUM_FIELDS:
        return {
            "anyOf": [
                {"type": "string", "enum": list(ENUM_FIELDS[name])},
                {"type": "null"},
            ]
        }
    if name in AMOUNT_FIELDS:
        return {"type": ["integer", "null"], "minimum": 0}
    if name in DATE_FIELDS:
        return {"type": ["string", "null"], "format": "date"}
    return {"type": ["boolean", "null"]}


def response_schema() -> dict[str, Any]:
    """LLM에 강제할 JSON 스키마. 모든 키를 required로 둬 null을 명시하게 한다."""
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


@cache
def system_prompt() -> str:
    return SYSTEM_PROMPT_FILE.read_text(encoding="utf-8")


@cache
def few_shot_turns() -> tuple[Turn, ...]:
    """few-shot 예시. 입력은 가상 문장, 출력 값은 케이스 초안의 입력 값이다 (파일의 case 키)."""
    examples = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    turns: list[Turn] = []
    for ex in examples:
        RawLaundryExtraction.model_validate(ex["output"])
        turns.append(Turn(role="user", text=ex["input"]))
        turns.append(
            Turn(role="model", text=json.dumps(ex["output"], ensure_ascii=False))
        )
    return tuple(turns)


def _grounded(name: str, value: Any, evidence: str | None, text: str) -> bool:
    """근거 구절이 입력에 있고, 금액·날짜는 그 구절에서 코드가 읽은 값이 정확히 그 값 하나여야 한다."""
    if not evidence_in_text(evidence, text):
        return False
    assert evidence is not None
    if name in AMOUNT_FIELDS:
        return amounts_in(evidence) == {value}
    if name in DATE_FIELDS:
        return dates_in(evidence) == {value}
    if name in BOOL_FIELDS and name not in SELECTION_FIELDS:
        return bool_grounded(name, value, evidence)
    return True


def questions(fields: dict[str, FieldValue]) -> list[str]:
    """되물을 필수 항목 (12.2 누락 판정과 같은 갈래). 최종 판정은 엔진의 MISSING_REQUIRED다."""
    need = ["service_type", "damage_type", "proof_available"]
    proof = fields.get("proof_available")
    if proof is not False:
        if fields.get("item_unlisted") is not True:
            need.append("item_key")
        need += ["purchase_price", "purchase_date", "request_date"]
    if proof is not True:
        need.append("laundry_fee")
    if fields.get("set_type") not in (None, "none"):
        need.append("set_part")
    return [n for n in dict.fromkeys(need) if n not in fields]


def check_extraction(raw: RawLaundryExtraction, text: str) -> AnalyzeResult:
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
    confirm = [n for n in SELECTION_FIELDS if n in fields]
    confirm += [
        n
        for n, values in (*STOP_VALUES.items(), *ROUTE_VALUES.items())
        if n in fields and fields[n] in values
    ]
    return AnalyzeResult(
        fields=fields,
        evidence=evidence,
        unverified=unverified,
        missing=questions(fields),
        confirm=confirm,
        judgment_requested=judgment,
    )


def analyze_laundry_text(masked_text: str, client: LLMClient) -> AnalyzeResult:
    """마스킹된 문장을 LLM으로 추출하고 확인한다. 마스킹은 호출하는 쪽(api)이 먼저 한다."""
    turns = [*few_shot_turns(), Turn(role="user", text=masked_text)]
    out = client.generate_json(
        system=system_prompt(), turns=turns, response_schema=response_schema()
    )
    try:
        raw = RawLaundryExtraction.model_validate_json(out)
    except ValidationError:
        raise LLMError(LLMErrorKind.BAD_RESPONSE) from None
    return check_extraction(raw, masked_text)
