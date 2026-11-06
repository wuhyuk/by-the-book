// /api/calculate 호출. 입력은 POST 본문으로만 보낸다 (URL·localStorage·콘솔에 남기지 않는다).
import type { CalculateResponse, GymInput, ValidationIssue } from './types'

export type CalculateOutcome =
  | { kind: 'ok'; data: CalculateResponse }
  | { kind: 'invalid'; message: string; issues: ValidationIssue[] }
  | { kind: 'error'; message: string }

const NETWORK_ERROR = '서버에 연결하지 못했습니다. 백엔드가 실행 중인지 확인해 주세요.'
const UNKNOWN_ERROR = '알 수 없는 오류가 발생했습니다. 잠시 뒤 다시 시도해 주세요.'

export async function calculate(input: GymInput): Promise<CalculateOutcome> {
  let response: Response
  try {
    response = await fetch('/api/calculate', {
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
        return { kind: 'ok', data: (await response.json()) as CalculateResponse }
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
