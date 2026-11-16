// 내 기록 저장 모듈 (src/history/storage.ts, MVP_SPEC 18절). 가짜 Storage로 돈다 (새 의존성 없음).
// 실행: npm test  (Node 내장 테스트 러너)
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, test } from 'node:test'
import {
  addItem,
  clearAll,
  deleteItem,
  HISTORY_KEY,
  isStorageAvailable,
  loadItems,
  MAX_ITEM_BYTES,
  MAX_ITEMS,
  MAX_SENTENCE_LENGTH,
  type NewHistoryItem,
  type StorageLike,
} from '../src/history/storage.ts'

class FakeStorage implements StorageLike {
  data = new Map<string, string>()
  getItem(k: string): string | null {
    return this.data.has(k) ? (this.data.get(k) as string) : null
  }
  setItem(k: string, v: string): void {
    this.data.set(k, String(v))
  }
  removeItem(k: string): void {
    this.data.delete(k)
  }
}

/** setItem이 QuotaExceededError를 낸다 */
class FullStorage extends FakeStorage {
  setItem(): void {
    const err = new Error('quota')
    err.name = 'QuotaExceededError'
    throw err
  }
}

/** 접근할 때마다 SecurityError (사이트 데이터 차단 등) */
class BlockedStorage implements StorageLike {
  getItem(): string | null {
    throw new Error('SecurityError')
  }
  setItem(): void {
    throw new Error('SecurityError')
  }
  removeItem(): void {
    throw new Error('SecurityError')
  }
}

// 승인 케이스 L1 모양의 계산 응답 (값은 서버 응답을 그대로 옮긴 것, 여기서 계산하지 않는다)
const result = (amount: number) => ({
  result: { badge: '✅ 기준 확인', calculated: true, amount, steps: [], flags: [], missing: [], notices: [], citations: [] },
  display: { badge: '✅ 기준 확인', screen_line: null, other_flags: [], notices: [], citations: [] },
})
const entry = (n: number, extra: Partial<NewHistoryItem> = {}): NewHistoryItem => ({
  domain: 'laundry',
  inputs: { purchase_price: 400000 + n },
  result: result(280000 + n),
  ...extra,
})

let seq = 0
const ids = () => `id-${++seq}`
const at = (i: number) => new Date(Date.UTC(2026, 10, 16, 0, i))

let realFetch: typeof globalThis.fetch
let fetchCalls = 0
beforeEach(() => {
  seq = 0
  fetchCalls = 0
  realFetch = globalThis.fetch
  globalThis.fetch = (() => {
    fetchCalls += 1
    return Promise.reject(new Error('no network'))
  }) as typeof globalThis.fetch
})
afterEach(() => {
  globalThis.fetch = realFetch
  // 어떤 테스트에서도 저장 모듈이 네트워크를 부르지 않는다
  assert.equal(fetchCalls, 0)
})

test('저장 → 목록 최신순 → 항목 삭제 → 전체 삭제', () => {
  const s = new FakeStorage()
  assert.equal(addItem(s, entry(1), at(1), ids).kind, 'saved')
  assert.equal(addItem(s, entry(2), at(2), ids).kind, 'saved')
  assert.equal(addItem(s, entry(3), at(3), ids).kind, 'saved')
  assert.deepEqual(
    loadItems(s).map((i) => i.id),
    ['id-3', 'id-2', 'id-1'],
  )
  const first = loadItems(s)[0]
  assert.equal(first.savedAt, '2026-11-16T00:03:00.000Z')
  assert.equal(first.domain, 'laundry')
  assert.deepEqual(first.result, result(280003))
  assert.ok(deleteItem(s, 'id-2'))
  assert.deepEqual(
    loadItems(s).map((i) => i.id),
    ['id-3', 'id-1'],
  )
  assert.ok(clearAll(s))
  assert.deepEqual(loadItems(s), [])
  assert.equal(s.getItem(HISTORY_KEY), null)
})

