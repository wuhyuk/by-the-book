// 결과 카드 팝업(result_cards)의 "다음 행동" 카드용. 화면 아래 GuidePanel이 받은 설명 응답의 next_steps를 그대로 넘겨받는다.
// 같은 요청을 한 번 더 보내지 않으려고 GuidePanel의 onLoaded를 쓴다. 꺼져 있으면 onLoaded가 undefined라 GuidePanel은 지금과 같다.
import { useState } from 'react'
import type { Guide, NextSteps } from '../types'

export function useGuideNextSteps(input: object | null, on: boolean) {
  const [got, setGot] = useState<{ input: object; steps: NextSteps | null } | null>(null)
  const onLoaded = on
    ? (i: object, guide: Guide | null) => setGot({ input: i, steps: guide?.next_steps ?? null })
    : undefined
  // 지금 계산한 입력에 대한 응답일 때만 쓴다 (입력이 바뀌면 이전 응답을 쓰지 않는다)
  const nextSteps = got !== null && got.input === input ? got.steps : null
  return { nextSteps, onLoaded }
}
