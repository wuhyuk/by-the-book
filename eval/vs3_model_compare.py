"""VS3 모델 비교: 같은 가상 문장으로 LLM 추출을 돌려 모델별로 비교한다 (MVP_SPEC 9절 확정 4).

실제 키로 호출하므로 사용자가 직접 실행한다. 키는 환경변수 또는 backend/.env의 LLM_API_KEY에서
llm.config.load_settings가 읽는다 (이 스크립트는 키 값을 출력하지 않는다).

사용 (저장소 루트, Git Bash):
    backend/.venv/Scripts/python eval/vs3_model_compare.py --dry-run      # 키 없이 케이스 점검
    backend/.venv/Scripts/python eval/vs3_model_compare.py                # 기본 목록 (DEFAULT_MODELS)
    backend/.venv/Scripts/python eval/vs3_model_compare.py --models gemini-3.1-flash-lite --interval 6

기본 목록은 gemini-3.1-flash-lite, gemini-3.5-flash-lite다 (2026-11-08 결정). gemini-3.6-flash는 하루 20건
한도라 기본에서 뺐고 --models로 직접 지정할 때만 쓴다 (호출 간격 13초, 한도 경고 출력).
호출 간격은 모델별 무료 한도(MODEL_LIMITS, 사용자가 AI Studio에서 2026-11-08 확인)로 정하고 --interval로 바꾼다.
이 스크립트는 재시도·예비 모델을 쓰지 않는다 (429 발생 수를 그대로 세기 위해).

비교 항목: 필수 필드 추출 정확도(LLM 원출력·근거 확인 후), 전체 필드 정확도(빈 값 포함),
refund_basis의 None/"unknown" 구분, 판단 질문 감지, 응답 시간, 429 발생 수.

출력에는 입력 문장, 추출 값, 응답 본문, 키를 넣지 않는다. 케이스 ID, 필드 이름, 맞음/틀림, 시간만 쓴다.
문장은 모두 가상이다. 기대값은 승인 케이스 입력(backend/tests/test_gym_calc.CASES)에서 가져오고,
문장에 적지 않은 필드는 null(추출하지 않음)이 기대값이다.
"""

import argparse
import importlib
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "backend" / "tests")]

from llm.client import LLMError, LLMErrorKind, Turn
from llm.config import load_settings
from llm.extraction import (
    EXAMPLES_FILE,
    FIELD_NAMES,
    RawExtraction,
    check_extraction,
    few_shot_turns,
    response_schema,
    system_prompt,
)
from llm.gemini import GeminiClient
from llm.guardrail import detect_judgment_request
from llm.masking import mask_pii

CASES = {c.id: c for c in importlib.import_module("test_gym_calc").CASES}

DEFAULT_MODELS = ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite")
# 모델별 무료 한도 (RPM, RPD). 사용자가 AI Studio에서 2026-11-08 확인한 값 (docs/sources/vs3_report.md 4절).
MODEL_LIMITS: dict[str, tuple[int, int]] = {
    "gemini-3.1-flash-lite": (15, 500),
    "gemini-3.5-flash-lite": (15, 500),
    "gemini-3.6-flash": (5, 20),
    "gemini-2.5-flash-lite": (10, 20),
    "gemini-2.5-flash": (5, 20),
    "gemini-3-flash": (5, 20),
    "gemini-3.8-flash": (5, 20),
}
UNKNOWN_LIMIT = (5, 20)  # 표에 없는 모델은 가장 낮은 한도로 본다
LOW_RPD = 20


