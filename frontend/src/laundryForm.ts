// 세탁 입력 폼 상태와 LaundryInput 변환 (MVP_SPEC 12.1). 화면에 보이지 않는 조건부 항목은 null로 보낸다.
// 입력 문자열을 정수로 바꾸는 것 외에 숫자를 만들지 않는다. 내용연수·배상비율·Set 배분 비율은 화면이 알지 못한다.
// R2(세트 의류 일부 손상, /api/config enabled_features에 set_partial)가 켜져 있을 때만 손상 벌·일부 의뢰 항목을 쓴다.
// 꺼져 있으면 요청 본문은 지금과 같다 (R2 항목을 보내지 않음).
import { parseWon, type TriChoice } from './formState.ts'
import type { LaundryAnalyzeResult, LaundryInput, LaundryItemOption, TriState } from './types.ts'

export const UNLISTED = '__unlisted__'

export interface LaundryForm {
  service_type: string // '' = 고르지 않음
  damage_type: LaundryInput['damage_type'] | ''
  proof_available: TriChoice
  item_key: string // 표 행 ID, UNLISTED(표에 없음), '' (고르지 않음)
  variant_key: string
  purchase_price: string
  purchase_date: string
  request_date: string
  laundry_fee: string
  set_type: LaundryInput['set_type']
  set_part: NonNullable<LaundryInput['set_part']> | ''
  hanbok_kind: NonNullable<LaundryInput['hanbok_kind']> | '' // R2
  damaged_parts: SetPart[] // R2, 체크박스 (Set 벌 순서로 정렬해 보낸다)
  set_partial_request: TriChoice // R2, 일부만 골랐을 때만 묻는다
  receipt_issued: TriChoice
  manufacturing_cause_claimed: TriChoice
  attachment_only: TriChoice
  special_agreement: TriChoice
  customer_partial_fault: TriChoice
  wants_damaged_item: TriChoice
  no_issue_confirmation: TriChoice
  uncollected: TriChoice
  provider_offer: string
}

export const INITIAL_LAUNDRY_FORM: LaundryForm = {
  service_type: '',
  damage_type: '',
  proof_available: 'unknown',
  item_key: '',
  variant_key: '',
  purchase_price: '',
  purchase_date: '',
  request_date: '',
  laundry_fee: '',
  set_type: 'none',
  set_part: '',
  hanbok_kind: '',
  damaged_parts: [],
  set_partial_request: 'unknown',
  receipt_issued: 'unknown',
  manufacturing_cause_claimed: 'unknown',
  attachment_only: 'unknown',
  special_agreement: 'unknown',
  customer_partial_fault: 'unknown',
  wants_damaged_item: 'unknown',
  no_issue_confirmation: 'unknown',
  uncollected: 'unknown',
  provider_offer: '',
}

export const LAUNDRY_TRI_FIELDS = [
  'proof_available',
  'receipt_issued',
  'manufacturing_cause_claimed',
  'attachment_only',
  'special_agreement',
  'customer_partial_fault',
  'wants_damaged_item',
  'no_issue_confirmation',
  'uncollected',
] as const

const MONEY_FIELDS = ['purchase_price', 'laundry_fee', 'provider_offer'] as const
type MoneyField = (typeof MONEY_FIELDS)[number]

export type SetPart = 'top' | 'mid' | 'bottom'

/** Set 유형별 벌 (서버 rules/laundry.py SET_PARTS와 같은 순서). */
export const SET_TYPE_PARTS: Record<LaundryInput['set_type'], readonly SetPart[]> = {
  none: [],
  top_bottom: ['top', 'bottom'],
  top_mid_bottom: ['top', 'mid', 'bottom'],
  hanbok: ['top', 'bottom'],
}

