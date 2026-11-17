// 결과 카드 팝업 (기능 플래그 result_cards)의 카드 나누기. 순수 함수만 둔다.
// 카드 내용은 인라인 결과 카드(ResultCard·LaundryResultCard·ApplianceResultCard)와 같은 응답 값을 골라 담기만 한다.
// 금액·비율을 새로 계산하지 않고, 문구도 응답·texts.ts의 기존 문구를 그대로 쓴다. 입력이 같으면 결과도 같다.
import {
  APPLIANCE_FIELD_LABEL,
  APPLIANCE_TEXT,
  BASIS_LABEL,
  FIELD_LABEL,
  LAUNDRY_FIELD_LABEL,
  LAUNDRY_TEXT,
  REFUND_KIND_LABEL,
  SCENARIO_LABEL,
} from '../texts.ts'
import type {
  ApplianceCalculateResponse,
  Basis,
  CalculateResponse,
  CitationCard,
  LaundryCalculateResponse,
  NextSteps,
  Step,
} from '../types.ts'

export type BadgeTone = 'ok' | 'warn' | 'unknown' | 'review'

/** 상단 고정 영역에 보이는 금액 한 줄. value가 null이면 '계산하지 않음'(정상가 B 미계산 등)을 글자 크기로 보인다 */
export interface HeaderAmount {
  label: string
  value: number | null
}

export interface CardsHeader {
  badge: string
  tone: BadgeTone
  /** amount: 금액 표시 / not_calculated: 계산하지 않음(금액 크기 아님) / unavailable: 판단 불가(❔, 금액 없음) */
  status: 'amount' | 'not_calculated' | 'unavailable'
  amounts: HeaderAmount[]
  /** 금액 아래 작은 글씨 (조회 칸, 결정 민감도 범위) — 인라인 카드와 같은 문구 */
  hints: string[]
  deposit: number | null
  /** 판단 불가일 때 배지 옆 안내 (화면 한 줄, 없으면 상담 창구 메시지) */
  notice: string | null
}

export interface SummaryCard {
  kind: 'summary'
  screenLine: string | null
  otherFlags: string[]
  guide: string | null
  missing: string[]
  offerGap: string | null
  notices: string[]
}
export interface StepsCard {
  kind: 'steps'
  steps: Step[]
}
export interface CitationsCard {
  kind: 'citations'
  citations: CitationCard[]
}
export interface NextCard {
  kind: 'next'
  consult: { message: string; channels: string[] } | null
  nextSteps: NextSteps | null
}
export type ResultCardData = SummaryCard | StepsCard | CitationsCard | NextCard

/** 세 품목 응답을 같은 모양으로 맞춘 것 */
export interface CardSource {
  header: CardsHeader
  summary: Omit<SummaryCard, 'kind'>
  steps: Step[]
  citations: CitationCard[]
  consult: { message: string; channels: string[] } | null
}

export function badgeTone(badge: string): BadgeTone {
  if (badge.startsWith('✅')) return 'ok'
  if (badge.startsWith('⚠️')) return 'warn'
  if (badge.startsWith('❔')) return 'unknown'
  return 'review'
}