def safe_interval(model: str) -> float:
    """분당 한도보다 1초 여유를 둔 호출 간격 (RPM 15 → 5초, 10 → 7초, 5 → 13초)."""
    rpm, _ = MODEL_LIMITS.get(model, UNKNOWN_LIMIT)
    return float(60 // rpm + 1)


def limit_warnings(model: str, calls: int, interval: float) -> list[str]:
    """실행 전 경고 (입력·키 없음)."""
    rpm, rpd = MODEL_LIMITS.get(model, UNKNOWN_LIMIT)
    out: list[str] = []
    if model not in MODEL_LIMITS:
        out.append(
            f"{model}: 한도표에 없는 모델이라 RPM {rpm}, RPD {rpd}로 가정합니다."
        )
    if rpd <= LOW_RPD:
        out.append(
            f"{model}: 하루 {rpd}건 한도 모델입니다. 이번 실행 최대 {calls}건 (평가·반복 실험에 쓰지 마세요)."
        )
    if calls > rpd:
        out.append(f"{model}: 호출 수 {calls}건이 하루 한도 {rpd}건을 넘습니다.")
    if interval < safe_interval(model):
        out.append(
            f"{model}: 간격 {interval}초가 권장 {safe_interval(model)}초보다 짧아 429가 날 수 있습니다."
        )
    return out


def fewshot_case_ids() -> set[str]:
    """few-shot 예시가 쓰는 승인 케이스 ID (겹침 구간 집계용)."""
    return {ex["case"] for ex in json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))}


@dataclass(frozen=True)
class CompareCase:
    id: str  # 비교 케이스 ID
    case: str  # 기대값을 가져올 승인 케이스 ID
    text: str  # 가상 문장
    stated: tuple[str, ...]  # 문장에 적은 필드 (기대값 = 승인 케이스 입력 값)
    override: dict[str, Any] = field(
        default_factory=dict
    )  # 승인 케이스와 다르게 적은 값
    judgment: bool = False  # 판단 질문을 넣었는지
    note: str = ""


PERIOD = ("start_date", "end_date", "notice_date")
BASE = ("industry", "contract_type", "termination_cause")
AMT = ("total_contract_amount", "paid_amount")

