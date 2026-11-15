// 세탁 R2(세트 의류 일부 손상) 폼 변환 (2026-11-15). Node 내장 테스트 러너로 돈다 (새 의존성 없음).
// 꺼짐: 요청 본문에 R2 항목이 없다 (지금과 같음). 켜짐: 손상 벌·일부 의뢰를 보낸다.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  buildLaundryInput,
  INITIAL_LAUNDRY_FORM,
  laundryVisibility,
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

// 승인 L4 / R2-1 입력 (여성정장 춘추복, 상·하 Set 300,000, 2026-02-22 → 2026-09-10)
const L4: LaundryForm = {
  ...INITIAL_LAUNDRY_FORM,
  service_type: 'laundry_shop',
  damage_type: 'defect',
  proof_available: 'yes',
  item_key: 'womens_suit',
  variant_key: 'spring_fall',
  purchase_price: '300000',
  purchase_date: '2026-02-22',
  request_date: '2026-09-10',
  set_type: 'top_bottom',
}

function input(f: LaundryForm, on: boolean) {
  const built = buildLaundryInput(f, ITEMS, on)
  assert.ok(built.ok)
  return built.input
}

test('꺼짐: R2 항목을 보내지 않고 set_part를 쓴다 (승인 L4 입력)', () => {
  const body = input({ ...L4, set_part: 'top' }, false)
  assert.equal(body.set_part, 'top')
  assert.ok(!('damaged_parts' in body))
  assert.ok(!('set_partial_request' in body))
  assert.ok(!('hanbok_kind' in body))
})

test('켜짐 + 상의만 + 아니오 = L4 재승인 입력', () => {
  const body = input({ ...L4, damaged_parts: ['top'], set_partial_request: 'no' }, true)
  assert.equal(body.set_part, null)
  assert.deepEqual(body.damaged_parts, ['top'])
  assert.equal(body.set_partial_request, false)
  assert.equal(body.hanbok_kind, null)
})

test('켜짐 + 상의만 + 예 = R2-38 입력', () => {
  const body = input({ ...L4, damaged_parts: ['top'], set_partial_request: 'yes' }, true)
  assert.equal(body.set_partial_request, true)
})

test('켜짐 + 모든 벌이면 일부 의뢰 질문을 숨기고 보내지 않는다 (Q15 (c))', () => {
  const f = { ...L4, damaged_parts: ['bottom', 'top'] as LaundryForm['damaged_parts'], set_partial_request: 'yes' as const }
  assert.equal(laundryVisibility(f, ITEMS, true).partialRequest, false)
  const body = input(f, true)
  assert.deepEqual(body.damaged_parts, ['top', 'bottom']) // Set 벌 순서
  assert.equal(body.set_partial_request, null)
})

test('켜짐 + 일부만 고르면 질문을 보인다', () => {
  assert.equal(laundryVisibility({ ...L4, damaged_parts: ['top'] }, ITEMS, true).partialRequest, true)
  assert.equal(laundryVisibility({ ...L4, damaged_parts: [] }, ITEMS, true).partialRequest, false)
})

test('켜짐: 품목 행에 맞는 Set 유형만 고른다 (Q5 (c))', () => {
  assert.deepEqual(laundryVisibility({ ...L4, item_key: 'hanbok' }, ITEMS, true).setTypes, ['none', 'hanbok'])
  assert.deepEqual(laundryVisibility(L4, ITEMS, true).setTypes, ['none', 'top_bottom', 'top_mid_bottom'])
  assert.equal(laundryVisibility({ ...L4, item_key: 'hanbok' }, ITEMS, false).setTypes.length, 4)
})

test('켜짐 + 한복: 한복 구성을 보낸다', () => {
  const f: LaundryForm = {
    ...L4,
    item_key: 'hanbok',
    variant_key: '',
    set_type: 'hanbok',
    hanbok_kind: 'chima_jeogori',
    damaged_parts: ['top'],
    set_partial_request: 'no',
  }
  const body = input(f, true)
  assert.equal(body.hanbok_kind, 'chima_jeogori')
  assert.deepEqual(body.damaged_parts, ['top'])
})

test('켜짐 + 세트 아님: R2 항목은 null', () => {
  const body = input({ ...L4, set_type: 'none' }, true)
  assert.equal(body.damaged_parts, null)
  assert.equal(body.set_partial_request, null)
})

test('켜짐: 문장 분석의 set_type·set_part는 쓰지 않는다', () => {
  const ext: LaundryAnalyzeResult = {
    fields: { set_type: 'top_bottom', set_part: 'top', purchase_price: 300000 },
    evidence: { set_type: '정장 상의', purchase_price: '30만원' },
    unverified: ['set_part'],
    missing: ['set_part', 'request_date'],
    confirm: [],
    judgment_requested: false,
  }
  const out = withoutSetFields(ext)
  assert.deepEqual(out.fields, { purchase_price: 300000 })
  assert.deepEqual(out.evidence, { purchase_price: '30만원' })
  assert.deepEqual(out.missing, ['request_date'])
  assert.deepEqual(out.unverified, [])
})