test('저장 형식은 {"v":1,"items":[…]}', () => {
  const s = new FakeStorage()
  addItem(s, entry(1, { sentence: '정장 상의가 줄었어요' }), at(1), ids)
  const raw = JSON.parse(s.getItem(HISTORY_KEY) as string)
  assert.equal(raw.v, 1)
  assert.equal(raw.items.length, 1)
  assert.deepEqual(Object.keys(raw.items[0]).sort(), ['domain', 'id', 'inputs', 'result', 'savedAt', 'sentence'])
})

test('문장이 없으면 sentence 키를 두지 않는다', () => {
  const s = new FakeStorage()
  addItem(s, entry(1, { sentence: null }), at(1), ids)
  addItem(s, entry(2, { sentence: '   ' }), at(2), ids)
  for (const it of loadItems(s)) assert.equal('sentence' in it, false)
})

test(`${MAX_ITEMS}건을 넘으면 가장 오래된 것부터 지우고 지운 건수를 알린다`, () => {
  const s = new FakeStorage()
  for (let i = 1; i <= MAX_ITEMS; i++) assert.equal(addItem(s, entry(i), at(i), ids).kind, 'saved')
  const out = addItem(s, entry(99), at(30), ids)
  assert.equal(out.kind, 'saved')
  if (out.kind === 'saved') assert.equal(out.removed, 1)
  const list = loadItems(s)
  assert.equal(list.length, MAX_ITEMS)
  assert.equal(list[0].id, 'id-21')
  assert.ok(!list.some((i) => i.id === 'id-1'))
})

test('직렬화 16KB를 넘는 항목은 저장하지 않는다', () => {
  const s = new FakeStorage()
  const big = { ...result(1), display: { pad: 'x'.repeat(MAX_ITEM_BYTES) } }
  assert.deepEqual(addItem(s, { domain: 'gym', inputs: {}, result: big }, at(1), ids), { kind: 'too_large' })
  assert.equal(s.getItem(HISTORY_KEY), null)
})

test('문장이 입력창 한도를 넘으면 저장하지 않는다', () => {
  const s = new FakeStorage()
  const out = addItem(s, entry(1, { sentence: '가'.repeat(MAX_SENTENCE_LENGTH + 1) }), at(1), ids)
  assert.deepEqual(out, { kind: 'too_large' })
  assert.equal(addItem(s, entry(1, { sentence: '가'.repeat(MAX_SENTENCE_LENGTH) }), at(1), ids).kind, 'saved')
})

test('같은 품목·폼 값·결과는 키 순서가 달라도 중복으로 거부한다', () => {
  const s = new FakeStorage()
  addItem(s, { domain: 'gym', inputs: { a: 1, b: 2 }, result: { x: { p: 1, q: 2 } } }, at(1), ids)
  assert.deepEqual(addItem(s, { domain: 'gym', inputs: { b: 2, a: 1 }, result: { x: { q: 2, p: 1 } } }, at(2), ids), {
    kind: 'duplicate',
  })
  // 품목이 다르거나 결과가 다르면 저장한다
  assert.equal(addItem(s, { domain: 'laundry', inputs: { a: 1, b: 2 }, result: { x: { p: 1, q: 2 } } }, at(3), ids).kind, 'saved')
  assert.equal(addItem(s, { domain: 'gym', inputs: { a: 1, b: 2 }, result: { x: { p: 1, q: 3 } } }, at(4), ids).kind, 'saved')
  assert.equal(loadItems(s).length, 3)
})

test('깨진 JSON·버전 불일치·모양이 다른 최상위 값은 빈 목록이고 읽기만으로 원본을 지우지 않는다', () => {
  for (const raw of ['{not json', JSON.stringify({ v: 2, items: [] }), JSON.stringify([1, 2]), JSON.stringify({ v: 1, items: 'x' })]) {
    const s = new FakeStorage()
    s.setItem(HISTORY_KEY, raw)
    assert.deepEqual(loadItems(s), [])
    assert.equal(s.getItem(HISTORY_KEY), raw)
  }
})

test('다른 버전의 저장 값은 덮어쓰지 않는다 (저장하지 못했습니다)', () => {
  const s = new FakeStorage()
  const raw = JSON.stringify({ v: 2, items: [{ id: 'future' }] })
  s.setItem(HISTORY_KEY, raw)
  assert.deepEqual(addItem(s, entry(1), at(1), ids), { kind: 'error' })
  assert.equal(s.getItem(HISTORY_KEY), raw)
})