COMPARE_CASES: tuple[CompareCase, ...] = (
    CompareCase(
        "Q01",
        "P1",
        "헬스장 1년 회원권을 2026년 1월 1일부터 2026년 12월 31일까지로 120만원 일시불 결제했어요. "
        "이사를 가게 돼서 2026년 3월 31일에 해지하겠다고 카톡으로 말했어요. "
        "계약서에 중도 해지 위약금 조항이 있었어요.",
        (*BASE, *AMT, *PERIOD, "has_refund_limit_clause"),
        note="헬스 기간제 기본",
    ),
    CompareCase(
        "Q02",
        "P4",
        "헬스 1년권이 총 1,200,000원인데 할부로 지금까지 600,000원 냈어요. "
        "기간은 2026-01-01~2026-12-31이고, 회사 일이 바빠져서 2026-02-28에 그만두겠다고 했어요. "
        "중간에 연기한 적은 없습니다.",
        (*BASE, *AMT, *PERIOD, "had_postponement"),
        note="분할 납부",
    ),
    CompareCase(
        "Q03",
        "P5",
        "헬스장 10개월권 100만원을 다 냈고 보증금 10만원도 따로 냈어요. 가입할 때 5만원짜리 운동복을 "
        "받았는데 돌려주진 않았어요. 2026.1.1부터 2026.10.31까지이고 2026.4.30에 건강 문제로 해지 요청했어요. "
        "계약서에 위약금 조항 있어요.",
        (
            *BASE,
            *AMT,
            *PERIOD,
            "deposit",
            "add_on_value",
            "has_refund_limit_clause",
        ),
        override={"add_on_returned": False},
        note="부가상품 미반환 + 보증금",
    ),
    CompareCase(
        "Q04",
        "S1",
        "필라테스 20회권 50만원 결제했고 계약할 때 환불은 횟수 기준으로 계산하기로 했어요. "
        "유효기간 2026-03-01~2026-05-31, 5회 듣고 2026-04-15에 개인 사정으로 해지 신청했어요.",
        (*BASE, "refund_basis", *AMT, *PERIOD, "total_sessions", "used_sessions"),
        note="refund_basis=session 명시",
    ),
    CompareCase(
        "Q05",
        "U1",
        "요가 20회 이용권, 원래 50만원인데 40만원에 할인받아 결제했어요. 2026년 3월 1일부터 2026년 6월 28일까지 "
        "쓸 수 있고 4번 갔어요. 2026년 4월 30일에 그만두겠다고 했는데, 환불을 기간으로 할지 횟수로 할지 "
        "계약 때 정했는지 기억이 안 나요. 계약서에 위약금 조항은 있어요.",
        (
            *BASE,
            "refund_basis",
            *AMT,
            *PERIOD,
            "total_sessions",
            "used_sessions",
            "list_price",
            "has_refund_limit_clause",
        ),
        note="refund_basis=unknown (모른다고 말함)",
    ),
    CompareCase(
        "Q06",
        "P3",
        "요가 90일권 90만원 결제했어요. 2026-04-01부터 2026-06-29까지인데 2026-04-30에 개인 사정으로 해지 "
        "요청했어요. 계약서에 위약금 조항 있었어요.",
        (*BASE, *AMT, *PERIOD, "has_refund_limit_clause"),
        override={"refund_basis": None},
        note="refund_basis 언급 없음 → null 기대",
    ),
    CompareCase(
        "Q07",
        "S3",
        "PT만 30회 150만원에 계약하고 전액 결제했어요. 12회 받았는데 이제 시간이 안 돼서 그만두려고요. "
        "업체에서는 60만원 돌려준다고 했어요. 계약서에 위약금 조항 있어요.",
        (
            *BASE,
            *AMT,
            "total_sessions",
            "used_sessions",
            "provider_offer",
            "is_pt_only",
            "has_refund_limit_clause",
        ),
        note="PT 단독, 날짜 없음, 지급액은 '전액 결제'(계약 금액과 같은 구절)",
    ),
    CompareCase(
        "Q08",
        "K1",
        "헬스 12개월 120만원 냈어요(2026-01-01~2026-12-31). 2026-03-31에 단순 변심으로 해지 요청했더니 "
        "계약서상 위약금이 20만원이라고 하네요. 계약서에 위약금 조항이 있긴 해요.",
        (*BASE, *AMT, *PERIOD, "contract_penalty", "has_refund_limit_clause"),
        note="계약서상 위약금",
    ),
    CompareCase(
        "Q09",
        "N2",
        "필라테스 30회권 정상가 90만원짜리를 60만원에 결제했어요. 환불은 횟수로 계산하기로 계약했고 "
        "기간은 2026-03-01부터 2026-08-31까지예요. 10회 듣고 2026-05-01에 이직 때문에 해지 신청했는데 "
        "업체가 20만원만 준대요. 위약금 조항 있어요.",
        (
            *BASE,
            "refund_basis",
            *AMT,
            *PERIOD,
            "total_sessions",
            "used_sessions",
            "list_price",
            "provider_offer",
            "has_refund_limit_clause",
        ),
        note="정상가 + 제시액",
    ),
    CompareCase(
        "Q10",
        "T1",
        "헬스 1년권 120만원 결제, 2026-01-01 시작이고 한 달 연기해서 종료일이 2027-01-31로 바뀌었어요. "
        "2026-03-31에 이사 때문에 해지한다고 했어요. 위약금 조항 있어요.",
        (*BASE, *AMT, *PERIOD, "had_postponement", "has_refund_limit_clause"),
        note="연기 + 연장된 종료일",
    ),
    CompareCase(
        "Q11",
        "M1",
        "필라테스 기간권 60만원 결제했어요. 환불은 기간 기준으로 정했어요. 2026-03-01에 시작했고 "
        "2026-04-01에 개인 사정으로 해지 요청했어요. 종료일은 기억이 안 나요. 위약금 조항은 있어요.",
        (
            *BASE,
            "refund_basis",
            *AMT,
            "start_date",
            "notice_date",
            "has_refund_limit_clause",
        ),
        note="종료일 없음 → end_date null 기대",
    ),
    CompareCase(
        "Q12",
        "C1",
        "헬스 6개월권을 정상가 그대로 60만원에 결제했어요. 이용 기간은 2026-03-01~2026-08-31인데 "
        "시작 전인 2026-02-20에 개인 사정으로 해지하겠다고 했어요. 계약서 받은 지 한 달이 넘어 청약철회 "
        "기간은 지났어요. 위약금 조항 있어요.",
        (
            *BASE,
            *AMT,
            *PERIOD,
            "list_price",
            "withdrawal_cleared",
            "has_refund_limit_clause",
        ),
        note="청약철회 기간 지남",
    ),
    CompareCase(
        "Q13",
        "P1",
        "제 이름은 홍길동이고 연락처는 010-1234-5678이에요. 헬스장 1년권 120만원을 2026-01-01~2026-12-31로 "
        "결제했는데 이사 때문에 2026-03-31에 해지 요청했어요. 환불은 계좌 110-123-456789로 받고 싶어요.",
        (*BASE, *AMT, *PERIOD),
        note="가상 개인정보 포함 (마스킹 후 추출)",
    ),
    CompareCase(
        "Q14",
        "S1",
        "필라테스 20회권을 50만원에 끊었어요. 3월 1일부터 다녔고 5회 갔는데 개인 사정으로 그만두려고요.",
        (*BASE, *AMT, "total_sessions", "used_sessions"),
        override={"refund_basis": None},
        note="연도 없는 날짜 → start_date null 기대, refund_basis null 기대",
    ),
    CompareCase(
        "Q15",
        "P1",
        "헬스장 1년권 120만원 결제하고 2026-01-01부터 다녔어요. 2026-03-31에 해지하려니 업체가 위약금을 "
        "다 내라는데, 업체 주장이 맞는 건지 판정해 주세요.",
        ("industry", "contract_type", *AMT, "start_date", "notice_date"),
        judgment=True,
        note="규칙 가드레일에 걸리지 않는 판단 요청 (LLM 감지 확인)",
    ),
)

