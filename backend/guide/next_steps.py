"""다음 행동: 준비 자료 체크리스트와 상담·피해구제 경로 (기능 플래그 next_steps, MVP_SPEC 14.2, 2026-11-16).

순수 함수와 고정 텍스트만 둔다. LLM을 호출하지 않고 금액·기간 숫자를 넣지 않는다.
체크리스트·채널 문구는 [제안] 상태이며 docs/sources/offer_gap_cases.md 2절 목록으로 승인받는다.

- 체크리스트 항목의 basis: "official"은 한국소비자원 「피해구제 접수방법」 증빙서류 안내
  (계약관련 근거자료(계약서, 영수증 등), 사업자에 이의를 제기한 서면·전자문서·게시판 자료 사본(화면 캡처
  또는 프린트))에 해당하는 항목, "general"은 그 안내에 직접 적혀 있지 않은 일반 안내다.
- 채널의 이름·전화번호·URL·이용 방법은 2026-11-16 공식 누리집에서 직접 열어 확인한 것만 쓴다.
  확인하지 못한 값은 None + status "needs_check"로 둔다 (지금은 세 곳 모두 확인됨).
- 표시 규칙: 계산했고(✅·⚠️·🔍) RULE_UNVERIFIED가 아니면 체크리스트와 채널, ❔·계산 안 함·RULE_UNVERIFIED이면 채널만.
"""

from collections.abc import Collection
from typing import Literal

from pydantic import BaseModel, ConfigDict

NEXT_STEPS_FEATURE = "next_steps"
CHECKED_ON = "2026-11-16"

# 한국소비자원 누리집 (2026-11-16 확인)
KCA_RECEIPT_URL = (
    "https://www.kca.go.kr/odr/pg/ma/pgProcssInfo2.do"  # 피해구제 접수방법
)
KCA_PROCESS_URL = (
    "https://www.kca.go.kr/odr/pg/ma/pgProcssInfo.do"  # 피해구제 절차 안내
)
KCA_COUNSEL_URL = "https://www.kca.go.kr/odr/pg/ma/cnsutInfo.do"  # 소비자상담 절차 안내
CCN_URL = "https://www.ccn.go.kr/index.ccn"  # 1372소비자상담센터
KLAC_URL = (
    "https://www.klac.or.kr/legalstruct/consultationGuidance.do"  # 법률상담 알아보기
)

Item = Literal["gym", "laundry", "appliance"]
Basis = Literal["official", "general"]
BASIS_LABELS: dict[Basis, str] = {"official": "공식 안내", "general": "일반 안내"}

TITLE = "다음 행동"
CHECKLIST_TITLE = "상담·협의 전에 준비해 두면 좋은 자료"
CHECKLIST_NOTE = (
    "'공식 안내'는 한국소비자원 피해구제 접수방법의 증빙서류 안내에 해당하는 항목, "
    "'일반 안내'는 이 서비스가 덧붙인 항목입니다."
)
CHANNELS_TITLE = "도움을 받을 수 있는 곳"
# 화면 하단 공통 고지(frontend/src/texts.ts APP_TEXT.disclaimer)와 같은 문장을 쓴다.
NEXT_STEPS_DISCLAIMER = (
    "이 서비스의 결과는 참고용이며 법률 자문이 아닙니다. "
    "고시는 분쟁 해결의 기준이며, 실제 환급·배상 여부와 금액을 확정하지 않습니다."
)


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChecklistItem(_Model):
    text: str
    basis: Basis
    basis_label: str
    source_url: str | None
    checked_on: str | None


class Channel(_Model):
    id: str
    name: str
    phone: str | None
    url: str | None
    how: str | None
    source_urls: list[str]
    checked_on: str | None
    status: Literal["confirmed", "needs_check"]


class NextSteps(_Model):
    title: str
    checklist_title: str
    checklist: list[ChecklistItem]
    checklist_note: str | None
    channels_title: str
    channels: list[Channel]
    disclaimer: str