export interface LaundryVisibility {
  ratioFields: boolean // 입증 가능 또는 모름: 품목·구입가격·날짜
  feeField: boolean // 입증 불가 또는 모름: 세탁요금
  variant: LaundryItemOption | null // 소재·용도를 고를 행
  setPart: boolean // R2 꺼짐: 손상 부분 선택
  setTypes: LaundryInput['set_type'][] // 고를 수 있는 Set 유형 (R2 켜짐이면 품목 행에 맞는 것만)
  hanbokKind: boolean // R2: 한복 조합
  damagedParts: readonly SetPart[] // R2: 손상 벌 체크박스
  partialRequest: boolean // R2: 일부만 골랐을 때만 "일부만 맡겼는지"
}

const ALL_SET_TYPES: LaundryInput['set_type'][] = ['none', 'top_bottom', 'top_mid_bottom', 'hanbok']

/** R2: 손상 벌이 그 Set의 일부(전부는 아님)인지. 서버 _partial과 같은 판정. */
export function isPartialSet(f: LaundryForm): boolean {
  const parts = SET_TYPE_PARTS[f.set_type]
  const chosen = parts.filter((p) => f.damaged_parts.includes(p))
  return chosen.length > 0 && chosen.length < parts.length
}

export function laundryVisibility(
  f: LaundryForm,
  items: LaundryItemOption[],
  setPartial = false,
): LaundryVisibility {
  const row = items.find((i) => i.key === f.item_key) ?? null
  const rowTypes = (row?.set_types ?? []).filter((t): t is LaundryInput['set_type'] =>
    (ALL_SET_TYPES as string[]).includes(t),
  )
  const r2Set = setPartial && f.set_type !== 'none'
  return {
    ratioFields: f.proof_available !== 'no',
    feeField: f.proof_available !== 'yes',
    variant: row && row.variants.length > 0 ? row : null,
    setPart: !setPartial && f.set_type !== 'none',
    setTypes: setPartial && rowTypes.length > 0 ? rowTypes : ALL_SET_TYPES,
    hanbokKind: r2Set && f.set_type === 'hanbok',
    damagedParts: r2Set ? SET_TYPE_PARTS[f.set_type] : [],
    partialRequest: r2Set && isPartialSet(f),
  }
}

const tri = (c: TriChoice): TriState => (c === 'yes' ? true : c === 'no' ? false : null)
const dateOrNull = (s: string) => (s === '' ? null : s)

export type LaundryBuildResult =
  | { ok: true; input: LaundryInput }
  | { ok: false; invalidFields: MoneyField[]; missingFields: ('service_type' | 'damage_type')[] }

/** 폼 → LaundryInput. 숫자 형식 오류와 필수 선택 누락은 보내기 전에 막는다. 그 밖의 누락은 엔진이 판정한다. */
export function buildLaundryInput(
  f: LaundryForm,
  items: LaundryItemOption[],
  setPartial = false,
): LaundryBuildResult {
  const v = laundryVisibility(f, items, setPartial)
  const parsed = {} as Record<MoneyField, number | null>
  const invalidFields: MoneyField[] = []
  for (const name of MONEY_FIELDS) {
    const p = parseWon(f[name])
    if (p === 'invalid') invalidFields.push(name)
    parsed[name] = p === 'invalid' ? null : p
  }
  const missingFields = (['service_type', 'damage_type'] as const).filter((n) => f[n] === '')
  if (invalidFields.length > 0 || missingFields.length > 0 || f.damage_type === '') {
    return { ok: false, invalidFields, missingFields }
  }
  const unlisted = f.item_key === UNLISTED
  return {
    ok: true,
    input: {
      judgment_requested: false, // 폼 입력은 항상 false (승패 질문은 문장 분석에서 막는다)
      service_type: f.service_type,
      damage_type: f.damage_type,
      manufacturing_cause_claimed: tri(f.manufacturing_cause_claimed),
      item_key: v.ratioFields && !unlisted && f.item_key !== '' ? f.item_key : null,
      item_unlisted: v.ratioFields && unlisted,
      variant_key: v.ratioFields && v.variant && f.variant_key !== '' ? f.variant_key : null,
      purchase_price: v.ratioFields ? parsed.purchase_price : null,
      purchase_date: v.ratioFields ? dateOrNull(f.purchase_date) : null,
      request_date: v.ratioFields ? dateOrNull(f.request_date) : null,
      proof_available: tri(f.proof_available),
      laundry_fee: v.feeField ? parsed.laundry_fee : null,
      set_type: f.set_type,
      set_part: v.setPart && f.set_part !== '' ? f.set_part : null,
      attachment_only: tri(f.attachment_only),
      special_agreement: tri(f.special_agreement),
      customer_partial_fault: tri(f.customer_partial_fault),
      wants_damaged_item: tri(f.wants_damaged_item),
      no_issue_confirmation: tri(f.no_issue_confirmation),
      uncollected: tri(f.uncollected),
      receipt_issued: tri(f.receipt_issued),
      provider_offer: parsed.provider_offer,
      ...(setPartial ? r2Fields(f, v) : {}),
    },
  }
}

