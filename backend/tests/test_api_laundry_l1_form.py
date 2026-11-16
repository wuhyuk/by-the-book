"""승인 케이스 L1을 화면 폼 흐름 그대로 /api/calculate?item=laundry에 보낸다 (2026-11-16 점검).

입력 값은 승인 케이스 L1(docs/sources/vs4_cases_approval.md 3절, tests/test_laundry_cases.py L1)
그대로다. 문장 분석이 채우는 값(few-shot L1 출력과 같은 필드) 외의 항목은 화면 기본값을
frontend/src/laundryForm.ts buildLaundryInput이 보내는 형태로 둔다:
"모름"(unknown) 선택 칸 → null, 세트 "세트 아님" → set_type "none", 보이지 않는 칸 → null.
기대값은 승인 정답 그대로다: ✅ 기준 확인, 280,000원, 범위 280,000~280,000.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.settings import AppSettings, get_app_settings
from main import app
from rules.badge import Badge

client = TestClient(app)

# 문장 분석이 채우는 값 (L1 승인 입력)
L1_FROM_SENTENCE: dict[str, Any] = {
    "service_type": "laundry_shop",
    "damage_type": "defect",
    "item_key": "mens_suit",
    "variant_key": "winter",
    "purchase_price": 400_000,
    "purchase_date": "2025-11-01",
    "request_date": "2026-10-01",
    "proof_available": True,
}
# 화면 기본값이 보내는 나머지 (buildLaundryInput, R2 꺼짐)
FORM_DEFAULTS: dict[str, Any] = {
    "judgment_requested": False,
    "manufacturing_cause_claimed": None,
    "item_unlisted": False,
    "laundry_fee": None,  # 입증 가능이면 세탁요금 칸은 보이지 않아 null
    "set_type": "none",
    "set_part": None,
    "attachment_only": None,
    "special_agreement": None,
    "customer_partial_fault": None,
    "wants_damaged_item": None,
    "no_issue_confirmation": None,
    "uncollected": None,
    "receipt_issued": None,
    "provider_offer": None,
}
# R2(set_partial) 켜짐이면 r2Fields가 더하는 값 (세트 아님이면 모두 null)
R2_DEFAULTS: dict[str, Any] = {
    "set_part": None,
    "hanbok_kind": None,
    "damaged_parts": None,
    "set_partial_request": None,
}


@pytest.fixture
def features() -> Iterator[Any]:
    def _set(*names: str) -> None:
        app.dependency_overrides[get_app_settings] = lambda: AppSettings(
            enabled_features=names
        )

    yield _set
    app.dependency_overrides.pop(get_app_settings, None)


def _check(body: dict[str, Any]) -> None:
    res = client.post("/api/calculate?item=laundry", json=body)
    assert res.status_code == 200
    result = res.json()["result"]
    assert result["badge"] == Badge.CONFIRMED.value
    assert result["calculated"] is True
    assert result["amount"] == 280_000
    assert (result["sensitivity_min"], result["sensitivity_max"]) == (280_000, 280_000)
    assert result["flags"] == []
    assert result["missing"] == []


def test_l1_form_defaults_flags_off(features: Any) -> None:
    features()
    _check({**FORM_DEFAULTS, **L1_FROM_SENTENCE})


def test_l1_form_defaults_set_partial_on(features: Any) -> None:
    features("set_partial")
    _check({**FORM_DEFAULTS, **R2_DEFAULTS, **L1_FROM_SENTENCE})
