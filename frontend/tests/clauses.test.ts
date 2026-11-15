// 조항 확인 상태 문구 (src/clauses.ts). 사람이 확인했다고 읽히는 말(확인됨·검증됨)을 쓰지 않는다.
// 실행: npm test  (Node 내장 테스트 러너, 새 의존성 없음)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clauseStatus } from '../src/clauses.ts'
import { CLAUSE_TEXT } from '../src/texts.ts'

test('verified는 자동 대조, user_checked null은 기록 없음', () => {
  assert.deepEqual(clauseStatus(true, null), ['자동 대조 통과', '조항 단위 사용자 대조 기록 없음'])
  assert.deepEqual(clauseStatus(true, true), ['자동 대조 통과', '사용자 표본 대조 기록 있음'])
  assert.deepEqual(clauseStatus(false, false), ['자동 대조 미완료', '사용자 대조 전'])
})

test('상태 문구에 확인됨·검증됨 같은 표현이 없다', () => {
  const all = [true, false].flatMap((v) => [null, true, false].flatMap((u) => clauseStatus(v, u)))
  for (const text of [...all, ...Object.values(CLAUSE_TEXT).filter((x) => typeof x === 'string')]) {
    assert.ok(!/확인됨|검증됨|검증 완료|확인 완료/.test(text), text)
  }
})
