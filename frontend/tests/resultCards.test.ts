// 결과 카드 팝업의 카드 나누기 (src/results/cards.ts, 기능 플래그 result_cards).
// 기대값은 모두 이 파일의 가짜 응답에서 고른 값이다 (금액을 새로 계산하지 않는지 확인한다).
// 실행: npm test  (Node 내장 테스트 러너, 새 의존성 없음)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  applianceCardSource,
  buildResultCards,
  gymCardSource,
  laundryCardSource,
} from '../src/results/cards.ts'
import { LAUNDRY_TEXT, RESULT_TEXT } from '../src/texts.ts'
import type {
  ApplianceCalculateResponse,
  CalculateResponse,
  LaundryCalculateResponse,
  NextSteps,
} from '../src/types.ts'

const citation = {
  id: 'fake_1',
  label: '가짜 조항',
  text: '가짜 원문',
  source: { name: '가짜 출처', url: 'https://example.invalid/', retrieved_at: '2026-01-01' },
}

const gymRuleSource = {
  name: '가짜 기준',
  notice_number: '가짜-1',
  url: 'https://example.invalid/',
  effective_date: '2026-01-01',
  last_amended: '2026-01-01',
  retrieved_at: '2026-01-01',
}

function gym(over: { result?: Partial<CalculateResponse['result']>; display?: Partial<CalculateResponse['display']> } = {}): CalculateResponse {
  return {
    result: {
      badge: '🔍 추가 확인 필요',
      calculated: true,
      results: {
        period: {
          elapsed: 10,
          units: 100,
          A: { used_amount: 111, raw_refund: 222, refund: 333 },
          B: { used_amount: 444, raw_refund: 555, refund: 666 },
        },
      },
      penalty: 7,
      penalty_cap: 8,
      refund_kind: 'minimum',
      deposit_refund: 0,
      contract_days: 100,
      steps: [{ label: '가짜 단계', formula: '가짜 식', amount: 999 }],
      flags: ['X'],
      missing: [],
      notices: ['N'],
      citations: ['fake_1'],
      ...over.result,
    },
    display: {
      badge: '🔍 추가 확인 필요',
      screen_line: { code: 'X', text: '가짜 화면 한 줄' },
      other_flags: [{ code: 'Y', text: '가짜 다른 사유' }],
      notices: [{ code: 'N', text: '가짜 안내' }],
      citations: [citation],
      rule_source: gymRuleSource,
      disclaimer: '가짜 고지',
      consult: null,
      withdrawal_guide: null,
      ...over.display,
    },
  } as CalculateResponse
}

test('일반 결과: 상단에 배지·금액, 카드 순서는 요약 → 계산 과정 → 근거 조항', () => {
  const src = gymCardSource(gym())
  assert.equal(src.header.badge, '🔍 추가 확인 필요')
  assert.equal(src.header.tone, 'review')
  assert.equal(src.header.status, 'amount')
  // 응답 값을 그대로 고른다 (A 333, B 666)
  assert.deepEqual(
    src.header.amounts.map((a) => a.value),
    [333, 666],
  )
  const cards = buildResultCards(src)
  assert.deepEqual(
    cards.map((c) => c.kind),
    ['summary', 'steps', 'citations'],
  )
  const summary = cards[0]
  assert.ok(summary.kind === 'summary')
  assert.equal(summary.screenLine, '가짜 화면 한 줄')
  assert.deepEqual(summary.otherFlags, ['가짜 다른 사유'])
  assert.deepEqual(summary.notices, ['가짜 안내'])
  const steps = cards[1]
  assert.ok(steps.kind === 'steps')
  assert.equal(steps.steps[0].amount, 999)
})

test('같은 입력이면 항상 같은 카드 목록', () => {
  const data = gym()
  assert.deepEqual(buildResultCards(gymCardSource(data)), buildResultCards(gymCardSource(data)))
  assert.deepEqual(buildResultCards(gymCardSource(gym())), buildResultCards(gymCardSource(gym())))
})

test('정상가(B) 미계산: 금액 대신 null → 화면은 "계산하지 않음" 글자', () => {
  const data = gym({
    result: {
      results: { period: { elapsed: 1, units: 2, A: { used_amount: 1, raw_refund: 2, refund: 3 }, B: null } },
    },
  })
  const amounts = gymCardSource(data).header.amounts
  assert.equal(amounts.length, 2)
  assert.equal(amounts[0].value, 3)
  assert.equal(amounts[1].value, null)
})

test('판단 불가(❔): 금액 없이 배지와 안내만, 화면 한 줄은 요약 카드에 다시 쓰지 않음', () => {
  const data = gym({
    result: { badge: '❔ 판단 불가', calculated: false, results: {}, steps: [], refund_kind: null },
    display: {
      badge: '❔ 판단 불가',
      screen_line: { code: 'J', text: '가짜 판단 불가 안내' },
      other_flags: [],
      notices: [],
      citations: [],
      consult: { message: '가짜 상담 메시지', channels: ['가짜 창구'] },
    },
  })
  const src = gymCardSource(data)
  assert.equal(src.header.status, 'unavailable')
  assert.equal(src.header.tone, 'unknown')
  assert.deepEqual(src.header.amounts, [])
  assert.equal(src.header.notice, '가짜 판단 불가 안내')
  const cards = buildResultCards(src)
  // 요약에 쓸 내용이 없어 요약·계산 과정·근거 조항은 건너뛰고 다음 행동(상담 창구)만 남는다
  assert.deepEqual(
    cards.map((c) => c.kind),
    ['next'],
  )
})

