"""추출·근거 확인·되묻기 테스트 (가짜 LLMClient). 실제 API를 부르지 않는다.

기대값: 문장에서 그대로 읽히는 값(금액 표기, 날짜 표기)과 MVP_SPEC 5.1 필수 열만 쓴다.
few-shot 예시의 값은 승인 케이스 입력(test_gym_calc.CASES)과 대조한다.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest
from test_gym_calc import CASES

from llm.client import LLMError, LLMErrorKind, Turn
from llm.extraction import (
    EXAMPLES_FILE,
    FIELD_NAMES,
    RawExtraction,
    analyze_text,
    check_extraction,
    few_shot_turns,
    questions,
    response_schema,
    system_prompt,
)
from rules.gym import GymInput


@dataclass
class FakeClient:
    """정해진 JSON을 돌려주고, 받은 요청을 기록한다."""

    reply: str
    model: str = "fake-model"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls.append({"system": system, "turns": turns, "schema": response_schema})
        return self.reply


def raw(
    values: dict[str, tuple[Any, str | None]],
    judgment: str | None = None,
    judgment_flag: bool | None = None,
) -> dict[str, Any]:
    fields = {n: None for n in FIELD_NAMES}
    evidence: dict[str, str | None] = {n: None for n in FIELD_NAMES}
    for k, (v, e) in values.items():
        fields[k] = v
        evidence[k] = e
    return {
        "judgment_requested": judgment is not None
        if judgment_flag is None
        else judgment_flag,
        "judgment_evidence": judgment,
        "fields": fields,
        "evidence": evidence,
    }


TEXT = (
    "헬스장 1년권을 2026-01-01부터 2026-12-31까지 120만원에 결제했고 "
    "이사 때문에 2026-03-31에 해지 요청했어요."
)


def check(values: dict[str, tuple[Any, str | None]], text: str = TEXT, **kw: Any):
    return check_extraction(RawExtraction.model_validate(raw(values, **kw)), text)


def test_grounded_values_pass() -> None:
    r = check(
        {
            "industry": ("fitness", "헬스장 1년권"),
            "contract_type": ("period", "헬스장 1년권"),
            "termination_cause": ("consumer", "이사 때문에"),
            "total_contract_amount": (1_200_000, "120만원에 결제했고"),
            "paid_amount": (1_200_000, "120만원에 결제했고"),
            "start_date": ("2026-01-01", "2026-01-01부터"),
            "end_date": ("2026-12-31", "2026-12-31까지"),
            "notice_date": ("2026-03-31", "2026-03-31에 해지 요청"),
        }
    )
    assert r.unverified == []
    assert r.missing == []
    assert r.fields["total_contract_amount"] == 1_200_000
    assert r.fields["start_date"] == "2026-01-01"
    assert r.evidence["termination_cause"] == "이사 때문에"
    assert r.judgment_requested is False


@pytest.mark.parametrize(
    ("name", "value", "ev"),
    [
        ("total_contract_amount", 1_000_000, "120만원에 결제했고"),  # 값이 근거와 다름
        ("paid_amount", 1_200_000, "120만원을 냈어요"),  # 근거가 입력에 없음
        ("paid_amount", 1_200_000, None),  # 근거 없음
        ("list_price", 1_500_000, "헬스장 1년권"),  # 근거에 금액이 없음
        ("start_date", "2026-01-02", "2026-01-01부터"),
        ("used_sessions", 3, "헬스장 1년권"),
        ("industry", "fitness", "필라테스"),  # 범주 값도 근거가 입력에 있어야 한다
        # 근거 구절에 같은 종류 후보가 여럿이면 어느 값인지 확인할 수 없어 받지 않는다
        (
            "notice_date",
            "2026-03-31",
            "2026-12-31까지 120만원에 결제했고 이사 때문에 2026-03-31",
        ),
    ],
)
def test_ungrounded_values_dropped(name: str, value: Any, ev: str | None) -> None:
    r = check({name: (value, ev)})
    assert name not in r.fields
    assert r.unverified == [name]


def test_date_without_year_rejected() -> None:
    text = "3월 1일부터 다녔어요"
    r = check({"start_date": ("2026-03-01", "3월 1일부터")}, text=text)
    assert "start_date" not in r.fields
    assert "start_date" in r.unverified


def test_refund_basis_none_vs_unknown() -> None:
    text = "필라테스 20회권인데 환불 기준을 정했는지는 모르겠어요"
    base = {
        "industry": ("yoga_pilates", "필라테스 20회권"),
        "contract_type": ("session", "필라테스 20회권"),
    }
    said_unknown = check(
        {**base, "refund_basis": ("unknown", "환불 기준을 정했는지는 모르겠어요")},
        text=text,
    )
    assert said_unknown.fields["refund_basis"] == "unknown"
    assert "refund_basis" not in said_unknown.missing

    not_said = check(base, text=text)
    assert "refund_basis" not in not_said.fields
    assert "refund_basis" in not_said.missing  # None = 누락 → 되묻기

    # "unknown"도 근거 없이 오면 받지 않는다
    no_ev = check({**base, "refund_basis": ("unknown", None)}, text=text)
    assert "refund_basis" not in no_ev.fields
    assert "refund_basis" in no_ev.unverified


def test_judgment_needs_evidence() -> None:
    text = "업체가 환불을 안 해 줘요. 소송하면 이길까요"
    assert check({}, text=text, judgment="소송하면 이길까요").judgment_requested
    assert not check(
        {}, text=text, judgment="소송으로 이길까요"
    ).judgment_requested  # 문장에 없음
    assert not check(
        {}, text=text, judgment=None, judgment_flag=True
    ).judgment_requested


def test_questions_follow_spec_required_column() -> None:
    assert questions({}) == [
        "industry",
        "contract_type",
        "termination_cause",
        "total_contract_amount",
        "paid_amount",
        "start_date",
        "end_date",
        "notice_date",
        "total_sessions",
        "used_sessions",
    ]
    period = {
        "industry": "fitness",
        "contract_type": "period",
        "termination_cause": "consumer",
        "total_contract_amount": 1,
        "paid_amount": 1,
    }
    assert questions(period) == ["start_date", "end_date", "notice_date"]
    session = {**period, "contract_type": "session"}
    assert questions(session) == ["total_sessions", "used_sessions"]
    assert questions({**session, "end_date": "2026-05-31"}) == [
        "total_sessions",
        "used_sessions",
        "notice_date",
    ]
    yoga = {**period, "industry": "yoga_pilates"}
    assert questions(yoga)[0] == "refund_basis"
    assert "total_sessions" in questions(yoga)  # 기준 미상이면 두 기준 모두
    assert questions({**session, "add_on_returned": True})[-1] == (
        "returned_add_on_value"
    )


def test_analyze_text_sends_prompt_schema_and_fewshot() -> None:
    reply = json.dumps(raw({"industry": ("fitness", "헬스장 1년권")}))
    client = FakeClient(reply)
    r = analyze_text(TEXT, client)
    assert r.fields == {"industry": "fitness"}
    call = client.calls[0]
    assert call["system"] == system_prompt()
    assert call["schema"] == response_schema()
    assert call["turns"][-1] == Turn("user", TEXT)
    assert tuple(call["turns"][:-1]) == few_shot_turns()


@pytest.mark.parametrize(
    "reply",
    [
        "not json",
        "{}",
        json.dumps({**raw({}), "extra": 1}),
        json.dumps(raw({"industry": ("swimming", "수영")})),
        json.dumps(raw({"total_contract_amount": ("120만원", "120만원")})),
    ],
)
def test_bad_llm_output_is_error(reply: str) -> None:
    with pytest.raises(LLMError) as exc:
        analyze_text(TEXT, FakeClient(reply))
    assert exc.value.kind == LLMErrorKind.BAD_RESPONSE
    assert TEXT not in str(exc.value)


def test_schema_covers_all_fields_and_marks_required() -> None:
    s = response_schema()
    assert s["properties"]["fields"]["required"] == list(FIELD_NAMES)
    assert s["properties"]["evidence"]["required"] == list(FIELD_NAMES)
    rb = s["properties"]["fields"]["properties"]["refund_basis"]
    assert {"type": "null"} in rb["anyOf"]
    assert {"type": "string", "enum": ["period", "session", "unknown"]} in rb["anyOf"]
    # 추출 필드 이름은 모두 GymInput 필드다 (judgment_requested는 따로 받는다)
    assert set(FIELD_NAMES) == set(GymInput.model_fields) - {"judgment_requested"}


# ---- few-shot 예시: 승인 케이스 입력과 대조 ----

EXAMPLES = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
CASE_BY_ID = {c.id: c for c in CASES}


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e["case"])
def test_few_shot_values_come_from_approved_case(ex: dict[str, Any]) -> None:
    case = CASE_BY_ID[ex["case"]]
    for name, value in ex["output"]["fields"].items():
        if value is None:
            continue
        expected = getattr(case.inp, name)
        if isinstance(expected, date):
            expected = expected.isoformat()
        assert value == expected, f"{ex['case']}.{name}"


@pytest.mark.parametrize("ex", EXAMPLES, ids=lambda e: e["case"])
def test_few_shot_examples_pass_grounding(ex: dict[str, Any]) -> None:
    r = check_extraction(RawExtraction.model_validate(ex["output"]), ex["input"])
    assert r.unverified == []
    filled = {k for k, v in ex["output"]["fields"].items() if v is not None}
    assert set(r.fields) == filled


def test_few_shot_has_none_and_unknown_refund_basis() -> None:
    yoga = [e for e in EXAMPLES if e["output"]["fields"]["industry"] == "yoga_pilates"]
    values = {e["output"]["fields"]["refund_basis"] for e in yoga}
    assert values >= {None, "unknown"}