REQUIRED_ALWAYS = ("industry", "contract_type", "termination_cause", *AMT)


def expected_fields(cc: CompareCase) -> dict[str, Any]:
    """필드별 기대값. 적은 필드는 승인 케이스 입력 값, 나머지는 None."""
    inp = CASES[cc.case].inp
    out: dict[str, Any] = {}
    for name in FIELD_NAMES:
        value = getattr(inp, name) if name in cc.stated else None
        if name in cc.override:
            value = cc.override[name]
        out[name] = value.isoformat() if isinstance(value, date) else value
    return out


def required_fields(exp: dict[str, Any]) -> list[str]:
    """정확도를 볼 필수 필드 (MVP_SPEC 5.1 필수 열, 기대값 기준)."""
    names = list(REQUIRED_ALWAYS)
    if exp["industry"] == "yoga_pilates":
        names.append("refund_basis")
        basis = exp["refund_basis"]
    else:
        basis = exp["contract_type"]
    if basis in (None, "unknown", "period"):
        names += list(PERIOD)
    if basis in (None, "unknown", "session"):
        names += ["total_sessions", "used_sessions"]
    return names


def run_one(client: GeminiClient, cc: CompareCase) -> dict[str, Any]:
    masked = mask_pii(cc.text)
    exp = expected_fields(cc)
    row: dict[str, Any] = {
        "id": cc.id,
        "case": cc.case,
        "note": cc.note,
        "yoga": exp["industry"] == "yoga_pilates",
        "fewshot_overlap": cc.case in fewshot_case_ids(),
    }
    if detect_judgment_request(masked):
        row.update(status="rule_guardrail", judgment_ok=cc.judgment)
        return row
    turns = [*few_shot_turns(), Turn(role="user", text=masked)]
    started = time.perf_counter()
    try:
        out = client.generate_json(
            system=system_prompt(), turns=turns, response_schema=response_schema()
        )
        raw = RawExtraction.model_validate_json(out)
    except LLMError as exc:
        row.update(status=exc.kind.value, http=exc.status)
        row["seconds"] = round(time.perf_counter() - started, 2)
        return row
    except ValueError:
        row.update(status=LLMErrorKind.BAD_RESPONSE.value)
        row["seconds"] = round(time.perf_counter() - started, 2)
        return row
    row["seconds"] = round(time.perf_counter() - started, 2)
    checked = check_extraction(raw, masked)
    raw_values = {
        k: (v.isoformat() if isinstance(v, date) else v)
        for k, v in raw.fields.model_dump().items()
    }
    verified = {n: checked.fields.get(n) for n in FIELD_NAMES}
    req = required_fields(exp)
    row.update(
        status="ok",
        required_raw=[n for n in req if raw_values[n] == exp[n]],
        required_verified=[n for n in req if verified[n] == exp[n]],
        required_total=len(req),
        all_raw_wrong=[n for n in FIELD_NAMES if raw_values[n] != exp[n]],
        all_verified_wrong=[n for n in FIELD_NAMES if verified[n] != exp[n]],
        unverified=checked.unverified,
        refund_basis_expected=repr(exp["refund_basis"]),
        refund_basis_ok_raw=raw_values["refund_basis"] == exp["refund_basis"],
        refund_basis_ok_verified=verified["refund_basis"] == exp["refund_basis"],
        judgment_ok=checked.judgment_requested == cc.judgment,
    )
    return row