test('근거 조항이 없으면 그 카드를 건너뜀', () => {
  const cards = buildResultCards(gymCardSource(gym({ display: { citations: [] } })))
  assert.deepEqual(
    cards.map((c) => c.kind),
    ['summary', 'steps'],
  )
})

test('계산하지 않음(🔍): 상태 not_calculated, 금액 없음, 빠진 항목은 요약 카드에 화면 이름으로', () => {
  const data = gym({
    result: { calculated: false, results: {}, steps: [], missing: ['paid_amount'] },
    display: { other_flags: [], notices: [], citations: [] },
  })
  const src = gymCardSource(data)
  assert.equal(src.header.status, 'not_calculated')
  assert.deepEqual(src.header.amounts, [])
  const cards = buildResultCards(src)
  assert.equal(cards.length, 1)
  assert.ok(cards[0].kind === 'summary')
  assert.equal(cards[0].missing.length, 1)
  assert.notEqual(cards[0].missing[0], 'paid_amount')
  assert.equal(RESULT_TEXT.notCalculated.length > 0, true)
})

test('보증금 환급이 있으면 상단에 따로 (응답 값 그대로)', () => {
  assert.equal(gymCardSource(gym({ result: { deposit_refund: 50 } })).header.deposit, 50)
  assert.equal(gymCardSource(gym()).header.deposit, null)
})

test('다음 행동: 설명 응답의 next_steps가 오면 마지막 카드로 붙음', () => {
  const next: NextSteps = {
    title: '가짜 다음 행동',
    checklist_title: '가짜 준비물',
    checklist: [],
    checklist_note: null,
    channels_title: '가짜 창구',
    channels: [],
    disclaimer: '가짜 고지',
  }
  const cards = buildResultCards(gymCardSource(gym()), next)
  assert.deepEqual(
    cards.map((c) => c.kind),
    ['summary', 'steps', 'citations', 'next'],
  )
  const last = cards[3]
  assert.ok(last.kind === 'next')
  assert.equal(last.nextSteps, next)
})

const laundryDisplay = {
  badge: '✅ 기준 확인',
  screen_line: null,
  other_flags: [],
  notices: [],
  citations: [citation],
  rule_source: { ...gymRuleSource, annex: '가짜 별표' },
  disclaimer: '가짜 고지',
  consult: null,
}

test('세탁: 금액·조회 칸·범위는 응답 값을 기존 문구에 넣기만', () => {
  const data = {
    result: {
      badge: '✅ 기준 확인',
      calculated: true,
      method: 'ratio',
      use_days: 30,
      life_years: 4,
      ratio_percent: 95,
      band_min_days: 0,
      band_max_days: 90,
      amount: 1234,
      fallback_amount: null,
      sensitivity_min: 1000,
      sensitivity_max: 1300,
      sensitivity_causes: ['use_days'],
      sensitivity_ratio_alt: 80,
      steps: [],
      flags: [],
      missing: [],
      notices: [],
      citations: ['fake_1'],
      set_type: null,
      hanbok_kind: null,
      damaged_parts: null,
      set_share_percent: null,
      set_base_raw: null,
    },
    display: laundryDisplay,
  } as LaundryCalculateResponse
  const src = laundryCardSource(data)
  assert.equal(src.header.tone, 'ok')
  assert.deepEqual(src.header.amounts, [{ label: LAUNDRY_TEXT.ratioLabel, value: 1234 }])
  assert.equal(src.header.hints.length, 2)
  // 요약 내용·계산 과정이 비어 있어 근거 조항 카드만
  assert.deepEqual(
    buildResultCards(src).map((c) => c.kind),
    ['citations'],
  )
})

test('가전: 금액은 응답 amount 그대로, 범위가 같으면 범위 줄 없음', () => {
  const data = {
    result: {
      badge: '🔍 추가 확인 필요',
      calculated: true,
      item_key: 'tv',
      row_id: 'r',
      warranty_months: 12,
      life_months: 60,
      used_months: 30,
      used_months_full: 30,
      partial_month: false,
      amount: 777,
      sensitivity_min: 777,
      sensitivity_max: 777,
      sensitivity_causes: [],
      steps: [{ label: 'a', formula: 'b', amount: null }],
      flags: [],
      missing: [],
      notices: [],
      citations: [],
    },
    display: { ...laundryDisplay, badge: '🔍 추가 확인 필요', citations: [] },
  } as ApplianceCalculateResponse
  const src = applianceCardSource(data)
  assert.equal(src.header.amounts[0].value, 777)
  assert.equal(src.header.hints.length, 1)
  assert.deepEqual(
    buildResultCards(src).map((c) => c.kind),
    ['steps'],
  )
})