def _item(text: str, basis: Basis) -> ChecklistItem:
    official = basis == "official"
    return ChecklistItem(
        text=text,
        basis=basis,
        basis_label=BASIS_LABELS[basis],
        source_url=KCA_RECEIPT_URL if official else None,
        checked_on=CHECKED_ON if official else None,
    )


# 품목별 체크리스트 [제안]. 숫자·효력 표현 없음.
CHECKLISTS: dict[Item, tuple[ChecklistItem, ...]] = {
    "gym": (
        _item("계약서·이용약관", "official"),
        _item("결제 내역", "official"),
        _item("해지 의사를 전한 기록(문자·카카오톡 등 캡처)", "general"),
        _item("이용 내역", "general"),
        _item("업체가 안내한 환급액 근거", "general"),
    ),
    "laundry": (
        _item("세탁물 사진(손상 부위)", "general"),
        _item("세탁 접수증·세탁 택", "official"),
        _item("구입 영수증 또는 구입가·구입일을 알 수 있는 자료", "general"),
        _item("업체와 나눈 대화 기록", "official"),
    ),
    "appliance": (
        _item("구입 영수증", "official"),
        _item("보증서", "general"),
        _item("수리 접수·수리 내역서", "general"),
        _item("부품이 없다는 업체 안내 기록", "general"),
        _item("제조일을 알 수 있는 제품 라벨 사진", "general"),
    ),
}

# 상담·피해구제 경로 [제안]. 2026-11-16 공식 누리집에서 확인한 내용만.
CHANNELS: tuple[Channel, ...] = (
    Channel(
        id="ccn_1372",
        name="1372 소비자상담센터",
        phone="1372",
        url=CCN_URL,
        how="국번 없이 1372로 전화하거나 누리집에서 인터넷 상담을 신청할 수 있습니다.",
        source_urls=[KCA_COUNSEL_URL, CCN_URL],
        checked_on=CHECKED_ON,
        status="confirmed",
    ),
    Channel(
        id="kca_relief",
        name="한국소비자원 소비자 피해구제",
        phone=None,
        url=KCA_RECEIPT_URL,
        how=(
            "피해구제 신청 전에 먼저 소비자상담을 받도록 안내되어 있습니다. "
            "상담으로 해결되지 않으면 방문·우편·인터넷으로 신청서와 증빙서류를 내어 신청할 수 있고, "
            "온라인 신청은 소비자상담에서 피해구제 절차를 안내받은 뒤 6개월 안에 할 수 있습니다."
        ),
        source_urls=[KCA_PROCESS_URL, KCA_RECEIPT_URL],
        checked_on=CHECKED_ON,
        status="confirmed",
    ),
    Channel(
        id="klac_132",
        name="대한법률구조공단",
        phone="132",
        url=KLAC_URL,
        how=(
            "승패·고소 같은 법률 판단이 필요한 질문은 법률상담에서 다룹니다. "
            "국번 없이 132로 전화하거나 누리집에서 사이버 상담 등을 신청할 수 있습니다."
        ),
        source_urls=[KLAC_URL],
        checked_on=CHECKED_ON,
        status="confirmed",
    ),
)


def build_next_steps(item: Item, *, with_checklist: bool) -> NextSteps:
    """품목별 다음 행동. with_checklist가 False면 채널만 (❔·계산 안 함·RULE_UNVERIFIED)."""
    return NextSteps(
        title=TITLE,
        checklist_title=CHECKLIST_TITLE,
        checklist=list(CHECKLISTS[item]) if with_checklist else [],
        checklist_note=CHECKLIST_NOTE if with_checklist else None,
        channels_title=CHANNELS_TITLE,
        channels=list(CHANNELS),
        disclaimer=NEXT_STEPS_DISCLAIMER,
    )


def checklist_allowed(*, calculated: bool, flags: Collection[str]) -> bool:
    """계산했고 RULE_UNVERIFIED가 없을 때만 체크리스트를 보인다 (❔는 계산하지 않으므로 여기서 빠진다)."""
    return calculated and not any(str(f) == "RULE_UNVERIFIED" for f in flags)