def summarize(model: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r["status"] == "ok"]
    secs = [r["seconds"] for r in ok]
    req_total = sum(r["required_total"] for r in ok)
    yoga_rb = [r for r in ok if r["yoga"]]
    return {
        "model": model,
        "calls": len(rows),
        "ok": len(ok),
        "rate_limited_429": sum(
            r["status"] == LLMErrorKind.RATE_LIMITED.value for r in rows
        ),
        "other_errors": sorted(
            {r["status"] for r in rows if r["status"] not in ("ok", "rule_guardrail")}
            - {LLMErrorKind.RATE_LIMITED.value}
        ),
        "required_accuracy_raw": f"{sum(len(r['required_raw']) for r in ok)}/{req_total}",
        "required_accuracy_verified": f"{sum(len(r['required_verified']) for r in ok)}/{req_total}",
        "all_fields_wrong_raw": sum(len(r["all_raw_wrong"]) for r in ok),
        "all_fields_wrong_verified": sum(len(r["all_verified_wrong"]) for r in ok),
        "refund_basis_ok_raw": f"{sum(r['refund_basis_ok_raw'] for r in yoga_rb)}/{len(yoga_rb)}",
        "judgment_ok": f"{sum(bool(r.get('judgment_ok')) for r in rows if r['status'] in ('ok', 'rule_guardrail'))}/"
        f"{sum(r['status'] in ('ok', 'rule_guardrail') for r in rows)}",
        "seconds_median": round(statistics.median(secs), 2) if secs else None,
        "seconds_max": max(secs) if secs else None,
        # few-shot과 같은 승인 케이스인지로 나눈 필수 필드 정확도 (근거 확인 후)
        "required_verified_fewshot_overlap": _ratio(
            [r for r in ok if r["fewshot_overlap"]]
        ),
        "required_verified_no_overlap": _ratio(
            [r for r in ok if not r["fewshot_overlap"]]
        ),
    }


def _ratio(rows: list[dict[str, Any]]) -> str:
    return f"{sum(len(r['required_verified']) for r in rows)}/{sum(r['required_total'] for r in rows)}"


