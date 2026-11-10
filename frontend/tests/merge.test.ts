// 문장 분석 결과를 폼에 합치는 규칙 (헬스장·세탁). Node 내장 테스트 러너로 돈다 (새 의존성 없음).
// 실행: npm test  (node --experimental-strip-types --test)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { INITIAL_FORM, mergeExtraction } from '../src/formState.ts'
import { INITIAL_LAUNDRY_FORM, mergeLaundryExtraction, UNLISTED } from '../src/laundryForm.ts'
import type { AnalyzeResult, LaundryAnalyzeResult, LaundryItemOption } from '../src/types.ts'

const gymExt = (fields: AnalyzeResult['fields']): AnalyzeResult => ({
  fields,
  evidence: {},
  unverified: [],
  missing: [],
  confirm: [],
  judgment_requested: false,
})
const laundryExt = (fields: LaundryAnalyzeResult['fields']): LaundryAnalyzeResult => ({
  fields,
  evidence: {},
  unverified: [],
  missing: [],
  confirm: [],
  judgment_requested: false,
})
const ITEMS: LaundryItemOption[] = [
  {
    key: 'mens_suit',
    label: '외의류 > 신사정장',
    examples: null,
    variant_by: 'use',
    variants: [
      { code: 'summer', text: '하복' },
      { code: 'winter', text: '동복' },
    ],
  },
  { key: 'hanbok', label: '한복류', examples: null, variant_by: null, variants: [] },
]

// ---- 헬스장 ----

test('헬스장: 기본값 "모름"은 문장 값으로 채운다', () => {
  const r = mergeExtraction(INITIAL_FORM, new Set(), gymExt({ has_refund_limit_clause: true }))
  assert.equal(r.form.has_refund_limit_clause, 'yes')
  assert.ok(r.filled.includes('has_refund_limit_clause'))
})

test('헬스장: 사용자가 직접 고른 "모름"은 유지하고 문장 값은 충돌로만 알린다', () => {
  const touched = new Set(['has_refund_limit_clause'])
  const r = mergeExtraction(INITIAL_FORM, touched, gymExt({ has_refund_limit_clause: true }))
  assert.equal(r.form.has_refund_limit_clause, 'unknown')
  assert.equal(r.conflicts.has_refund_limit_clause, 'yes')
  assert.ok(!r.filled.includes('has_refund_limit_clause'))
})

test('헬스장: 직접 비운 빈칸은 빈 값으로 보고 채운다', () => {
  const r = mergeExtraction(INITIAL_FORM, new Set(['paid_amount']), gymExt({ paid_amount: 1200000 }))
  assert.equal(r.form.paid_amount, '1200000')
})

// ---- 세탁 ----

test('세탁: 직접 고른 "세트 아님"과 "모름"은 유지한다', () => {
  const touched = new Set(['set_type', 'special_agreement'])
  const r = mergeLaundryExtraction(
    INITIAL_LAUNDRY_FORM,
    touched,
    laundryExt({ set_type: 'top_bottom', special_agreement: true }),
    ITEMS,
  )
  assert.equal(r.form.set_type, 'none')
  assert.equal(r.form.special_agreement, 'unknown')
  assert.equal(r.conflicts.set_type, 'top_bottom')
  assert.equal(r.conflicts.special_agreement, 'yes')
})

test('세탁: 기본값 "세트 아님"·"모름"은 문장 값으로 채운다', () => {
  const r = mergeLaundryExtraction(
    INITIAL_LAUNDRY_FORM,
    new Set(),
    laundryExt({ set_type: 'top_bottom', set_part: 'whole', special_agreement: true }),
    ITEMS,
  )
  assert.equal(r.form.set_type, 'top_bottom')
  assert.equal(r.form.set_part, 'whole')
  assert.equal(r.form.special_agreement, 'yes')
})

test('세탁: 합친 뒤 Set에 없는 부분(상·하의 중의)과 다른 행의 소재는 비운다', () => {
  const r = mergeLaundryExtraction(
    { ...INITIAL_LAUNDRY_FORM, item_key: 'hanbok' },
    new Set(['item_key']),
    laundryExt({ set_type: 'top_bottom', set_part: 'mid', item_key: 'mens_suit', variant_key: 'winter' }),
    ITEMS,
  )
  assert.equal(r.form.item_key, 'hanbok')
  assert.equal(r.form.variant_key, '')
  assert.equal(r.form.set_part, '')
  assert.ok(!r.filled.includes('set_part'))
})

test('세탁: 표에 없는 품목은 선택지 UNLISTED로 채운다', () => {
  const r = mergeLaundryExtraction(INITIAL_LAUNDRY_FORM, new Set(), laundryExt({ item_unlisted: true }), ITEMS)
  assert.equal(r.form.item_key, UNLISTED)
})
