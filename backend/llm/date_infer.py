"""연도 없는 날짜 보완 (기능 플래그 date_year_infer, 2026-11-16). 순수 함수, LLM 호출 없음.

헬스장 추출만 쓴다. LLM은 연도 없는 날짜를 null로 둔다 (prompts/gym_extract_system.md). 켜져 있으면 근거 확인을
마친 뒤 이 모듈이 문장에서 연도 없는 "M월 D일"을 코드로 찾아 이용 종료일·해지 의사 도달일만 결정적 규칙으로
보완한다. 연도는 LLM이 만들지 않는다. 기준 연도는 이미 근거가 확인된 이용 시작일의 연도, 없으면 문장에 적힌
연도가 정확히 하나일 때 그 연도다. 보완한 값의 근거는 문장의 원문 구절(월·일 텍스트 포함) 그대로다.

- 이용 종료일: "까지"는 바로 앞 날짜에만 결합한다. "M월 D일까지"가 하나뿐이면 기준 연도로, 시작일보다 앞서면
  다음 해로. "N개월권·N년권"이 있으면 시작일 + N개월 − 1일과 같을 때만 (어긋나거나 시작일이 없으면 비움). 날짜 없이 기간만 있는 종료일은 계산하지 않는다.
- 해지 의사 도달일: 해지 단서는 자기 앞쪽에서 가장 가까운 날짜 하나에만 결합한다 (그 날짜가 연도 없는 "M월 D일"이고
  같은 문장 안, 날짜 끝에서 NOTICE_WINDOW 글자 안일 때). 그런 날짜가 하나뿐일 때 연도 후보
  {기준 연도 − 1, 기준 연도, 기준 연도 + 1} 중 (a) 시작 전 단서가 그 날짜와 같은 절(쉼표·문장 끝으로 나눔) 안,
  날짜 앞뒤 BEFORE_START_WINDOW 글자 안에 있으면 시작일보다 앞서고 시작일 12개월 전 이후,
  (b) 없으면 시작일 이상 종료일 이하인 후보가 하나만 남을 때. 0개·2개 이상이면 비움.
- 이미 근거가 확인된 값은 덮어쓰지 않는다 (fill-only-empty, 호출하는 쪽이 지킨다).
"""

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

from llm.grounding import DATE_PATTERN

_MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_YEAR = re.compile(r"(?<!\d)(\d{4})\s*년")
_UNTIL = re.compile(r"\s*까지")
_FROM = re.compile(r"\s*부터")
_DURATION = re.compile(
    r"(?<![\d,.])(\d{1,2})\s*(개월|년)\s*(?:짜리\s*)?(?:이용권|회원권|수강권|권|계약)"
)
_SENTENCE_END = re.compile(r"[.!?\n]")
_CLAUSE_END = re.compile(r"[.!?\n,]")

NOTICE_CUES: tuple[str, ...] = ("해지", "그만두", "그만 두", "탈퇴")
BEFORE_START_CUES: tuple[str, ...] = (
    "시작도 안",
    "시작 안 한",
    "시작하기 전",
    "시작 전",
    "시작하지 않",
    "시작도 하기 전",
)
# 날짜 끝에서 해지 단서 끝까지의 최대 글자 수 (같은 문장 안, 사이에 다른 날짜가 없을 때)
NOTICE_WINDOW = 20
# 시작 전 단서를 찾는 범위: 해지일 날짜 앞뒤 글자 수 (같은 절 안)
BEFORE_START_WINDOW = 30


@dataclass(frozen=True)
class YearInference:
    """보완한 값 하나. evidence는 입력 문장의 원문 구절 그대로다."""

    field: str
    value: date
    evidence: str
    year: int


@dataclass(frozen=True)
class _MonthDay:
    start: int
    end: int
    month: int
    day: int


def add_months(d: date, months: int) -> date:
    """달 단위로 더한다. 그 달에 같은 날이 없으면 말일로."""
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _yearless(text: str) -> list[_MonthDay]:
    """연도가 있는 날짜 표기 안에 들어 있지 않은 "M월 D일"."""
    full = [m.span() for m in DATE_PATTERN.finditer(text)]
    found: list[_MonthDay] = []
    for m in _MONTH_DAY.finditer(text):
        if any(s <= m.start() < e for s, e in full):
            continue
        found.append(_MonthDay(m.start(), m.end(), int(m.group(1)), int(m.group(2))))
    return found


def _anchor_year(text: str, start: date | None) -> int | None:
    if start is not None:
        return start.year
    years = {int(m.group(1)) for m in DATE_PATTERN.finditer(text)}
    years |= {int(m.group(1)) for m in _YEAR.finditer(text)}
    return years.pop() if len(years) == 1 else None


