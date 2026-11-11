// 문장 분석 뒤 되묻기 목록 규칙 (헬스장 followUpFields, 세탁 laundryFollowUpFields).
// 필수 누락은 직접 고른 "모름"이어도 다시 묻고, '확인 안 됨'은 직접 고른 값이면 묻지 않는다.
// 실행: npm test  (Node 내장 테스트 러너, 새 의존성 없음)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { followUpFields, INITIAL_FORM } from '../src/formState.ts'
import { INITIAL_LAUNDRY_FORM, laundryFollowUpFields, UNLISTED } from '../src/laundryForm.ts'

const none = new Set<string>()

// ---- 헬스장 ----

test('헬스장: 필수 누락은 빈칸이면 묻고, 합친 뒤 채워졌으면 묻지 않는다', () => {
  const form = { ...INITIAL_FORM, total_contract_amount: '1200000' }
  const r = followUpFields({ missing: ['paid_amount', 'total_contract_amount'], unverified: [] }, form, none)
  assert.deepEqual(r.missing, ['paid_amount'])
})

test('헬스장: 필수 누락은 직접 고른 "모름"이어도 다시 묻는다', () => {
  const touched = new Set(['has_refund_limit_clause'])
  const r = followUpFields({ missing: ['has_refund_limit_clause'], unverified: [] }, INITIAL_FORM, touched)
  assert.deepEqual(r.missing, ['has_refund_limit_clause'])
})

test('헬스장: 확인 안 됨은 직접 고른 "모름"이면 묻지 않고, 기본값 "모름"이면 묻는다', () => {
  const ext = { missing: [], unverified: ['has_refund_limit_clause', 'had_postponement'] }
  const r = followUpFields(ext, INITIAL_FORM, new Set(['has_refund_limit_clause']))
  assert.deepEqual(r.unverified, ['had_postponement'])
})

test('헬스장: 확인 안 됨은 빈칸이면 묻고(직접 비운 빈칸 포함), 값이 있으면 묻지 않는다', () => {
  const form = { ...INITIAL_FORM, list_price: '1500000' }
  const ext = { missing: [], unverified: ['provider_offer', 'list_price'] }
  const r = followUpFields(ext, form, new Set(['provider_offer']))
  assert.deepEqual(r.unverified, ['provider_offer'])
})

test('헬스장: 필수 누락과 확인 안 됨에 모두 있으면 필수 누락으로만 묻고, 폼에 없는 이름은 버린다', () => {
  const ext = { missing: ['paid_amount', 'no_such_field'], unverified: ['paid_amount', 'no_such_field'] }
  const r = followUpFields(ext, INITIAL_FORM, none)
  assert.deepEqual(r, { missing: ['paid_amount'], unverified: [] })
})

// ---- 세탁 ----

test('세탁: 필수 누락 입증 여부는 직접 고른 "모름"이어도 다시 묻는다 (L10)', () => {
  const touched = new Set(['proof_available'])
  const r = laundryFollowUpFields({ missing: ['proof_available'], unverified: [] }, INITIAL_LAUNDRY_FORM, touched)
  assert.deepEqual(r.missing, ['proof_available'])
})

test('세탁: 확인 안 됨은 직접 고른 "모름"·"세트 아님"이면 묻지 않고, 기본값이면 묻는다', () => {
  const ext = { missing: [], unverified: ['special_agreement', 'set_type', 'uncollected'] }
  const r = laundryFollowUpFields(ext, INITIAL_LAUNDRY_FORM, new Set(['special_agreement', 'set_type']))
  assert.deepEqual(r.unverified, ['uncollected'])
})

test('세탁: 표에 없는 품목(item_unlisted)은 품목 칸으로 판단하고 이름은 그대로 돌려준다', () => {
  const ext = { missing: [], unverified: ['item_unlisted'] }
  assert.deepEqual(laundryFollowUpFields(ext, INITIAL_LAUNDRY_FORM, none).unverified, ['item_unlisted'])
  const chosen = { ...INITIAL_LAUNDRY_FORM, item_key: UNLISTED }
  assert.deepEqual(laundryFollowUpFields(ext, chosen, new Set(['item_key'])).unverified, [])
})

test('세탁: 합친 뒤 채워진 필수 항목은 묻지 않고, 폼에 없는 이름은 버린다', () => {
  const form = { ...INITIAL_LAUNDRY_FORM, purchase_price: '400000' }
  const ext = { missing: ['purchase_price', 'purchase_date', 'no_such_field'], unverified: ['purchase_date'] }
  const r = laundryFollowUpFields(ext, form, none)
  assert.deepEqual(r, { missing: ['purchase_date'], unverified: [] })
})
