"""LLM 호출 전 개인정보 마스킹 (CLAUDE.md 절대 규칙 6, MVP_SPEC 9절 확정 3).

가리는 것: 주민등록번호, 카드번호, 전화번호, 계좌번호, 이메일, 이름(단서가 있는 경우).
가리지 않는 것: 금액(1,200,000원, 120만원), 날짜(2026-01-01, 2026년 1월 1일), 횟수(20회) — 계산에 필요하다.

이름은 형태만으로 알 수 없어 단서가 있을 때만 가린다:
- "이름은 홍길동", "성함: 홍길동", "저는 홍길동입니다"
- 흔한 성씨로 시작하는 2~4글자 + "씨"/"님" (트레이너님·회원님 같은 호칭은 제외)
단서 없는 이름은 놓칠 수 있다 (보고서 남은 위험).
"""

import re

TOKENS = {
    "rrn": "[주민등록번호]",
    "card": "[카드번호]",
    "phone": "[전화번호]",
    "account": "[계좌번호]",
    "email": "[이메일]",
    "name": "[이름]",
}

_D = r"(?<![\d-])"  # 앞에 숫자·하이픈이 없음
_E = r"(?![\d-])"  # 뒤에 숫자·하이픈이 없음

_RRN = re.compile(_D + r"\d{6}\s?-\s?[1-8]\d{6}" + _E)
_CARD = re.compile(_D + r"\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{3,4}" + _E)
_PHONE = re.compile(_D + r"0\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}" + _E)
_PHONE_REP = re.compile(_D + r"1[5-9]\d{2}-\d{4}" + _E)  # 대표번호 (1588-0000 등)
_PHONE_INTL = re.compile(r"\+82[-. ]?\d{1,2}[-. ]?\d{3,4}[-. ]?\d{4}" + _E)
# 계좌: 하이픈·공백으로 나뉜 숫자 묶음(숫자 합계 10~16자리) 또는 붙은 숫자 10~16자리.
# 날짜(2026-01-01, 숫자 8자리)는 자릿수가 모자라 걸리지 않는다.
_ACCOUNT_DASHED = re.compile(_D + r"\d{2,6}(?:[- ]\d{2,8}){1,4}" + _E)
_ACCOUNT_PLAIN = re.compile(_D + r"\d{10,16}" + _E)
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_SURNAMES = "김이박최정강조윤장임한오서신권황안송류유전홍고문양손배백허남심노하곽성차주우구민진나지엄채원천방공현함변염여추도소석선설마길연위표명기반왕금옥육인맹제모탁국어은편용예봉경사부가복태목형피두감음빈동온호범좌팽승간상갈단견당화창"
_TITLES = (
    "회원",
    "고객",
    "선생",
    "사장",
    "대표",
    "매니저",
    "실장",
    "원장",
    "강사",
    "직원",
    "상담사",
    "팀장",
    "부장",
    "과장",
    "트레이너",
    "코치",
    "관장",
    "센터장",
    "기사",
    "주인",
    "어머",
    "아버",
    "부모",
    "할머",
    "할아버",
)
# 이름 단서 뒤에 와도 이름이 아닌 흔한 낱말 ("이름이 기억이 안 나요", "저는 회원입니다")
_NOT_NAMES = ("기억", "생각", "확인", "모르", "없", "뭐", "직장", "학생", "회사")
_NAME_CUE = re.compile(
    r"(?P<cue>(?:이름|성함|성명|예금주)\s*(?:은|는|이|:|：)?\s*)(?P<name>[가-힣]{2,4})"
    r"(?=(?:이고|이며|입니다|이에요|예요|이야|이고요|으로|로|이|,|\.|\s|$))"
)
_NAME_SELF = re.compile(
    r"(?P<cue>저는\s*)(?P<name>[가-힣]{2,4})(?=(?:입니다|이에요|예요|이고|이라고|라고))"
)
_NAME_HONORIFIC = re.compile(
    rf"(?<![가-힣])(?P<name>[{_SURNAMES}][가-힣]{{1,3}})(?=\s?(?:씨|님))"
)


def _mask_honorific(m: re.Match[str]) -> str:
    name = m.group("name")
    if any(name.startswith(t) or name.endswith(t) for t in _TITLES):
        return name
    return TOKENS["name"]


def _mask_cue(m: re.Match[str]) -> str:
    name = m.group("name")
    if any(name.startswith(w) for w in (*_TITLES, *_NOT_NAMES)):
        return m.group(0)
    return m.group("cue") + TOKENS["name"]


def mask_pii(text: str) -> str:
    """개인정보로 보이는 부분을 고정 토큰으로 바꾼 문자열을 돌려준다. 원문은 남기지 않는다."""
    s = _RRN.sub(TOKENS["rrn"], text)
    s = _CARD.sub(TOKENS["card"], s)
    s = _EMAIL.sub(TOKENS["email"], s)
    s = _PHONE_INTL.sub(TOKENS["phone"], s)
    s = _PHONE.sub(TOKENS["phone"], s)
    s = _PHONE_REP.sub(TOKENS["phone"], s)

    def _account(m: re.Match[str]) -> str:
        digits = sum(ch.isdigit() for ch in m.group(0))
        return TOKENS["account"] if 10 <= digits <= 16 else m.group(0)

    s = _ACCOUNT_DASHED.sub(_account, s)
    s = _ACCOUNT_PLAIN.sub(TOKENS["account"], s)
    s = _NAME_CUE.sub(_mask_cue, s)
    s = _NAME_SELF.sub(_mask_cue, s)
    s = _NAME_HONORIFIC.sub(_mask_honorific, s)
    return s
