// 다음 행동(/api/guide next_steps) 표시용 순수 함수. 서버가 준 고정 텍스트만 쓰고 새 내용을 만들지 않는다.
import type { NextStepsChannel } from './types.ts'
import { NEXT_STEPS_TEXT } from './texts.ts'

export interface ChannelView {
  /** 전화 링크 (tel:) — 확인된 번호가 있을 때만 */
  telHref: string | null
  phoneText: string | null
  /** 누리집 링크 — 확인된 https 주소만 */
  url: string | null
  how: string
  /** 확인일 문구, 확인하지 못했으면 '확인 필요' */
  status: string
}

export function channelView(c: NextStepsChannel): ChannelView {
  const confirmed = c.status === 'confirmed'
  const phone = confirmed && c.phone && /^\d+$/.test(c.phone) ? c.phone : null
  const url = confirmed && c.url && c.url.startsWith('https://') ? c.url : null
  return {
    telHref: phone ? `tel:${phone}` : null,
    phoneText: phone ? NEXT_STEPS_TEXT.phone(phone) : null,
    url,
    how: confirmed && c.how ? c.how : NEXT_STEPS_TEXT.needsCheck,
    status: confirmed && c.checked_on ? NEXT_STEPS_TEXT.checkedOn(c.checked_on) : NEXT_STEPS_TEXT.needsCheck,
  }
}