/** R2 켜짐일 때만 붙이는 항목. 손상 벌은 Set 벌 순서로 보낸다. set_part는 쓰지 않는다. */
function r2Fields(f: LaundryForm, v: LaundryVisibility): Partial<LaundryInput> {
  const r2Set = f.set_type !== 'none'
  return {
    set_part: null,
    hanbok_kind: v.hanbokKind && f.hanbok_kind !== '' ? f.hanbok_kind : null,
    damaged_parts: r2Set ? v.damagedParts.filter((p) => f.damaged_parts.includes(p)) : null,
    set_partial_request: v.partialRequest ? tri(f.set_partial_request) : null,
  }
}

/** R2 켜짐: 세트 관련 값은 폼으로만 받는다. 문장 분석 결과의 set_type·set_part는 쓰지 않는다. */
export function withoutSetFields(ext: LaundryAnalyzeResult): LaundryAnalyzeResult {
  const keep = (f: string) => f !== 'set_type' && f !== 'set_part'
  const fields = Object.fromEntries(Object.entries(ext.fields).filter(([k]) => keep(k)))
  const evidence = Object.fromEntries(Object.entries(ext.evidence).filter(([k]) => keep(k)))
  return {
    ...ext,
    fields,
    evidence,
    unverified: ext.unverified.filter(keep),
    missing: ext.missing.filter(keep),
    confirm: ext.confirm.filter(keep),
  }
}

// ---- 문장 분석 결과 → 폼 (헬스장과 같은 결정 B: 사용자가 입력한 값은 덮어쓰지 않는다) ----

type Name = keyof LaundryForm
type Value = LaundryForm[Name]

const ENUMS: Partial<Record<Name, readonly string[]>> = {
  service_type: ['laundry_shop', 'self_laundromat', 'other'],
  damage_type: ['defect', 'loss', 'other'],
  set_type: ['none', 'top_bottom', 'top_mid_bottom', 'hanbok'],
  set_part: ['top', 'mid', 'bottom', 'whole'],
}

/** 분석 결과(근거 확인된 값) → 폼 값. 품목·소재는 선택지에 있는 값만 받는다. */
export function laundryExtractedValues(
  ext: LaundryAnalyzeResult,
  items: LaundryItemOption[],
): Partial<Record<Name, Value>> {
  const v = ext.fields
  const out: Partial<Record<Name, Value>> = {}
  for (const [name, allowed] of Object.entries(ENUMS) as [Name, readonly string[]][]) {
    const value = v[name as keyof typeof v]
    if (typeof value === 'string' && allowed.includes(value)) out[name] = value as Value
  }
  if (v.item_unlisted === true) out.item_key = UNLISTED
  const row = items.find((i) => i.key === v.item_key)
  if (row && v.item_unlisted !== true) {
    out.item_key = row.key
    if (typeof v.variant_key === 'string' && row.variants.some((x) => x.code === v.variant_key)) {
      out.variant_key = v.variant_key
    }
  }
  for (const name of MONEY_FIELDS) {
    const value = v[name]
    if (typeof value === 'number' && Number.isSafeInteger(value) && value >= 0) out[name] = String(value)
  }
  for (const name of ['purchase_date', 'request_date'] as const) {
    const value = v[name]
    if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) out[name] = value
  }
  for (const name of LAUNDRY_TRI_FIELDS) {
    const value = v[name]
    if (typeof value === 'boolean') out[name] = value ? 'yes' : 'no'
  }
  return out
}

