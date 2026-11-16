// 내 기록 표시용 순수 함수 (MVP_SPEC 18절). 저장된 응답 값을 고르고 형식만 바꾼다. 금액을 새로 계산하지 않는다.
import { HISTORY_TEXT } from '../texts.ts'
import { isStorageAvailable, type AddOutcome, type HistoryDomain, type StorageLike } from './storage.ts'

export type HistoryMode = 'off' | 'unavailable' | 'on'

/**
 * 플래그 꺼짐이면 'off'이고 저장소를 건드리지 않는다 (getStorage를 부르지 않음).
 * 켜짐이면 저장소를 시험해 'on' 또는 'unavailable'.
 */
export function historyAccess(
  features: readonly string[],
  getStorage: () => StorageLike | null,
): { mode: HistoryMode; storage: StorageLike | null } {
  if (!features.includes('local_history')) return { mode: 'off', storage: null }
  let storage: StorageLike | null = null
  try {
    storage = getStorage()
  } catch {
    storage = null
  }
  return isStorageAvailable(storage) ? { mode: 'on', storage } : { mode: 'unavailable', storage: null }
}

/** 저장 결과 → 안내 문구 */
export function saveMessage(outcome: AddOutcome): string {
  switch (outcome.kind) {
    case 'saved':
      return outcome.removed > 0 ? HISTORY_TEXT.savedTrimmed(outcome.removed) : HISTORY_TEXT.saved
    case 'duplicate':
      return HISTORY_TEXT.duplicate
    case 'too_large':
      return HISTORY_TEXT.tooLarge
    default:
      return HISTORY_TEXT.failed
  }
}

const pad = (n: number) => String(n).padStart(2, '0')

/** ISO 시각 → 한국시간 "YYYY-MM-DD HH:mm". 읽을 수 없으면 원래 문자열 */
export function formatKst(iso: string): string {
  const t = Date.parse(iso)
  if (Number.isNaN(t)) return iso
  const d = new Date(t + 9 * 60 * 60 * 1000)
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`
}

/** ISO 시각 → 한국시간 날짜 "YYYY-MM-DD" */
export function kstDate(iso: string): string {
  return formatKst(iso).slice(0, 10)
}

export function domainLabel(domain: HistoryDomain): string {
  return HISTORY_TEXT.domain[domain]
}

function obj(v: unknown): Record<string, unknown> | null {
  return typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null
}

const isInt = (v: unknown): v is number => typeof v === 'number' && Number.isInteger(v)

function won(n: number): string {
  return `${n.toLocaleString('ko-KR')}원`
}

/** 저장된 응답의 배지 문자열 (아이콘 + 글자). 없으면 빈 문자열 */
export function savedBadge(result: Record<string, unknown>): string {
  const badge = obj(result.display)?.badge ?? obj(result.result)?.badge
  return typeof badge === 'string' ? badge : ''
}

/** 기준 시행일·원문 확인일 (응답 display.rule_source에 있을 때만) */
export function baseDateText(result: Record<string, unknown>): string | null {
  const src = obj(obj(result.display)?.rule_source)
  if (!src || typeof src.effective_date !== 'string' || typeof src.retrieved_at !== 'string') return null
  return HISTORY_TEXT.baseDate(src.effective_date, src.retrieved_at)
}

/**
 * 기준 금액 요약. 응답에 있는 금액을 그대로 고른다:
 * 헬스장은 기준·시나리오별 환급액, 세탁·가전은 amount(없으면 sensitivity_min~max).
 * 값이 여럿이면 가장 작은 값~가장 큰 값으로 보여 준다.
 */
export function amountSummary(domain: HistoryDomain, result: Record<string, unknown>): string {
  const r = obj(result.result)
  if (!r || r.calculated !== true) return HISTORY_TEXT.notCalculated
  let values: number[] = []
  if (domain === 'gym') {
    const bases = obj(r.results) ?? {}
    for (const basis of ['period', 'session']) {
      const b = obj(bases[basis])
      for (const scenario of ['A', 'B']) {
        const refund = obj(b?.[scenario])?.refund
        if (isInt(refund)) values.push(refund)
      }
    }
  } else if (isInt(r.amount)) {
    values = [r.amount]
  } else if (isInt(r.sensitivity_min) && isInt(r.sensitivity_max)) {
    values = [r.sensitivity_min, r.sensitivity_max]
  }
  if (values.length === 0) return HISTORY_TEXT.notCalculated
  const lo = values.reduce((a, b) => (b < a ? b : a))
  const hi = values.reduce((a, b) => (b > a ? b : a))
  return lo === hi ? won(lo) : `${won(lo)}~${won(hi)}`
}

/** 결과 카드에 그대로 넣을 수 있는 모양인지 (아니면 요약만 보여 준다) */
export function isRenderable(domain: HistoryDomain, result: Record<string, unknown>): boolean {
  const r = obj(result.result)
  const d = obj(result.display)
  if (!r || !d) return false
  const arrays = [r.steps, r.flags, r.missing, d.other_flags, d.notices, d.citations]
  if (!arrays.every(Array.isArray)) return false
  if (typeof d.badge !== 'string' || typeof r.calculated !== 'boolean' || !obj(d.rule_source)) return false
  if (domain === 'gym' && !obj(r.results)) return false
  return true
}
