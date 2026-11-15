// 가전 폼 변환 (MVP_SPEC 13절, 2026-11-15). Node 내장 테스트 러너로 돈다 (새 의존성 없음).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { APPLIANCE_UNLISTED, buildApplianceInput, INITIAL_APPLIANCE_FORM, type ApplianceForm } from '../src/applianceForm.ts'

// 승인 케이스 A-1 입력 (TV 1,200,000, 2022-03-15 → 2025-03-15, 제조 2022-01-10)
const A1: ApplianceForm = {
  ...INITIAL_APPLIANCE_FORM,
  item_key: 'tv',
  purchase_price: '1,200,000',
  purchase_date: '2022-03-15',
  request_date: '2025-03-15',
  manufacture_date: '2022-01-10',
  parts_unavailable: 'yes',
  certificate_confirmed: 'yes',
}

test('A-1 입력을 그대로 보낸다 (숫자는 정수로만 바꾼다)', () => {
  const built = buildApplianceInput(A1)
  assert.ok(built.ok)
  assert.deepEqual(built.input, {
    judgment_requested: false,
    item_key: 'tv',
    item_unlisted: false,
    purchase_price: 1200000,
    purchase_date: '2022-03-15',
    request_date: '2025-03-15',
    manufacture_date: '2022-01-10',
    parts_unavailable: true,
    certificate_confirmed: true,
    certificate_warranty_months: null,
    certificate_parts_years: null,
    provider_offer: null,
  })
})

test('목록에 없는 품목은 item_unlisted, 모름은 null', () => {
  const built = buildApplianceInput({ ...A1, item_key: APPLIANCE_UNLISTED, parts_unavailable: 'unknown' })
  assert.ok(built.ok)
  assert.equal(built.input.item_key, null)
  assert.equal(built.input.item_unlisted, true)
  assert.equal(built.input.parts_unavailable, null)
})

test('제조일을 비우면 null (엔진이 PARTS_PERIOD_UNCONFIRMED로 판정)', () => {
  const built = buildApplianceInput({ ...A1, manufacture_date: '' })
  assert.ok(built.ok)
  assert.equal(built.input.manufacture_date, null)
})

test('숫자 형식 오류는 보내기 전에 막는다', () => {
  const built = buildApplianceInput({ ...A1, purchase_price: '12만원', certificate_parts_years: '1.5' })
  assert.equal(built.ok, false)
  if (!built.ok) assert.deepEqual(built.invalidFields, ['purchase_price', 'certificate_parts_years'])
})