/** 사용자 입력으로 볼 값인지. 직접 고른 "모름"·"세트 아님"은 기본값과 같아도 사용자 입력이다. */
export function isUserLaundryValue(name: Name, value: Value, touched: ReadonlySet<string>): boolean {
  if (!touched.has(name)) return false
  if ((LAUNDRY_TRI_FIELDS as readonly string[]).includes(name) || name === 'set_type') return true
  if (name === 'set_partial_request') return true
  return !isEmptyLaundryValue(name, value)
}

/** 추출 항목 이름 → 폼 항목 이름. 표에 없는 품목(item_unlisted)은 item_key 칸(UNLISTED)으로 보인다 */
export function laundryFormKey(field: string): string {
  return field === 'item_unlisted' ? 'item_key' : field
}

/**
 * 문장 분석 뒤 되묻기 목록 (헬스장 followUpFields와 같은 규칙, 이름은 추출 항목 이름 그대로 돌려준다).
 * - 필수 누락(missing): 합친 뒤에도 비어 있으면 묻는다. 직접 고른 "모름"이어도 다시 묻는다 (예: 입증 여부 "모름" → L10).
 * - 확인 안 됨(unverified): 비어 있고, 필수 누락에 없고, 사용자가 직접 고른 값이 아닐 때만 묻는다.
 */
export function laundryFollowUpFields(
  ext: Pick<LaundryAnalyzeResult, 'missing' | 'unverified'>,
  form: LaundryForm,
  touched: ReadonlySet<string>,
): { missing: string[]; unverified: string[] } {
  const key = (f: string): Name | null => {
    const k = laundryFormKey(f)
    return k in form ? (k as Name) : null
  }
  const stillEmpty = (f: string) => {
    const k = key(f)
    return k !== null && isEmptyLaundryValue(k, form[k])
  }
  const missing = ext.missing.filter(stillEmpty)
  const unverified = ext.unverified.filter((f) => {
    const k = key(f)
    return k !== null && stillEmpty(f) && !missing.includes(f) && !isUserLaundryValue(k, form[k], touched)
  })
  return { missing, unverified }
}

export function isEmptyLaundryValue(name: Name, value: Value): boolean {
  if (Array.isArray(value)) return value.length === 0
  if (name === 'set_partial_request') return value === 'unknown'
  if ((LAUNDRY_TRI_FIELDS as readonly string[]).includes(name)) return value === 'unknown'
  if (name === 'set_type') return value === 'none'
  return value === ''
}

export interface LaundryMerge {
  form: LaundryForm
  filled: Name[]
  conflicts: Partial<Record<Name, Value>>
}

export function mergeLaundryExtraction(
  form: LaundryForm,
  touched: ReadonlySet<string>,
  ext: LaundryAnalyzeResult,
  items: LaundryItemOption[],
): LaundryMerge {
  const values = laundryExtractedValues(ext, items)
  const next = { ...form } as Record<Name, Value>
  const filled: Name[] = []
  const conflicts: Partial<Record<Name, Value>> = {}
  for (const name of Object.keys(INITIAL_LAUNDRY_FORM) as Name[]) {
    const userValue = isUserLaundryValue(name, form[name], touched)
    const extracted = values[name]
    if (userValue) {
      if (extracted !== undefined && extracted !== form[name]) conflicts[name] = extracted
      continue
    }
    if (extracted !== undefined) {
      next[name] = extracted
      filled.push(name)
    } else {
      next[name] = INITIAL_LAUNDRY_FORM[name]
    }
  }
  // 합친 뒤 최종 품목·세트 기준으로 다시 확인한다 (사용자가 고른 품목에 다른 행의 소재가 붙거나,
  // 상·하 Set에 '중의'가 들어가 화면에 보이지 않는 값이 전송되지 않게).
  const merged = next as unknown as LaundryForm
  const row = items.find((i) => i.key === merged.item_key)
  const dropped: Name[] = []
  if (merged.variant_key !== '' && !row?.variants.some((x) => x.code === merged.variant_key)) {
    merged.variant_key = ''
    dropped.push('variant_key')
  }
  const parts = SET_PARTS[merged.set_type]
  if (merged.set_part !== '' && !parts.includes(merged.set_part)) {
    merged.set_part = ''
    dropped.push('set_part')
  }
  return { form: merged, filled: filled.filter((n) => !dropped.includes(n)), conflicts }
}

