// /api/calculate·/api/analyze 호출. 입력은 POST 본문으로만 보낸다 (URL·localStorage·콘솔에 남기지 않는다).
// 품목은 쿼리 item으로만 고른다 (입력값은 URL에 넣지 않는다).
import type {
  AnalyzeResponse,
  CalculateResponse,
  GymInput,
  Item,
  LaundryCalculateResponse,
  LaundryInput,
  LaundryItemOption,
  ValidationIssue,
} from './types'

export type Outcome<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'invalid'; message: string; issues: ValidationIssue[] }
  | { kind: 'error'; message: string }

export type CalculateOutcome = Outcome<CalculateResponse>
export type LaundryCalculateOutcome = Outcome<LaundryCalculateResponse>

const NETWORK_ERROR = '서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.'
const UNKNOWN_ERROR = '알 수 없는 오류가 발생했습니다. 잠시 뒤 다시 시도해 주세요.'
const ANALYZE_INVALID = '문장을 1자 이상 2,000자 이하로 입력해 주세요.'

async function postCalculate<T>(url: string, input: unknown): Promise<Outcome<T>> {
  let response: Response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
      cache: 'no-store',
    })
  } catch {
    return { kind: 'error', message: NETWORK_ERROR }
  }
  if (response.ok || response.status === 422) {
    try {
      if (response.ok) {
        return { kind: 'ok', data: (await response.json()) as T }
      }
      const body = (await response.json()) as { message: string; detail: ValidationIssue[] }
      return { kind: 'invalid', message: body.message, issues: body.detail }
    } catch {
      return { kind: 'error', message: UNKNOWN_ERROR }
    }
  }
  try {
    const body = (await response.json()) as { message?: string }
    return { kind: 'error', message: body.message ?? UNKNOWN_ERROR }
  } catch {
    return { kind: 'error', message: UNKNOWN_ERROR }
  }
}

export function calculate(input: GymInput): Promise<CalculateOutcome> {
  return postCalculate<CalculateResponse>('/api/calculate', input)
}

export function calculateLaundry(input: LaundryInput): Promise<LaundryCalculateOutcome> {
  return postCalculate<LaundryCalculateResponse>('/api/calculate?item=laundry', input)
}

// 세탁 품목 선택지 (평균 내용연수표 행 이름 그대로). 실패하면 null.
export async function fetchLaundryItems(): Promise<LaundryItemOption[] | null> {
  try {
    const response = await fetch('/api/laundry/items', { cache: 'no-store' })
    return response.ok ? ((await response.json()) as LaundryItemOption[]) : null
  } catch {
    return null
  }
}

export type AnalyzeOutcome =
  | { kind: 'ok'; data: AnalyzeResponse }
  | { kind: 'error'; message: string }

// /api/analyze 호출. 문장은 POST 본문으로만 보낸다 (URL·localStorage·콘솔에 남기지 않는다).
export async function analyze(text: string, item: Item = 'gym'): Promise<AnalyzeOutcome> {
  let response: Response
  try {
    response = await fetch(item === 'gym' ? '/api/analyze' : `/api/analyze?item=${item}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
      cache: 'no-store',
    })
  } catch {
    return { kind: 'error', message: NETWORK_ERROR }
  }
  try {
    if (response.ok) {
      return { kind: 'ok', data: (await response.json()) as AnalyzeResponse }
    }
    if (response.status === 422) return { kind: 'error', message: ANALYZE_INVALID }
    const body = (await response.json()) as { message?: string }
    return { kind: 'error', message: body.message ?? UNKNOWN_ERROR }
  } catch {
    return { kind: 'error', message: UNKNOWN_ERROR }
  }
}
