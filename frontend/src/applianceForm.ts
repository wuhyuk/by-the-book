// 가전 입력 폼 상태와 ApplianceInput 변환 (MVP_SPEC 13절). 입력 문자열을 정수로 바꾸는 것 외에 숫자를 만들지 않는다.
// 기간·내용연수·환급액은 화면이 알지 못한다 (서버 엔진만 계산).
import { parseWon, type TriChoice } from './formState.ts'
import type { ApplianceInput, TriState } from './types.ts'

export const APPLIANCE_UNLISTED = '__unlisted__'

export interface ApplianceForm {
  item_key: string // 지원 품목 키, APPLIANCE_UNLISTED, '' (고르지 않음)
  purchase_price: string
  purchase_date: string
  request_date: string
  manufacture_date: string
  parts_unavailable: TriChoice
  certificate_confirmed: TriChoice
  certificate_warranty_months: string
  certificate_parts_years: string
  provider_offer: string
}

export const INITIAL_APPLIANCE_FORM: ApplianceForm = {
  item_key: '',
  purchase_price: '',
  purchase_date: '',
  request_date: '',
  manufacture_date: '',
  parts_unavailable: 'unknown',
  certificate_confirmed: 'unknown',
  certificate_warranty_months: '',
  certificate_parts_years: '',
  provider_offer: '',
}

const NUMBER_FIELDS = [
  'purchase_price',
  'provider_offer',
  'certificate_warranty_months',
  'certificate_parts_years',
] as const
type NumberField = (typeof NUMBER_FIELDS)[number]

const tri = (c: TriChoice): TriState => (c === 'yes' ? true : c === 'no' ? false : null)
const dateOrNull = (s: string) => (s === '' ? null : s)

export type ApplianceBuildResult =
  | { ok: true; input: ApplianceInput }
  | { ok: false; invalidFields: NumberField[] }

/** 폼 → ApplianceInput. 숫자 형식 오류만 보내기 전에 막는다. 누락·입력 오류·범위는 엔진이 판정한다. */
export function buildApplianceInput(f: ApplianceForm): ApplianceBuildResult {
  const parsed = {} as Record<NumberField, number | null>
  const invalidFields: NumberField[] = []
  for (const name of NUMBER_FIELDS) {
    const p = parseWon(f[name])
    if (p === 'invalid') invalidFields.push(name)
    parsed[name] = p === 'invalid' ? null : p
  }
  if (invalidFields.length > 0) return { ok: false, invalidFields }
  const unlisted = f.item_key === APPLIANCE_UNLISTED
  return {
    ok: true,
    input: {
      judgment_requested: false, // 폼 입력은 항상 false
      item_key: unlisted || f.item_key === '' ? null : f.item_key,
      item_unlisted: unlisted,
      purchase_price: parsed.purchase_price,
      purchase_date: dateOrNull(f.purchase_date),
      request_date: dateOrNull(f.request_date),
      manufacture_date: dateOrNull(f.manufacture_date),
      parts_unavailable: tri(f.parts_unavailable),
      certificate_confirmed: tri(f.certificate_confirmed),
      certificate_warranty_months: parsed.certificate_warranty_months,
      certificate_parts_years: parsed.certificate_parts_years,
      provider_offer: parsed.provider_offer,
    },
  }
}
