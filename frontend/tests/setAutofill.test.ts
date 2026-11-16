// 세탁 R2 켜짐: 문장 분석의 세트 단서 → 폼 자동 입력·확인 안내 (2026-11-16). Node 내장 테스트 러너 (새 의존성 없음).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  applySetAutofill,
  buildLaundryInput,
  INITIAL_LAUNDRY_FORM,
  mergeLaundryExtraction,
  withoutSetFields,
  type LaundryForm,
} from '../src/laundryForm.ts'
import type { LaundryAnalyzeResult, LaundryItemOption } from '../src/types.ts'

const ITEMS: LaundryItemOption[] = [
  {
    key: 'womens_suit',
    label: '외의류 > 여성정장',
    examples: null,
    variant_by: 'use',
    variants: [{ code: 'spring_fall', text: '춘추복' }],
    set_types: ['none', 'top_bottom', 'top_mid_bottom'],
  },
  { key: 'hanbok', label: '한복류', examples: null, variant_by: null, variants: [], set_types: ['none', 'hanbok'] },
]

// "정장 상의만 손상됐는데 바지는 멀쩡해요. 세트 배상 비율이 어떻게 되나요"의 서버 응답 모양
function ext(fields: LaundryAnalyzeResult['fields'], evidence: LaundryAnalyzeResult['evidence'] = {}, extra: Partial<LaundryAnalyzeResult> = {}): LaundryAnalyzeResult {
  return { fields, evidence, unverified: [], missing: [], confirm: [], judgment_requested: false, ...extra }
}

const SUIT_TOP = ext(
  { set_type: 'top_bottom', set_part: 'top', damage_type: 'defect' },
  { set_type: '정장 상의만', set_part: '상의만 손상됐는데', damage_type: '손상됐는데' },
)

function run(raw: LaundryAnalyzeResult, opts: { form?: LaundryForm; touched?: string[]; on?: boolean } = {}) {
  const form = opts.form ?? INITIAL_LAUNDRY_FORM
  const touched = new Set(opts.touched ?? [])
  const on = opts.on ?? true
  const stripped = on ? withoutSetFields(raw) : raw
  const base = mergeLaundryExtraction(form, touched, stripped, ITEMS)
  return { base, out: applySetAutofill(base, raw, form, touched, ITEMS, on) }
}

test('(a) 상·하 Set + 상의 → 세트 칸과 손상 벌 자동 입력, 근거 표시, 찾은 항목에 포함', () => {
  const { out } = run(SUIT_TOP)
  assert.equal(out.merge.form.set_type, 'top_bottom')
  assert.deepEqual(out.merge.form.damaged_parts, ['top'])
  assert.equal(out.merge.form.set_part, '')
  assert.ok(out.merge.filled.includes('set_type') && out.merge.filled.includes('damaged_parts'))
  assert.ok(out.merge.filled.includes('damage_type'))
  assert.deepEqual(out.evidence, { set_type: '정장 상의만', damaged_parts: '상의만 손상됐는데' })
  assert.equal(out.confirm, false)
})

test('(b) 상·하 Set + 하의 → 자동 입력', () => {
  const { out } = run(ext({ set_type: 'top_bottom', set_part: 'bottom' }))
  assert.equal(out.merge.form.set_type, 'top_bottom')
  assert.deepEqual(out.merge.form.damaged_parts, ['bottom'])
  assert.deepEqual(out.evidence, {}) // 서버가 근거를 주지 않으면 근거 없이 채운다
  assert.equal(out.confirm, false)
})

for (const [name, fields] of [
  ['한복', { set_type: 'hanbok', set_part: 'top' }],
  ['상·중·하 3벌', { set_type: 'top_mid_bottom', set_part: 'mid' }],
  ['부위 불명', { set_type: 'top_bottom' }],
  ['전부 손상', { set_type: 'top_bottom', set_part: 'whole' }],
  ['세트 유형 없이 부위만', { set_part: 'top' }],
] as [string, LaundryAnalyzeResult['fields']][]) {
  test(`(c) ${name} → 자동 입력 없음 + 확인 안내`, () => {
    const { base, out } = run(ext(fields))
    assert.equal(out.merge, base)
    assert.equal(out.merge.form.set_type, 'none')
    assert.deepEqual(out.merge.form.damaged_parts, [])
    assert.ok(!out.merge.filled.includes('set_type'))
    assert.equal(out.confirm, true)
  })
}