test('모양이 틀린 항목은 조용히 빼고 나머지를 보여 준다', () => {
  const s = new FakeStorage()
  const good = { id: 'ok', savedAt: '2026-11-16T00:00:00.000Z', domain: 'gym', inputs: {}, result: {} }
  const bad = [
    { ...good, id: 1 },
    { ...good, id: '' },
    { ...good, savedAt: 5 },
    { ...good, domain: 'car' },
    { ...good, inputs: null },
    { ...good, inputs: [] },
    { ...good, result: 'x' },
    { ...good, sentence: 3 },
    null,
    'x',
  ]
  s.setItem(HISTORY_KEY, JSON.stringify({ v: 1, items: [bad[0], good, ...bad.slice(1)] }))
  assert.deepEqual(
    loadItems(s).map((i) => i.id),
    ['ok'],
  )
})

test('쓰기 오류(QuotaExceededError)는 잡아서 error로 돌려준다', () => {
  const s = new FullStorage()
  assert.deepEqual(addItem(s, entry(1), at(1), ids), { kind: 'error' })
})

test('접근 예외는 잡는다: 읽기는 빈 목록, 저장·삭제는 실패로', () => {
  const s = new BlockedStorage()
  assert.deepEqual(loadItems(s), [])
  assert.deepEqual(addItem(s, entry(1), at(1), ids), { kind: 'error' })
  assert.equal(deleteItem(s, 'x'), false)
  assert.equal(clearAll(s), false)
})

test('isStorageAvailable: 쓰기·읽기·삭제 시험', () => {
  assert.equal(isStorageAvailable(new FakeStorage()), true)
  assert.equal(isStorageAvailable(new FullStorage()), false)
  assert.equal(isStorageAvailable(new BlockedStorage()), false)
  assert.equal(isStorageAvailable(null), false)
  assert.equal(isStorageAvailable(undefined), false)
  // 시험용 키를 남기지 않는다
  const s = new FakeStorage()
  isStorageAvailable(s)
  assert.equal(s.data.size, 0)
})

test('문장 분석 응답의 extraction·evidence·clauses 키는 저장하지 않는다', () => {
  const s = new FakeStorage()
  addItem(
    s,
    {
      domain: 'gym',
      sentence: '헬스장 해지',
      inputs: { paid_amount: 1, extraction: { fields: {} }, evidence: { a: 'b' }, clauses: { candidates: [] } },
      result: { ...result(1), extraction: {}, evidence: {}, clauses: {} },
    },
    at(1),
    ids,
  )
  const raw = s.getItem(HISTORY_KEY) as string
  const item = loadItems(s)[0]
  for (const key of ['extraction', 'evidence', 'clauses']) {
    assert.equal(key in item.inputs, false)
    assert.equal(key in item.result, false)
    assert.ok(!raw.includes(`"${key}"`), key)
  }
  assert.deepEqual(item.inputs, { paid_amount: 1 })
})

test('crypto.randomUUID가 없으면 시각+난수 id를 쓴다', async () => {
  const { defaultId } = await import('../src/history/storage.ts')
  const desc = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { value: {}, configurable: true })
  try {
    const id = defaultId(new Date(0))
    assert.match(id, /^0-[a-z0-9]+$/)
  } finally {
    if (desc) Object.defineProperty(globalThis, 'crypto', desc)
  }
  assert.match(defaultId(), /^[0-9a-f-]{36}$/)
})

test('저장·표시 코드에 네트워크 호출(fetch·XMLHttpRequest·sendBeacon)이 없다', () => {
  for (const f of [
    '../src/history/storage.ts',
    '../src/history/view.ts',
    '../src/components/HistoryPanel.tsx',
    '../src/components/HistorySaveButton.tsx',
  ]) {
    const src = readFileSync(new URL(f, import.meta.url), 'utf8')
    assert.ok(!/\bfetch\s*\(|XMLHttpRequest|sendBeacon|from '\.\.\/api'|from '\.\/api'/.test(src), f)
  }
})
