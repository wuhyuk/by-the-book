// 내 기록 표시 규칙 (src/history/view.ts, MVP_SPEC 18절). 금액은 저장된 응답 값을 고를 뿐 계산하지 않는다.
// 실행: npm test  (Node 내장 테스트 러너, 새 의존성 없음)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { StorageLike } from '../src/history/storage.ts'
import {
  amountSummary,
  baseDateText,
  formatKst,
  historyAccess,
  isRenderable,
  kstDate,
  savedBadge,
  saveMessage,
} from '../src/history/view.ts'
import { HISTORY_TEXT } from '../src/texts.ts'

const memory = (): StorageLike => {
  const m = new Map<string, string>()
  return {
    getItem: (k) => (m.has(k) ? (m.get(k) as string) : null),
    setItem: (k, v) => void m.set(k, v),
    removeItem: (k) => void m.delete(k),
  }
}

test('꺼짐: 저장소를 건드리지 않고 off (버튼·패널·저장 안내 없음)', () => {
  let called = 0
  const r = historyAccess(['set_partial', 'appliance'], () => {
    called += 1
    return memory()
  })
  assert.deepEqual(r, { mode: 'off', storage: null })
  assert.equal(called, 0)
  assert.equal(historyAccess([], () => memory()).mode, 'off')
})

test('켜짐: 저장소를 쓸 수 있으면 on, 아니면 unavailable', () => {
  assert.equal(historyAccess(['local_history'], memory).mode, 'on')
  assert.deepEqual(historyAccess(['local_history'], () => null), { mode: 'unavailable', storage: null })
  const blocked = () => {
    throw new Error('SecurityError')
  }
  assert.deepEqual(historyAccess(['local_history'], blocked), { mode: 'unavailable', storage: null })
  const readOnly: StorageLike = {
    getItem: () => null,
    setItem: () => {
      throw new Error('QuotaExceededError')
    },
    removeItem: () => {},
  }
  assert.equal(historyAccess(['local_history'], () => readOnly).mode, 'unavailable')
})

test('저장 결과별 안내 문구', () => {
  const item = { id: 'a', savedAt: '', domain: 'gym' as const, inputs: {}, result: {} }
  assert.equal(saveMessage({ kind: 'saved', item, removed: 0 }), HISTORY_TEXT.saved)
  assert.equal(saveMessage({ kind: 'saved', item, removed: 1 }), HISTORY_TEXT.savedTrimmed(1))
  assert.equal(saveMessage({ kind: 'duplicate' }), '이미 저장되어 있습니다.')
  assert.equal(saveMessage({ kind: 'too_large' }), '저장하기에는 내용이 너무 큽니다.')
  assert.equal(saveMessage({ kind: 'error' }), '저장하지 못했습니다.')
})

test('저장 시각은 한국시간 YYYY-MM-DD HH:mm', () => {
  assert.equal(formatKst('2026-11-16T15:30:00.000Z'), '2026-11-17 00:30')
  assert.equal(formatKst('2026-11-16T00:05:00.000Z'), '2026-11-16 09:05')
  assert.equal(kstDate('2026-11-16T15:30:00.000Z'), '2026-11-17')
  assert.equal(formatKst('nope'), 'nope')
})

const laundryL1 = {
  result: {
    badge: '✅ 기준 확인',
    calculated: true,
    amount: 280000,
    sensitivity_min: 280000,
    sensitivity_max: 280000,
    steps: [],
    flags: [],
    missing: [],
    notices: [],
    citations: [],
  },
  display: {
    badge: '✅ 기준 확인',
    other_flags: [],
    notices: [],
    citations: [],
    rule_source: { effective_date: '2025-01-01', retrieved_at: '2026-11-02' },
  },
}

test('세탁·가전: amount, 없으면 결정 민감도 범위, 계산 안 함', () => {
  assert.equal(savedBadge(laundryL1), '✅ 기준 확인')
  assert.equal(amountSummary('laundry', laundryL1), '280,000원')
  const range = { result: { calculated: true, amount: null, sensitivity_min: 74074, sensitivity_max: 86420 } }
  assert.equal(amountSummary('laundry', range), '74,074원~86,420원')
  assert.equal(amountSummary('appliance', { result: { calculated: true, amount: 920000 } }), '920,000원')
  assert.equal(amountSummary('appliance', { result: { calculated: false, amount: null } }), HISTORY_TEXT.notCalculated)
  assert.equal(amountSummary('laundry', {}), HISTORY_TEXT.notCalculated)
})

test('헬스장: 기준·시나리오별 환급액 중 가장 작은 값~가장 큰 값', () => {
  const gym = {
    result: {
      calculated: true,
      results: {
        period: { A: { refund: 900000 }, B: { refund: 850000 } },
        session: { A: { refund: 700000 }, B: null },
      },
    },
  }
  assert.equal(amountSummary('gym', gym), '700,000원~900,000원')
  const one = { result: { calculated: true, results: { period: { A: { refund: 1000 }, B: null } } } }
  assert.equal(amountSummary('gym', one), '1,000원')
})

test('기준일은 응답 rule_source에 있을 때만', () => {
  assert.equal(baseDateText(laundryL1), '기준 시행일 2025-01-01, 원문 확인일 2026-11-02')
  assert.equal(baseDateText({ display: {} }), null)
})

test('결과 카드에 넣을 수 없는 모양이면 요약으로', () => {
  assert.equal(isRenderable('laundry', laundryL1), true)
  assert.equal(isRenderable('gym', laundryL1), false) // 헬스장은 results가 있어야 한다
  assert.equal(isRenderable('laundry', { result: {}, display: {} }), false)
  assert.equal(isRenderable('appliance', {}), false)
})