const SET_PARTS: Record<LaundryInput['set_type'], readonly string[]> = {
  none: [],
  top_bottom: ['whole', 'top', 'bottom'],
  top_mid_bottom: ['whole', 'top', 'mid', 'bottom'],
  hanbok: ['whole', 'top', 'bottom'],
}

// ---- R2 켜짐: 문장 분석의 세트 단서 → 폼 (2026-11-16) ----
// 자동 입력은 상·하 Set(top_bottom) + 손상 부분 상의/하의 하나일 때만. 한복·상중하·부분 불명·전부 손상·
// 일부 의뢰 여부는 채우지 않고 "확인이 필요한 항목"에 한 줄을 더한다. 사용자가 이미 고른 세트 칸은 덮어쓰지 않는다.
// 계산 요청은 기존 변환(buildLaundryInput, R2 켜짐이면 set_part: null)을 그대로 쓴다.

const SET_FIELDS = ['set_type', 'set_part'] as const

export interface SetAutofill {
  merge: LaundryMerge
  /** 폼 칸 이름 → 근거 구절 (set_type → set_type, set_part → damaged_parts) */
  evidence: Record<string, string>
  /** 세트 단서가 있는데 자동으로 채우지 않았으면 true → 확인 안내 한 줄 */
  confirm: boolean
}

/** 세트 단서: 근거 확인된 값(세트 아님 제외) 또는 확인 안 됨·누락 목록의 세트 항목. */
function hasSetClue(raw: LaundryAnalyzeResult): boolean {
  const type = raw.fields.set_type
  const part = raw.fields.set_part
  if (typeof type === 'string' && type !== 'none') return true
  if (typeof part === 'string') return true
  return [...raw.unverified, ...raw.missing].some((f) => (SET_FIELDS as readonly string[]).includes(f))
}

export function applySetAutofill(
  merged: LaundryMerge,
  raw: LaundryAnalyzeResult,
  form: LaundryForm,
  touched: ReadonlySet<string>,
  items: LaundryItemOption[],
  setPartial: boolean,
): SetAutofill {
  const none: SetAutofill = { merge: merged, evidence: {}, confirm: false }
  if (!setPartial || !hasSetClue(raw)) return none
  // 사용자가 세트 칸(세트 아님 포함)이나 손상 벌을 직접 고쳤으면 그대로 둔다
  if (isUserLaundryValue('set_type', form.set_type, touched) || touched.has('damaged_parts')) return none
  const type = raw.fields.set_type
  const part = raw.fields.set_part
  // 품목 행이 고를 수 있는 Set 유형에 상·하가 없으면 채우지 않는다 (laundryVisibility와 같은 기준)
  const rowAllows = laundryVisibility(merged.form, items, true).setTypes.includes('top_bottom')
  if (type !== 'top_bottom' || (part !== 'top' && part !== 'bottom') || !rowAllows) {
    return { ...none, confirm: true }
  }
  const nextForm: LaundryForm = {
    ...merged.form,
    set_type: 'top_bottom',
    set_part: '',
    hanbok_kind: '',
    damaged_parts: [part],
    set_partial_request: 'unknown',
  }
  const evidence: Record<string, string> = {}
  if (raw.evidence.set_type) evidence.set_type = raw.evidence.set_type
  if (raw.evidence.set_part) evidence.damaged_parts = raw.evidence.set_part
  return {
    merge: { ...merged, form: nextForm, filled: [...merged.filled, 'set_type', 'damaged_parts'] },
    evidence,
    confirm: false,
  }
}