def _iso(value: object) -> date | None:
    return date.fromisoformat(value) if isinstance(value, str) else None


def _infer_end(
    text: str, anchor: int, start: date | None, yearless: list[_MonthDay]
) -> YearInference | None:
    ends = [(md, _UNTIL.match(text, md.end)) for md in yearless]
    found = [(md, m) for md, m in ends if m is not None]
    if len({(md.month, md.day) for md, _ in found}) != 1:
        return None
    md, until = found[0]
    end = _safe_date(anchor, md.month, md.day)
    if end is not None and start is not None and end < start:
        end = _safe_date(anchor + 1, md.month, md.day)
    if end is None:
        return None
    durations = {
        int(m.group(1)) * (12 if m.group(2) == "년" else 1)
        for m in _DURATION.finditer(text)
    }
    if durations:
        if start is None or len(durations) != 1:
            return None
        if end != add_months(start, durations.pop()) - timedelta(days=1):
            return None
    return YearInference("end_date", end, text[md.start : until.end()], end.year)


def _notice_bindings(
    text: str, yearless: list[_MonthDay]
) -> list[tuple[_MonthDay, str]]:
    """해지 단서마다 앞쪽에서 가장 가까운 날짜 하나에만 결합한다. 결과는 (날짜, 날짜부터 단서까지 원문)."""
    dates: list[tuple[int, _MonthDay | None]] = [
        (m.end(), None) for m in DATE_PATTERN.finditer(text)
    ]
    dates += [(md.end, md) for md in yearless]
    best: dict[int, tuple[_MonthDay, int]] = {}
    for cue in NOTICE_CUES:
        for m in re.finditer(re.escape(cue), text):
            before = [d for d in dates if d[0] <= m.start()]
            if not before:
                continue
            md = max(before, key=lambda d: d[0])[1]
            if md is None:  # 가장 가까운 날짜가 연도 있는 날짜
                continue
            if _UNTIL.match(text, md.end) or _FROM.match(text, md.end):
                continue
            if m.end() - md.end > NOTICE_WINDOW:
                continue
            if _SENTENCE_END.search(text, md.end, m.start()):
                continue
            if md.start not in best or m.end() < best[md.start][1]:
                best[md.start] = (md, m.end())
    return [(md, text[md.start : end]) for md, end in best.values()]


def _before_start_near(text: str, md: _MonthDay) -> bool:
    """시작 전 단서가 날짜와 같은 절 안, 날짜 앞뒤 BEFORE_START_WINDOW 글자 안에 있는지."""
    ends = [m.end() for m in _CLAUSE_END.finditer(text, 0, md.start)]
    lo = max([md.start - BEFORE_START_WINDOW, *ends])
    nxt = _CLAUSE_END.search(text, md.end)
    hi = min(md.end + BEFORE_START_WINDOW, nxt.start() if nxt else len(text))
    span = text[max(lo, 0) : hi]
    return any(c in span for c in BEFORE_START_CUES)


def _infer_notice(
    text: str, start: date, end: date | None, yearless: list[_MonthDay]
) -> YearInference | None:
    found = _notice_bindings(text, yearless)
    if len({(md.month, md.day) for md, _ in found}) != 1:
        return None
    md, ev = found[0]
    before_start = _before_start_near(text, md)
    if not before_start and end is None:
        return None
    candidates: list[date] = []
    for year in (start.year - 1, start.year, start.year + 1):
        d = _safe_date(year, md.month, md.day)
        if d is None:
            continue
        if before_start:
            ok = add_months(start, -12) <= d < start
        else:
            assert end is not None
            ok = start <= d <= end
        if ok and (end is None or d <= end):
            candidates.append(d)
    if len(candidates) != 1:
        return None
    return YearInference("notice_date", candidates[0], ev, candidates[0].year)


def infer_years(text: str, fields: dict[str, object]) -> list[YearInference]:
    """근거가 확인된 fields(값은 ISO 문자열)와 마스킹한 문장으로 비어 있는 종료일·도달일을 보완한다."""
    start = _iso(fields.get("start_date"))
    anchor = _anchor_year(text, start)
    if anchor is None:
        return []
    yearless = _yearless(text)
    if not yearless:
        return []
    out: list[YearInference] = []
    end = _iso(fields.get("end_date"))
    if end is None:
        inferred = _infer_end(text, anchor, start, yearless)
        if inferred is not None:
            out.append(inferred)
            end = inferred.value
    if "notice_date" not in fields and start is not None:
        notice = _infer_notice(text, start, end, yearless)
        if notice is not None:
            out.append(notice)
    return out
