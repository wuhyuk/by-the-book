// 내 기록 (기능 플래그 local_history, MVP_SPEC 18절). 브라우저 localStorage에만 저장하고 서버로 보내지 않는다.
// 순수 함수: Storage 객체를 인자로 받는다 (테스트는 가짜 Storage). 이 모듈은 네트워크 함수를 부르지 않는다.
// 저장하는 금액은 /api/calculate 응답 그대로이며 여기서 계산·변환하지 않는다.

export const HISTORY_KEY = 'btb.history.v1'
export const HISTORY_VERSION = 1
export const MAX_ITEMS = 20
/** 항목 하나를 JSON으로 직렬화한 UTF-8 바이트 상한 */
export const MAX_ITEM_BYTES = 16 * 1024
/** 문장 입력창 한도와 같다 (components/AnalyzePanel.tsx MAX_LENGTH, /api/analyze 2,000자) */
export const MAX_SENTENCE_LENGTH = 2000
const PROBE_KEY = 'btb.history.probe'

export type HistoryDomain = 'gym' | 'laundry' | 'appliance'
export const HISTORY_DOMAINS: readonly HistoryDomain[] = ['gym', 'laundry', 'appliance']

/** 문장 분석 응답에서 저장하지 않는 키 (문장 원문·폼 값·계산 결과만 저장한다) */
export const EXCLUDED_KEYS: readonly string[] = ['extraction', 'evidence', 'clauses']

export interface HistoryItem {
  id: string
  /** ISO 8601 (UTC). 화면에서 한국시간으로 표시한다 */
  savedAt: string
  domain: HistoryDomain
  /** 문장 입력으로 폼을 채운 경우에만 */
  sentence?: string
  /** /api/calculate에 보낸 폼 값 */
  inputs: Record<string, unknown>
  /** /api/calculate 응답 그대로 ({result, display}) */
  result: Record<string, unknown>
}

export type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

/** 화면에 넘기는 저장소 상태. null(플래그 꺼짐)과 storage null(이 브라우저에서 저장 불가)을 나눈다 */
export interface HistoryAccess {
  storage: StorageLike | null
}

export interface NewHistoryItem {
  domain: HistoryDomain
  inputs: object
  result: object
  sentence?: string | null
}

export type AddOutcome =
  | { kind: 'saved'; item: HistoryItem; removed: number }
  | { kind: 'duplicate' }
  | { kind: 'too_large' }
  | { kind: 'error' }

function isPlainObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}

function isHistoryItem(v: unknown): v is HistoryItem {
  if (!isPlainObject(v)) return false
  return (
    typeof v.id === 'string' &&
    v.id !== '' &&
    typeof v.savedAt === 'string' &&
    typeof v.domain === 'string' &&
    (HISTORY_DOMAINS as readonly string[]).includes(v.domain) &&
    (v.sentence === undefined || typeof v.sentence === 'string') &&
    isPlainObject(v.inputs) &&
    isPlainObject(v.result)
  )
}

type Raw =
  | { status: 'empty' | 'ok'; items: HistoryItem[] }
  | { status: 'corrupt' | 'other_version' | 'unreadable'; items: HistoryItem[] }

/** 저장된 값을 읽는다. 읽기만 하고 원본을 지우거나 고치지 않는다. */
function readRaw(storage: StorageLike): Raw {
  let text: string | null
  try {
    text = storage.getItem(HISTORY_KEY)
  } catch {
    return { status: 'unreadable', items: [] }
  }
  if (text === null) return { status: 'empty', items: [] }
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    return { status: 'corrupt', items: [] }
  }
  if (!isPlainObject(parsed)) return { status: 'corrupt', items: [] }
  if (parsed.v !== HISTORY_VERSION) return { status: 'other_version', items: [] }
  if (!Array.isArray(parsed.items)) return { status: 'corrupt', items: [] }
  // 모양이 틀린 항목은 조용히 뺀다
  return { status: 'ok', items: parsed.items.filter(isHistoryItem) }
}

function write(storage: StorageLike, items: HistoryItem[]): boolean {
  try {
    storage.setItem(HISTORY_KEY, JSON.stringify({ v: HISTORY_VERSION, items }))
    return true
  } catch {
    // QuotaExceededError, SecurityError 등
    return false
  }
}