def print_rows(model: str, rows: list[dict[str, Any]]) -> None:
    print(f"\n## {model}")
    for r in rows:
        if r["status"] != "ok":
            extra = f" http={r.get('http')}" if r.get("http") else ""
            print(
                f"- {r['id']} ({r['case']}): {r['status']}{extra} {r.get('seconds', '')}"
            )
            continue
        print(
            f"- {r['id']} ({r['case']}): 필수 {len(r['required_verified'])}/{r['required_total']}"
            f" (원출력 {len(r['required_raw'])}), refund_basis 기대 {r['refund_basis_expected']}"
            f" {'맞음' if r['refund_basis_ok_raw'] else '틀림'}, 판단 {'맞음' if r['judgment_ok'] else '틀림'},"
            f" {r['seconds']}s"
        )
        if r["all_raw_wrong"]:
            print(f"    원출력 불일치 필드: {', '.join(r['all_raw_wrong'])}")
        if r["unverified"]:
            print(f"    근거 확인 실패 필드: {', '.join(r['unverified'])}")


def dry_run() -> None:
    """키 없이 케이스 정의를 점검한다: 기대 숫자·날짜가 문장에 읽히는지, 규칙 가드레일 결과."""
    from llm.extraction import AMOUNT_FIELDS, COUNT_FIELDS, DATE_FIELDS
    from llm.grounding import amounts_in, counts_in, dates_in

    problems = 0
    for cc in COMPARE_CASES:
        masked = mask_pii(cc.text)
        exp = expected_fields(cc)
        bad: list[str] = []
        for n, v in exp.items():
            if v is None:
                continue
            if n in AMOUNT_FIELDS and v not in amounts_in(masked):
                bad.append(n)
            if n in COUNT_FIELDS and v not in counts_in(masked):
                bad.append(n)
            if n in DATE_FIELDS and date.fromisoformat(v) not in dates_in(masked):
                bad.append(n)
        rule = detect_judgment_request(masked)
        if rule:
            bad.append("rule_guardrail")
        problems += len(bad)
        print(f"- {cc.id}: {'OK' if not bad else '문제: ' + ', '.join(bad)}")
    print(f"문제 {problems}건")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--models", nargs="+", help=f"비교할 모델 (기본: {' '.join(DEFAULT_MODELS)})"
    )
    parser.add_argument(
        "--interval",
        type=float,
        help="호출 사이 대기 초 (기본: 모델별 한도로 계산, flash-lite 5초·하루 20건 모델 13초)",
    )
    parser.add_argument("--cases", nargs="+", help="일부 케이스만 (예: Q05 Q06)")
    parser.add_argument(
        "--out", type=Path, help="요약 JSON 저장 경로 (입력 문장·값 없음)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="API를 부르지 않고 케이스 정의만 점검"
    )
    args = parser.parse_args()
    if args.dry_run:
        dry_run()
        return

    settings = load_settings()
    models = args.models or list(DEFAULT_MODELS)
    cases = [c for c in COMPARE_CASES if not args.cases or c.id in args.cases]
    report: dict[str, Any] = {"cases": len(cases), "models": {}}
    for model in models:
        interval = args.interval if args.interval is not None else safe_interval(model)
        for warning in limit_warnings(model, len(cases), interval):
            print(f"[한도 경고] {warning}")
        print(f"{model}: 호출 간격 {interval}초, 최대 {len(cases)}건")
        # 간격은 이 스크립트가 지키므로 클라이언트 간격 제한은 끈다. temperature는 설정을 따른다.
        client = GeminiClient(
            api_key=settings.api_key,
            model=model,
            temperature=settings.temperature,
            limiter=None,
        )
        rows: list[dict[str, Any]] = []
        for i, cc in enumerate(cases):
            if i:
                time.sleep(interval)
            rows.append(run_one(client, cc))
        print_rows(model, rows)
        summary = summarize(model, rows)
        report["models"][model] = {"summary": summary, "rows": rows}
    print("\n## 요약")
    for model in models:
        print(json.dumps(report["models"][model]["summary"], ensure_ascii=False))
    if args.out:
        args.out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n저장: {args.out}")


if __name__ == "__main__":
    main()