function won(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

interface CommonDisplay {
  badge: string
  screen_line: { text: string } | null
  other_flags: { text: string }[]
  notices: { text: string }[]
  citations: CitationCard[]
  consult: { message: string; channels: string[] } | null
  offer_gap_text?: string
}

function common(
  display: CommonDisplay,
  calculated: boolean,
  missing: string[],
  labels: Record<string, string>,
  steps: Step[],
): { source: CardSource; unavailable: boolean } {
  const tone = badgeTone(display.badge)
  const unavailable = tone === 'unknown'
  const screenLine = display.screen_line?.text ?? null
  return {
    unavailable,
    source: {
      header: {
        badge: display.badge,
        tone,
        status: unavailable ? 'unavailable' : calculated ? 'amount' : 'not_calculated',
        amounts: [],
        hints: [],
        deposit: null,
        notice: unavailable ? (screenLine ?? display.consult?.message ?? null) : null,
      },
      summary: {
        // 판단 불가이면 화면 한 줄은 상단에 이미 보이므로 요약 카드에 다시 쓰지 않는다
        screenLine: unavailable ? null : screenLine,
        otherFlags: display.other_flags.map((f) => f.text),
        guide: null,
        missing: calculated ? [] : missing.map((m) => labels[m] ?? m),
        offerGap: display.offer_gap_text ?? null,
        notices: display.notices.map((n) => n.text),
      },
      steps,
      citations: display.citations,
      consult: display.consult,
    },
  }
}

const BASIS_ORDER: Basis[] = ['period', 'session']

export function gymCardSource(data: CalculateResponse): CardSource {
  const { result, display } = data
  const { source, unavailable } = common(display, result.calculated, result.missing, FIELD_LABEL, result.steps)
  source.summary.guide = display.withdrawal_guide
  if (result.calculated && !unavailable) {
    const kind = result.refund_kind ? REFUND_KIND_LABEL[result.refund_kind] : ''
    for (const b of BASIS_ORDER) {
      const r = result.results[b]
      if (!r) continue
      source.header.amounts.push({ label: `${BASIS_LABEL[b]} · ${SCENARIO_LABEL.A} ${kind}`, value: r.A.refund })
      source.header.amounts.push({ label: `${BASIS_LABEL[b]} · ${SCENARIO_LABEL.B} ${kind}`, value: r.B ? r.B.refund : null })
    }
    if (result.deposit_refund > 0) source.header.deposit = result.deposit_refund
  }
  return source
}

function rangeHint(
  min: number | null,
  max: number | null,
  text: (a: string, b: string) => string,
): string | null {
  return min !== null && max !== null && min !== max ? text(won(min), won(max)) : null
}

export function laundryCardSource(data: LaundryCalculateResponse): CardSource {
  const { result, display } = data
  const { source, unavailable } = common(display, result.calculated, result.missing, LAUNDRY_FIELD_LABEL, result.steps)
  if (result.calculated && !unavailable && result.amount !== null) {
    const label =
      result.method === 'fallback'
        ? LAUNDRY_TEXT.fallbackLabel
        : result.set_share_percent !== null && result.set_share_percent < 100
          ? LAUNDRY_TEXT.setRatioLabel(result.set_share_percent)
          : LAUNDRY_TEXT.ratioLabel
    source.header.amounts.push({ label, value: result.amount })
    if (result.method === 'ratio' && result.life_years !== null && result.ratio_percent !== null) {
      const days = result.use_days !== null ? `${LAUNDRY_TEXT.daysText(result.use_days)} · ` : ''
      source.header.hints.push(days + LAUNDRY_TEXT.lookup(result.life_years, result.ratio_percent))
    }
    const range = rangeHint(result.sensitivity_min, result.sensitivity_max, LAUNDRY_TEXT.range)
    if (range) source.header.hints.push(range)
  }
  return source
}

export function applianceCardSource(data: ApplianceCalculateResponse): CardSource {
  const { result, display } = data
  const { source, unavailable } = common(display, result.calculated, result.missing, APPLIANCE_FIELD_LABEL, result.steps)
  if (result.calculated && !unavailable && result.amount !== null) {
    source.header.amounts.push({ label: APPLIANCE_TEXT.amountLabel, value: result.amount })
    if (result.life_months !== null && result.used_months !== null) {
      source.header.hints.push(APPLIANCE_TEXT.lookup(result.life_months, result.used_months))
    }
    const range = rangeHint(result.sensitivity_min, result.sensitivity_max, APPLIANCE_TEXT.range)
    if (range) source.header.hints.push(range)
  }
  return source
}

/** 카드 목록: 1 요약·주의 안내 → 2 계산 과정 → 3 근거 조항 → 4 다음 행동. 내용이 없는 카드는 뺀다 */
export function buildResultCards(source: CardSource, nextSteps: NextSteps | null = null): ResultCardData[] {
  const cards: ResultCardData[] = []
  const s = source.summary
  if (s.screenLine || s.otherFlags.length || s.guide || s.missing.length || s.offerGap || s.notices.length) {
    cards.push({ kind: 'summary', ...s })
  }
  if (source.steps.length > 0) cards.push({ kind: 'steps', steps: source.steps })
  if (source.citations.length > 0) cards.push({ kind: 'citations', citations: source.citations })
  if (source.consult || nextSteps) cards.push({ kind: 'next', consult: source.consult, nextSteps })
  return cards
}