/** 쓰기·읽기·삭제를 시험한다. 하나라도 실패하면 false (예외를 밖으로 내지 않는다) */
export function isStorageAvailable(storage: StorageLike | null | undefined): boolean {
  if (!storage) return false
  try {
    storage.setItem(PROBE_KEY, '1')
    const ok = storage.getItem(PROBE_KEY) === '1'
    storage.removeItem(PROBE_KEY)
    return ok && storage.getItem(PROBE_KEY) === null
  } catch {
    return false
  }
}

/** 브라우저 localStorage. 접근 자체가 예외를 내는 환경(차단된 사이트 데이터 등)이면 null */
export function browserStorage(): StorageLike | null {
  try {
    const s = (globalThis as { localStorage?: StorageLike }).localStorage
    return s ?? null
  } catch {
    return null
  }
}

/** 저장한 기록 (최신순). 읽지 못하면 빈 목록 */
export function loadItems(storage: StorageLike): HistoryItem[] {
  return readRaw(storage).items
}

function withoutExcluded(obj: object): Record<string, unknown> {
  return Object.fromEntries(Object.entries(obj).filter(([k]) => !EXCLUDED_KEYS.includes(k)))
}

/** 키 순서와 상관없는 비교용 직렬화 */
function stable(v: unknown): string {
  if (Array.isArray(v)) return `[${v.map(stable).join(',')}]`
  if (isPlainObject(v)) {
    return `{${Object.keys(v)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stable(v[k])}`)
      .join(',')}}`
  }
  return JSON.stringify(v) ?? 'null'
}

function sameEntry(a: HistoryItem, domain: HistoryDomain, inputs: Record<string, unknown>, result: Record<string, unknown>): boolean {
  return a.domain === domain && stable(a.inputs) === stable(inputs) && stable(a.result) === stable(result)
}

export function defaultId(now: Date = new Date()): string {
  const c = (globalThis as { crypto?: { randomUUID?: () => string } }).crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `${now.getTime().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export function itemBytes(item: HistoryItem): number {
  return new TextEncoder().encode(JSON.stringify(item)).length
}

/**
 * 기록 하나를 맨 앞(최신)에 더한다. 같은 품목+폼 값+결과가 있으면 저장하지 않는다.
 * 20건을 넘으면 가장 오래된 것부터 지운다 (removed). 다른 버전의 저장 값이 있으면 덮어쓰지 않는다.
 */
export function addItem(
  storage: StorageLike,
  entry: NewHistoryItem,
  now: Date = new Date(),
  makeId: (now: Date) => string = defaultId,
): AddOutcome {
  if (!(HISTORY_DOMAINS as readonly string[]).includes(entry.domain)) return { kind: 'error' }
  if (!isPlainObject(entry.inputs) || !isPlainObject(entry.result)) return { kind: 'error' }
  const sentence = typeof entry.sentence === 'string' && entry.sentence.trim() !== '' ? entry.sentence : undefined
  if (sentence !== undefined && sentence.length > MAX_SENTENCE_LENGTH) return { kind: 'too_large' }

  const raw = readRaw(storage)
  if (raw.status === 'unreadable' || raw.status === 'other_version') return { kind: 'error' }
  const inputs = withoutExcluded(entry.inputs)
  const result = withoutExcluded(entry.result)
  if (raw.items.some((it) => sameEntry(it, entry.domain, inputs, result))) return { kind: 'duplicate' }

  const item: HistoryItem = {
    id: makeId(now),
    savedAt: now.toISOString(),
    domain: entry.domain,
    ...(sentence !== undefined ? { sentence } : {}),
    inputs,
    result,
  }
  if (itemBytes(item) > MAX_ITEM_BYTES) return { kind: 'too_large' }

  const next = [item, ...raw.items]
  const removed = Math.max(0, next.length - MAX_ITEMS)
  if (!write(storage, next.slice(0, MAX_ITEMS))) return { kind: 'error' }
  return { kind: 'saved', item, removed }
}

/** 항목 하나를 지운다. 성공하면 true (없는 id도 true) */
export function deleteItem(storage: StorageLike, id: string): boolean {
  const raw = readRaw(storage)
  if (raw.status !== 'ok') return raw.status === 'empty'
  return write(
    storage,
    raw.items.filter((it) => it.id !== id),
  )
}

/** 저장한 기록을 모두 지운다 (키를 없앤다). */
export function clearAll(storage: StorageLike): boolean {
  try {
    storage.removeItem(HISTORY_KEY)
    return true
  } catch {
    return false
  }
}
