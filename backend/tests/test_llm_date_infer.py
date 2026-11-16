"""연도 없는 날짜 보완(기능 플래그 date_year_infer)과 '미룬 적 없다' 단서 (2026-11-16, 헬스장 추출만).

가짜 LLM만 쓴다 (키·네트워크 없음). 문장은 사용자가 승인한 비교표 질문문
(docs/sources/eval_compare_sheet.md C1·N2·P1·H1), 2026-11-16 지시로 승인한 결합 규칙 확인 문장 두 개,
비움 확인 문장뿐이다.
가짜 LLM은 실제 프롬프트 규칙대로 연도 없는 날짜를 null로 둔다 (prompts/gym_extract_system.md 15~16줄).
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.analyze import get_client_provider
from api.settings import AppSettings, get_app_settings
from llm.client import Turn
from llm.date_infer import add_months, infer_years
from llm.extraction import FIELD_NAMES, RawExtraction, check_extraction
from llm.grounding import bool_grounded
from main import app

client = TestClient(app)
FLAG = "date_year_infer"

# ---- 승인 문장 (비교표 질문문 그대로) ----
C1 = (
    "헬스장 6개월 이용권을 할인 없이 정상가 60만원에 한 번에 결제했어요. 이용 기간은 2026년 3월 1일부터 "
    "8월 31일까지인데, 시작하기 전인 2월 20일에 사정이 생겨서 해지하겠다고 헬스장에 알렸어요. 계약서에 "
    "중도 해지하면 위약금이 있다는 조항은 있는데 금액은 안 적혀 있어요. 청약철회 기간은 이미 지났고 "
    "이용을 연기한 적은 없어요. 공정위 기준으로 환급 금액이 얼마인가요?"
)
N2 = (
    "필라테스 30회권을 정상가 90만원인데 할인받아 60만원에 결제했어요. 유효기간은 2026년 3월 1일부터 "
    "8월 31일까지이고 환불은 횟수 기준으로 하기로 했어요. 10회 수업을 듣고 5월 1일에 그만두겠다고 "
    "말했어요. 계약서에 중도 해지 시 위약금 조항은 있지만 금액은 없고, 연기한 적은 없어요. 업체는 "
    "20만원만 돌려주겠다는데 기준대로라면 얼마를 돌려받아야 하나요?"
)
P1 = (
    "헬스장 1년 회원권(2026년 1월 1일부터 12월 31일까지)을 120만원에 일시불로 결제했어요. 3월 31일에 "
    "해지하겠다고 헬스장에 알렸고 이용을 연기한 적은 없어요. 계약서에는 중도 해지하면 위약금이 있다고만 "
    "적혀 있고 금액은 없어요. 할인 전 정상가는 잘 모르겠어요. 환급 금액은 얼마가 맞나요?"
)
H1 = (
    "헬스장 6개월권(2026년 3월 1일부터 8월 31일까지)을 60만원에 결제했고 4월 1일에 해지하겠다고 "
    "전달했어요. 계약서를 다시 봤는데 중도에 해지할 때 환불을 제한하거나 위약금을 받는다는 조항이 아예 "
    "없어요. 연기한 적도 없고요. 이 경우 환급액은 얼마인가요?"
)
# 결합 규칙 확인 문장 (2026-11-16 사용자 승인 테스트 입력)
# 다른 절의 "시작 전"은 해지일 후보 선택에 쓰지 않는다
FAR_BEFORE_START = (
    "2026년 3월 1일부터 8월 31일까지 헬스장 6개월권을 60만원에 결제했어요. "
    "시작 전에 결제를 마쳤고, 5월 1일에 해지하겠다고 말했어요."
)
# 해지 단서는 가장 가까운 앞쪽 날짜(3월 5일)에만 결합한다
NEAREST_DATE = (
    "2026년 3월 1일부터 8월 31일까지 헬스장 6개월권을 60만원에 결제했어요. "
    "2월 20일에 결제했고 3월 5일에 해지하겠다고 말했어요."
)

# ---- 비움 확인 문장 ----
NO_ANCHOR = "3월 1일부터 8월 31일까지"
TWO_CANDIDATES = "2026년 1월 1일부터 2027년 12월 31일까지 쓰는 헬스장 회원권인데 3월 31일에 해지하겠다고 했어요."
NOTICE_AFTER_END = "2026년 3월 1일부터 8월 31일까지 쓰는 헬스장 6개월권인데 10월 1일에 해지하겠다고 했어요."
DURATION_MISMATCH = "2026년 3월 1일부터 8월 31일까지 쓰는 헬스장 3개월권인데 4월 1일에 해지하겠다고 했어요."
YEAR_GIVEN = "2026년 3월 1일부터 8월 31일까지 쓰는 헬스장 6개월권인데 2026년 4월 1일에 해지하겠다고 했어요."

START_0301 = {"start_date": "2026-03-01"}


def inferred(text: str, fields: dict[str, Any]) -> dict[str, tuple[date, str]]:
    return {i.field: (i.value, i.evidence) for i in infer_years(text, fields)}


# ---- 규칙 (순수 함수) ----


@pytest.mark.parametrize(
    ("text", "start", "end", "notice", "notice_ev"),
    [
        (C1, "2026-03-01", date(2026, 8, 31), date(2026, 2, 20), "2월 20일에 사정이 생겨서 해지"),
        (N2, "2026-03-01", date(2026, 8, 31), date(2026, 5, 1), "5월 1일에 그만두"),
        (P1, "2026-01-01", date(2026, 12, 31), date(2026, 3, 31), "3월 31일에 해지"),
        (H1, "2026-03-01", date(2026, 8, 31), date(2026, 4, 1), "4월 1일에 해지"),
    ],
)  # fmt: skip
def test_approved_sentences(
    text: str, start: str, end: date, notice: date, notice_ev: str
) -> None:
    got = inferred(text, {"start_date": start})
    assert got["end_date"][0] == end
    assert got["notice_date"] == (notice, notice_ev)
    for _, ev in got.values():
        assert ev in text  # 근거는 문장의 원문 구절 그대로


@pytest.mark.parametrize(
    ("text", "notice", "notice_ev"),
    [
        (FAR_BEFORE_START, date(2026, 5, 1), "5월 1일에 해지"),
        (NEAREST_DATE, date(2026, 3, 5), "3월 5일에 해지"),
    ],
)
def test_binding_rules(text: str, notice: date, notice_ev: str) -> None:
    got = inferred(text, START_0301)
    assert got["end_date"] == (date(2026, 8, 31), "8월 31일까지")
    assert got["notice_date"] == (notice, notice_ev)


def test_end_evidence_is_month_day_text() -> None:
    assert inferred(C1, START_0301)["end_date"][1] == "8월 31일까지"


def test_no_anchor_year() -> None:
    assert infer_years(NO_ANCHOR, {}) == []


def test_two_notice_candidates() -> None:
    fields = {"start_date": "2026-01-01", "end_date": "2027-12-31"}
    assert infer_years(TWO_CANDIDATES, fields) == []


def test_notice_after_end_not_filled() -> None:
    got = inferred(NOTICE_AFTER_END, START_0301)
    assert got["end_date"][0] == date(2026, 8, 31)
    assert "notice_date" not in got


def test_duration_mismatch_leaves_end_and_notice_empty() -> None:
    assert infer_years(DURATION_MISMATCH, START_0301) == []


def test_existing_year_date_not_overwritten() -> None:
    fields = {"start_date": "2026-03-01", "notice_date": "2026-04-01"}
    got = inferred(YEAR_GIVEN, fields)
    assert set(got) == {"end_date"}


def test_add_months_clamps_to_month_end() -> None:
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 1), -12) == date(2025, 3, 1)


# ---- '미룬 적 없다' 단서 (헬스장 had_postponement, 플래그와 무관) ----


@pytest.mark.parametrize(
    "evidence",
    [
        "이용을 미룬 적 없어요",
        "미룬 적은 없어요",
        "미루지 않았어요",
        "연기한 적 없어요",
        "연기하지 않았어요",
        "일시정지한 적 없어요",
        "일시정지하지 않았어요",
    ],
)
def test_postponement_negation_accepted(evidence: str) -> None:
    assert bool_grounded("had_postponement", False, evidence)


def test_miroon_is_not_a_true_cue() -> None:
    """'미룬'은 아니오 단서로만 쓴다. 예(True)는 기존 단서(미뤘·미루·연기 등)만."""
    assert not bool_grounded("had_postponement", True, "미룬 적은 없어요")
    assert not bool_grounded("had_postponement", False, "한 달 미룬 적 있어요")
    assert bool_grounded("had_postponement", True, "한 달 미뤘어요")


# ---- /api/analyze (가짜 LLM) ----


@dataclass
class RecordingClient:
    reply: str
    model: str = "fake-model"
    calls: list[tuple[str, list[Turn], dict[str, Any]]] = field(default_factory=list)

    def generate_json(
        self, *, system: str, turns: list[Turn], response_schema: dict[str, Any]
    ) -> str:
        self.calls.append((system, turns, response_schema))
        return self.reply


def raw(fields: dict[str, Any], evidence: dict[str, str]) -> dict[str, Any]:
    return {
        "judgment_requested": False,
        "judgment_evidence": None,
        "fields": {n: fields.get(n) for n in FIELD_NAMES},
        "evidence": {n: evidence.get(n) for n in FIELD_NAMES},
    }


def llm_reply(text: str, start_ev: str, postpone_ev: str, **extra: Any) -> str:
    """연도 없는 종료일·도달일은 null (프롬프트 규칙). 금액은 C1의 60만원."""
    fields = {
        "industry": "fitness",
        "contract_type": "period",
        "termination_cause": "consumer",
        "total_contract_amount": 600_000,
        "paid_amount": 600_000,
        "start_date": "2026-03-01",
        "had_postponement": False,
        **extra.get("fields", {}),
    }
    ev = {
        "industry": "헬스장",
        "contract_type": "6개월",
        "termination_cause": "사정이 생겨서",
        "total_contract_amount": "60만원에 한 번에 결제",
        "paid_amount": "60만원에 한 번에 결제",
        "start_date": start_ev,
        "had_postponement": postpone_ev,
        **extra.get("evidence", {}),
    }
    for v in ev.values():
        assert v in text
    return json.dumps(raw(fields, ev), ensure_ascii=False)


@pytest.fixture
def setup() -> Iterator[Callable[..., RecordingClient]]:
    def _setup(reply: str, *features: str) -> RecordingClient:
        fake = RecordingClient(reply)
        app.dependency_overrides[get_client_provider] = lambda: lambda: fake
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=features
        )
        return fake

    yield _setup
    app.dependency_overrides.clear()


def post(text: str) -> dict[str, Any]:
    res = client.post("/api/analyze", json={"text": text})
    assert res.status_code == 200
    return res.json()["extraction"]


def test_c1_flag_on(setup: Any) -> None:
    setup(llm_reply(C1, "2026년 3월 1일부터", "이용을 연기한 적은 없어요"), FLAG)
    ext = post(C1)
    f = ext["fields"]
    assert f["start_date"] == "2026-03-01"
    assert f["end_date"] == "2026-08-31"
    assert f["notice_date"] == "2026-02-20"
    assert f["had_postponement"] is False
    assert ext["year_inferred"] == {"end_date": 2026, "notice_date": 2026}
    assert ext["evidence"]["end_date"] == "8월 31일까지"
    assert ext["evidence"]["notice_date"] == "2월 20일에 사정이 생겨서 해지"
    assert "end_date" not in ext["missing"] and "notice_date" not in ext["missing"]


def start_only_reply(
    text: str, start: str, start_ev: str, **dates: tuple[str, str]
) -> str:
    """시작일(과 연도 있는 날짜)만 근거와 함께 내는 가짜 LLM 응답. 연도 없는 날짜는 null."""
    fields = {"start_date": start, **{k: v for k, (v, _) in dates.items()}}
    ev = {"start_date": start_ev, **{k: e for k, (_, e) in dates.items()}}
    for v in ev.values():
        assert v in text
    return json.dumps(raw(fields, ev), ensure_ascii=False)


@pytest.mark.parametrize(
    ("text", "notice"),
    [(FAR_BEFORE_START, "2026-05-01"), (NEAREST_DATE, "2026-03-05")],
)
def test_binding_rules_flag_on(setup: Any, text: str, notice: str) -> None:
    setup(start_only_reply(text, "2026-03-01", "2026년 3월 1일부터"), FLAG)
    ext = post(text)
    assert ext["fields"]["end_date"] == "2026-08-31"
    assert ext["fields"]["notice_date"] == notice
    assert ext["year_inferred"] == {"end_date": 2026, "notice_date": 2026}


@pytest.mark.parametrize(
    ("text", "start", "end", "notice", "notice_ev"),
    [
        (C1, "2026-03-01", "2026-08-31", "2026-02-20", "2월 20일에 사정이 생겨서 해지"),
        (N2, "2026-03-01", "2026-08-31", "2026-05-01", "5월 1일에 그만두"),
        (P1, "2026-01-01", "2026-12-31", "2026-03-31", "3월 31일에 해지"),
        (H1, "2026-03-01", "2026-08-31", "2026-04-01", "4월 1일에 해지"),
    ],
)  # fmt: skip
def test_approved_sentences_flag_on(
    setup: Any, text: str, start: str, end: str, notice: str, notice_ev: str
) -> None:
    start_ev = f"{start[:4]}년 {int(start[5:7])}월 {int(start[8:])}일부터"
    setup(start_only_reply(text, start, start_ev), FLAG)
    ext = post(text)
    assert (ext["fields"]["end_date"], ext["fields"]["notice_date"]) == (end, notice)
    assert ext["evidence"]["notice_date"] == notice_ev


def test_ambiguous_notice_left_empty_flag_on(setup: Any) -> None:
    """해지일 연도 후보가 둘(2026·2027) 남으면 비운다."""
    reply = start_only_reply(
        TWO_CANDIDATES,
        "2026-01-01",
        "2026년 1월 1일부터",
        end_date=("2027-12-31", "2027년 12월 31일까지"),
    )
    setup(reply, FLAG)
    ext = post(TWO_CANDIDATES)
    assert "notice_date" not in ext["fields"]
    assert "notice_date" in ext["missing"]
    assert "year_inferred" not in ext


def test_flag_off_unchanged(setup: Any) -> None:
    """꺼짐: year_inferred 키 없음, 연도 없는 날짜는 되묻기 그대로 (변경 전 check_extraction 결과와 같음)."""
    reply = llm_reply(C1, "2026년 3월 1일부터", "이용을 연기한 적은 없어요")
    setup(reply)
    ext = post(C1)
    assert "year_inferred" not in ext
    assert "end_date" not in ext["fields"] and "notice_date" not in ext["fields"]
    assert {"end_date", "notice_date"} <= set(ext["missing"])
    expected = check_extraction(RawExtraction.model_validate_json(reply), C1)
    assert ext == expected.model_dump(mode="json")


def test_flag_does_not_change_prompt_or_schema(setup: Any) -> None:
    reply = llm_reply(C1, "2026년 3월 1일부터", "이용을 연기한 적은 없어요")
    off = setup(reply)
    post(C1)
    on = setup(reply, FLAG)
    post(C1)
    assert off.calls == on.calls


def test_laundry_unaffected_by_flag(setup: Any) -> None:
    """세탁 추출에는 보완을 하지 않는다 (year_inferred 키 없음)."""
    from llm.laundry_extraction import FIELD_NAMES as LAUNDRY_FIELDS

    text = NO_ANCHOR
    reply = json.dumps(
        {
            "judgment_requested": False,
            "judgment_evidence": None,
            "fields": {n: None for n in LAUNDRY_FIELDS},
            "evidence": {n: None for n in LAUNDRY_FIELDS},
        }
    )
    setup(reply, FLAG)
    res = client.post("/api/analyze?item=laundry", json={"text": text})
    assert res.status_code == 200
    assert "year_inferred" not in res.json()["extraction"]


def test_config_lists_flag(setup: Any) -> None:
    setup("{}", FLAG)
    assert client.get("/api/config").json()["enabled_features"] == [FLAG]
