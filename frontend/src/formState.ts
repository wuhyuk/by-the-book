// 입력 폼 상태와 GymInput 변환. 화면에 보이지 않는 조건부 항목은 null/기본값으로 보낸다.
// 입력 문자열을 정수로 바꾸는 것 외에 숫자를 만들지 않는다.
import type { GymInput, TriState } from './types'

export type TriChoice = 'yes' | 'no' | 'unknown'

export interface FormState {
  industry: string // 'fitness' | 'yoga_pilates' | 'other'
  termination_cause: GymInput['termination_cause'] | ''
  contract_type: GymInput['contract_type'] | ''
  refund_basis: 'period' | 'session' | 'unknown' | ''
  academy_law_applies: boolean
  is_withdrawal: boolean
  withdrawal_cleared: boolean
  total_contract_amount: string
  paid_amount: string
  start_date: string
  end_date: string
  notice_date: string
  total_sessions: string
  used_sessions: string
  add_on_value: string
  add_on_returned: boolean
  returned_add_on_value: string
  deposit: string
  has_refund_limit_clause: TriChoice
  list_price: string
  contract_penalty: string
  provider_offer: string
  had_postponement: TriChoice
  is_pt_only: TriChoice
}

export const INITIAL_FORM: FormState = {
  industry: 'fitness',
  termination_cause: '',
  contract_type: '',
  refund_basis: '',
  academy_law_applies: false,
  is_withdrawal: false,
  withdrawal_cleared: false,
  total_contract_amount: '',
  paid_amount: '',
  start_date: '',
  end_date: '',
  notice_date: '',
  total_sessions: '',
  used_sessions: '',
  add_on_value: '',
  add_on_returned: false,
  returned_add_on_value: '',
  deposit: '',
  has_refund_limit_clause: 'unknown',
  list_price: '',
  contract_penalty: '',
  provider_offer: '',
  had_postponement: 'unknown',
  is_pt_only: 'unknown',
}

export interface Visibility {
  refundBasis: boolean
  periodFields: boolean
  sessionFields: boolean
  ptQuestion: boolean
  returnedAddOn: boolean
  postponementHint: boolean
}

/** 조건부 항목 표시 여부 (MVP_SPEC 5.1). */
export function visibility(f: FormState): Visibility {
  const yoga = f.industry === 'yoga_pilates'
  // 헬스·피트니스(그 외 업종 포함)는 계약 방식, 요가·필라테스는 합의한 환급 기준
  const basis = yoga ? f.refund_basis : f.contract_type
  const both = basis === 'unknown' || basis === ''
  return {
    refundBasis: yoga,
    periodFields: basis === 'period' || both,
    sessionFields: basis === 'session' || both,
    ptQuestion: f.industry === 'fitness' && f.contract_type === 'session',
    returnedAddOn: f.add_on_returned,
    postponementHint: f.had_postponement === 'yes',
  }
}

// 숫자만, 또는 세 자리마다 쉼표 (예: 1200000, 1,200,000)
const INT = /^(\d+|\d{1,3}(,\d{3})+)$/

/** 쉼표를 지운 뒤 0 이상의 정수 문자열이면 정수, 비었으면 null, 그 외는 'invalid'. */
export function parseWon(raw: string): number | null | 'invalid' {
  const s = raw.trim()
  if (s === '') return null
  if (!INT.test(s)) return 'invalid'
  const n = Number(s.replaceAll(',', ''))
  return Number.isSafeInteger(n) ? n : 'invalid'
}

function tri(c: TriChoice): TriState {
  return c === 'yes' ? true : c === 'no' ? false : null
}

const NUMBER_FIELDS = [
  'total_contract_amount',
  'paid_amount',
  'total_sessions',
  'used_sessions',
  'add_on_value',
  'returned_add_on_value',
  'deposit',
  'list_price',
  'contract_penalty',
  'provider_offer',
] as const

type NumberField = (typeof NUMBER_FIELDS)[number]

export const COUNT_FIELDS: readonly string[] = ['total_sessions', 'used_sessions']

type ChoiceField = 'termination_cause' | 'contract_type'

export type BuildResult =
  | { ok: true; input: GymInput }
  | { ok: false; invalidFields: NumberField[]; missingFields: (NumberField | ChoiceField)[] }

/** 폼 상태 → GymInput. 숫자 형식 오류와 스키마 필수 금액 누락은 보내기 전에 막는다. */
export function buildInput(f: FormState): BuildResult {
  const v = visibility(f)
  const parsed = {} as Record<NumberField, number | null>
  const invalidFields: NumberField[] = []
  for (const name of NUMBER_FIELDS) {
    const p = parseWon(f[name])
    if (p === 'invalid') invalidFields.push(name)
    parsed[name] = p === 'invalid' ? null : p
  }
  // 사용자가 고르지 않은 값을 대신 채워 보내지 않는다 (필수 선택 항목)
  const missingFields: (NumberField | ChoiceField)[] = [
    ...(['termination_cause', 'contract_type'] as const).filter((n) => f[n] === ''),
    ...(['total_contract_amount', 'paid_amount'] as const).filter(
      (n) => parsed[n] === null && !invalidFields.includes(n),
    ),
  ]
  if (invalidFields.length > 0 || missingFields.length > 0 || f.termination_cause === '' || f.contract_type === '') {
    return { ok: false, invalidFields, missingFields }
  }
  const dateOrNull = (s: string) => (s === '' ? null : s)
  return {
    ok: true,
    input: {
      judgment_requested: false, // 폼 입력은 항상 false (MVP_SPEC 8.1 VS2 기본값)
      industry: f.industry,
      academy_law_applies: f.academy_law_applies,
      is_withdrawal: f.is_withdrawal,
      withdrawal_cleared: f.withdrawal_cleared ? true : null,
      termination_cause: f.termination_cause,
      contract_type: f.contract_type,
      refund_basis: v.refundBasis && f.refund_basis !== '' ? f.refund_basis : null,
      total_contract_amount: parsed.total_contract_amount as number,
      paid_amount: parsed.paid_amount as number,
      start_date: dateOrNull(f.start_date),
      end_date: dateOrNull(f.end_date),
      notice_date: dateOrNull(f.notice_date),
      total_sessions: v.sessionFields ? parsed.total_sessions : null,
      used_sessions: v.sessionFields ? parsed.used_sessions : null,
      add_on_value: parsed.add_on_value ?? 0,
      add_on_returned: f.add_on_returned,
      returned_add_on_value: v.returnedAddOn ? parsed.returned_add_on_value : null,
      deposit: parsed.deposit ?? 0,
      has_refund_limit_clause: tri(f.has_refund_limit_clause),
      list_price: parsed.list_price,
      contract_penalty: parsed.contract_penalty,
      provider_offer: parsed.provider_offer,
      had_postponement: tri(f.had_postponement),
      is_pt_only: v.ptQuestion ? tri(f.is_pt_only) : null,
    },
  }
}
