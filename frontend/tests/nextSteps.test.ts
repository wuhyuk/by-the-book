// 다음 행동 채널 표시 규칙 (src/nextSteps.ts). 확인된 번호·https 주소만 링크로 만들고, 확인하지 못한 값은 '확인 필요'.
// 실행: npm test  (Node 내장 테스트 러너, 새 의존성 없음)
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { channelView } from '../src/nextSteps.ts'
import type { NextStepsChannel } from '../src/types.ts'

const base: NextStepsChannel = {
  id: 'x',
  name: '창구',
  phone: '1372',
  url: 'https://example.invalid/page',
  how: '이용 방법',
  source_urls: ['https://example.invalid/page'],
  checked_on: '2026-11-16',
  status: 'confirmed',
}

test('확인된 채널: 전화·누리집 링크와 확인일', () => {
  const v = channelView(base)
  assert.equal(v.telHref, 'tel:1372')
  assert.equal(v.url, 'https://example.invalid/page')
  assert.equal(v.how, '이용 방법')
  assert.equal(v.status, '확인일 2026-11-16')
})

test('확인 필요 채널: 링크 없이 확인 필요', () => {
  const v = channelView({ ...base, status: 'needs_check', url: null, how: null, checked_on: null })
  assert.equal(v.telHref, null)
  assert.equal(v.url, null)
  assert.equal(v.how, '확인 필요')
  assert.equal(v.status, '확인 필요')
})

test('숫자가 아닌 전화번호·https가 아닌 주소는 링크로 만들지 않는다', () => {
  const v = channelView({ ...base, phone: '13-72', url: 'http://example.invalid' })
  assert.equal(v.telHref, null)
  assert.equal(v.url, null)
})