test('(c) 확인 안 됨 목록에만 세트 항목이 있어도 확인 안내', () => {
  const { out } = run(ext({}, {}, { unverified: ['set_type'] }))
  assert.equal(out.confirm, true)
})

test('(c) 고른 품목 행이 상·하 Set을 허용하지 않으면 채우지 않고 확인 안내', () => {
  const form = { ...INITIAL_LAUNDRY_FORM, item_key: 'hanbok' }
  const { out } = run(SUIT_TOP, { form, touched: ['item_key'] })
  assert.equal(out.merge.form.set_type, 'none')
  assert.equal(out.confirm, true)
})

test('(d) 사용자가 세트 칸을 이미 바꿨으면 덮어쓰지 않는다 (세트 아님을 직접 골라도)', () => {
  for (const set_type of ['none', 'top_mid_bottom'] as const) {
    const form = { ...INITIAL_LAUNDRY_FORM, set_type }
    const { out } = run(SUIT_TOP, { form, touched: ['set_type'] })
    assert.equal(out.merge.form.set_type, set_type)
    assert.ok(!out.merge.filled.includes('set_type'))
    assert.equal(out.confirm, false)
  }
  const form = { ...INITIAL_LAUNDRY_FORM, set_type: 'top_bottom' as const, damaged_parts: ['bottom' as const] }
  const { out } = run(SUIT_TOP, { form, touched: ['set_type', 'damaged_parts'] })
  assert.deepEqual(out.merge.form.damaged_parts, ['bottom'])
})

test('(d) 기본값 "세트 아님"을 사용자가 바꾸지 않았으면 빈칸으로 보고 채운다', () => {
  const { out } = run(SUIT_TOP, { touched: ['service_type'] })
  assert.equal(out.merge.form.set_type, 'top_bottom')
})

test('(e) 세트 단서 없음 → 변화 없음', () => {
  for (const fields of [{ damage_type: 'loss' }, { set_type: 'none' }] as LaundryAnalyzeResult['fields'][]) {
    const { base, out } = run(ext(fields))
    assert.equal(out.merge, base)
    assert.deepEqual(out.evidence, {})
    assert.equal(out.confirm, false)
  }
})

test('(f) 플래그 꺼짐 → 변화 없음 (기존 병합 결과 그대로)', () => {
  const { base, out } = run(SUIT_TOP, { on: false })
  assert.equal(out.merge, base)
  assert.equal(out.confirm, false)
  assert.deepEqual(out.evidence, {})
  // 꺼짐에서는 기존처럼 일반 채우기가 set_type·set_part를 채운다 (변경 전과 같음)
  assert.equal(base.form.set_type, 'top_bottom')
  assert.equal(base.form.set_part, 'top')
})

test('(g) 자동 입력에 성공하면 확인 안내를 더하지 않는다', () => {
  const { out } = run(ext({ set_type: 'top_bottom', set_part: 'top' }, {}, { missing: ['set_part'] }))
  assert.equal(out.merge.form.set_type, 'top_bottom')
  assert.equal(out.confirm, false)
})

test('계산 요청: 자동 입력 뒤에도 기존 R2 변환 그대로 (set_part는 null, 손상 벌만)', () => {
  const { out } = run(SUIT_TOP)
  const form: LaundryForm = {
    ...out.merge.form,
    service_type: 'laundry_shop',
    proof_available: 'no',
    laundry_fee: '20000',
  }
  const built = buildLaundryInput(form, ITEMS, true)
  assert.ok(built.ok)
  if (!built.ok) return
  assert.equal(built.input.set_type, 'top_bottom')
  assert.equal(built.input.set_part, null)
  assert.deepEqual(built.input.damaged_parts, ['top'])
  assert.equal(built.input.hanbok_kind, null)
  assert.equal(built.input.set_partial_request, null) // 일부 의뢰 여부는 채우지 않는다 (모름 → null)
})
