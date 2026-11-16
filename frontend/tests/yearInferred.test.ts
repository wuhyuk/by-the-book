// 연도 보완 안내 (기능 플래그 date_year_infer, 2026-11-16). Node 내장 테스트 러너로 돈다.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { INITIAL_FORM, mergeExtraction, yearInferredFields } from '../src/formState.ts'
import type { AnalyzeResult } from '../src/types.ts'

// 승인 비교표 C1 문장을 켜짐 상태로 분석한 응답 모양 (backend/tests/test_llm_date_infer.py test_c1_flag_on)
const c1On: AnalyzeResult = {
  fields: { start_date: '2026-03-01', end_date: '2026-08-31', notice_date: '2026-02-20', had_postponement: false },
  evidence: { start_date: '2026년 3월 1일부터', end_date: '8월 31일까지', notice_date: '2월 20일에 사정이 생겨서 해지' },
  unverified: [],
  missing: [],
  confirm: [],
  judgment_requested: false,
  year_inferred: { end_date: 2026, notice_date: 2026 },
}

test('채운 항목에만 연도 안내를 붙인다', () => {
  const merged = mergeExtraction(INITIAL_FORM, new Set(), c1On)
  assert.deepEqual(yearInferredFields(c1On, merged.filled), [
    ['end_date', 2026],
    ['notice_date', 2026],
  ])
})

test('사용자가 이미 입력한 항목은 채우지 않으므로 안내도 없다', () => {
  const form = { ...INITIAL_FORM, end_date: '2026-08-30' }
  const merged = mergeExtraction(form, new Set(['end_date']), c1On)
  assert.deepEqual(yearInferredFields(c1On, merged.filled), [['notice_date', 2026]])
})

test('꺼짐(키 없음)이면 빈 목록', () => {
  const { year_inferred: _omit, ...off } = c1On
  assert.deepEqual(yearInferredFields(off, ['end_date', 'notice_date']), [])
})
